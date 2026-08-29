"""MCP tool: analyze_repo — parse a repository and build the dependency graph.

This is the entry-point tool for the IDE-driven wiki generation pipeline.
It runs CodeWiki's Tree-sitter-based dependency analyzer (no LLM needed),
caches results in SQLite and creates a new session with lazy-loaded components.

Incremental mode: on subsequent calls, detects changed files via Git (commit
diff + staged + unstaged/untracked) or file fingerprints, and only re-parses
changed files.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from codewiki.mcp.cache import (
    AnalysisCache,
    ComponentMeta,
    LazyComponentStore,
    default_cache_db,
)
from codewiki.mcp.session import SessionStore
from codewiki.mcp.workspace import SessionWorkspace

logger = logging.getLogger(__name__)


def _read_source_from_disk(node) -> str:
    """Re-read component source from the original file using line range."""
    fp = getattr(node, "file_path", "")
    sl = getattr(node, "start_line", 0)
    el = getattr(node, "end_line", 0)
    if not fp:
        return ""
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if sl > 0 and el > 0:
            return "".join(lines[max(0, sl - 1) : el])
        return "".join(lines)
    except Exception as e:
        logger.warning("Failed to read source for %s: %s", fp, e)
        return ""


def handle_analyze_repo(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Run dependency analysis, cache to SQLite, create session with lazy store."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        return json.dumps({"error": f"Repository not found: {repo_path}"})

    # Layout-aware default output_dir (ticket 04): an explicit argument always
    # wins; otherwise a centralized-workspace member repo analyses into the
    # workspace knowledge base, everything else keeps <repo>/repowiki.
    _od_arg = (arguments.get("output_dir") or "").strip()
    if _od_arg:
        output_dir = Path(_od_arg).expanduser().resolve()
    else:
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        output_dir = default_output_dir(repo_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    import tempfile
    from codewiki.src.config import Config, MAX_DEPTH

    # Use a temp dir for the legacy JSON output — we write to SQLite instead
    _tmp = Path(tempfile.mkdtemp(prefix="codewiki_"))
    config = Config(
        repo_path=str(repo_path),
        output_dir=str(_tmp),
        dependency_graph_dir=str(_tmp / "dependency_graphs"),
        docs_dir=str(output_dir),
        max_depth=MAX_DEPTH,
        llm_base_url="not-needed",
        llm_api_key="not-needed",
        main_model="unused",
        cluster_model="unused",
    )

    include = arguments.get("include_patterns")
    exclude = arguments.get("exclude_patterns")
    doc_type = arguments.get("doc_type", "design")
    custom_instructions = arguments.get("custom_instructions")
    ai: Dict[str, Any] = {"doc_type": doc_type}
    if include:
        ai["include_patterns"] = [p.strip() for p in include.split(",")]
    if exclude:
        ai["exclude_patterns"] = [p.strip() for p in exclude.split(",")]
    if custom_instructions:
        ai["custom_instructions"] = custom_instructions
    config.agent_instructions = ai

    # Get or create shared cache for this repo
    cache = store.get_cache(str(repo_path))

    # Incremental check
    incremental = arguments.get("incremental", True)
    changes_info = None
    cached_unchanged_components: Dict[str, Any] = {}
    skip_file_paths: Optional[set] = None

    if incremental and cache.is_fresh():
        changes_info = cache.detect_changes()
        if changes_info and changes_info.get("no_changes"):
            # No changes — reuse cached data
            return _build_no_change_response(repo_path, output_dir, store, cache, changes_info)
        if changes_info and changes_info.get("changed_files"):
            changed = changes_info["changed_files"]
            logger.info("Incremental mode: %d files changed", len(changed))
            # Remove stale components and routes for changed files
            for cf in changed:
                cache.remove_by_file(cf)
                try:
                    cache.remove_routes_by_file(cf)
                except Exception as e:
                    logger.warning("Route removal for %s failed (non-fatal): %s", cf, e)

            # Compute set of unchanged files to skip during parsing
            all_cached_paths = cache.get_cached_file_paths()
            # These are the relative paths of files that are still cached and unchanged
            unchanged_rel_paths = all_cached_paths  # After remove_by_file, only unchanged remain

            # Load cached components for unchanged files
            cached_unchanged_components = cache.get_components_by_files(unchanged_rel_paths)

            # Build set of absolute paths to skip during parsing
            skip_file_paths = set()
            for comp in cached_unchanged_components.values():
                if comp.file_path:
                    skip_file_paths.add(comp.file_path)

            logger.info(
                "Incremental: %d cached components from %d unchanged files, "
                "will skip %d files during parsing",
                len(cached_unchanged_components),
                len(unchanged_rel_paths),
                len(skip_file_paths),
            )

    # Full parse (writes legacy JSONs to _tmp — clean up afterwards)
    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    import shutil

    builder = DependencyGraphBuilder(config)
    try:
        components, leaf_nodes, routes = builder.build_dependency_graph(
            skip_file_paths=skip_file_paths
        )
    finally:
        shutil.rmtree(str(_tmp), ignore_errors=True)

    # Merge cached unchanged components with newly parsed ones
    if cached_unchanged_components:
        for comp_id, node in cached_unchanged_components.items():
            if comp_id not in components:
                components[comp_id] = node
        logger.info(
            "Merged %d cached components with %d newly parsed = %d total",
            len(cached_unchanged_components),
            len(components) - len(cached_unchanged_components),
            len(components),
        )
        # Recompute leaf nodes on the full merged graph — the builder only
        # saw the changed-file subgraph, so its leaf_nodes list is partial
        # and would otherwise overwrite the full list in repo_meta.
        try:
            from codewiki.src.be.dependency_analyzer.topo_sort import (
                build_graph_from_components,
                get_leaf_nodes,
            )

            graph = build_graph_from_components(components)
            raw_leafs = get_leaf_nodes(graph, components)
            valid_types = {"class", "interface", "struct"}
            available_types = {c.component_type for c in components.values()}
            if not available_types & valid_types:
                valid_types.add("function")
            leaf_nodes = [
                n
                for n in raw_leafs
                if isinstance(n, str)
                and n in components
                and components[n].component_type in valid_types
            ]
            logger.info("Recomputed %d leaf nodes on merged graph", len(leaf_nodes))
        except Exception as e:
            logger.warning("Leaf-node recompute failed, merging with cached list: %s", e)
            old_leafs = cache.get_leaf_nodes()
            merged = [n for n in old_leafs if n in components]
            merged.extend(n for n in leaf_nodes if n not in merged)
            leaf_nodes = merged

    # Write to SQLite cache (incremental mode if we had cached components)
    is_incremental = bool(cached_unchanged_components)
    try:
        cache.batch_insert_components(components, leaf_nodes, incremental=is_incremental)
        logger.info(
            "Components cached to SQLite (%s mode)", "incremental" if is_incremental else "full"
        )
    except Exception as e:
        logger.warning("SQLite cache write failed (continuing in memory): %s", e)

    # Store cross-service routes to SQLite cache
    try:
        if routes:
            cache.batch_insert_routes(routes, incremental=is_incremental)
            logger.info("Cached %d routes to SQLite", len(routes))
    except Exception as e:
        logger.warning("Route cache write failed (non-fatal): %s", e)

    # Monorepo sub-service detection + intra-repo cross-service analysis
    cross_service_info: Dict[str, Any] = {}
    detect_services_flag = arguments.get("detect_services", True)
    if detect_services_flag:
        try:
            cross_service_info = _run_monorepo_cross_service(
                repo_path,
                output_dir,
                cache,
            )
        except Exception as e:
            logger.warning("Monorepo cross-service analysis failed (non-fatal): %s", e)

    # Build LazyComponentStore from ComponentMeta
    metas: Dict[str, ComponentMeta] = {}
    for comp_id, node in components.items():
        metas[comp_id] = ComponentMeta(
            id=node.id,
            name=node.name,
            component_type=node.component_type,
            file_path=node.file_path,
            relative_path=node.relative_path,
            start_line=node.start_line,
            end_line=node.end_line,
            language=(node.language or "").strip() or "unknown",
            depends_on=node.depends_on,
            node_type=node.node_type,
            base_classes=node.base_classes,
            class_name=node.class_name,
            display_name=node.display_name,
            qualified_name=node.qualified_name,
            has_docstring=node.has_docstring,
            parameters=node.parameters,
        )
    lazy_store = LazyComponentStore(cache, metas)

    # Create session
    session = store.create(
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        components=lazy_store,
        leaf_nodes=leaf_nodes,
        cache=cache,
    )
    # Remember the analysis options so watch-mode incremental re-parses
    # apply the same include/exclude filtering (see tools/watch.py).
    session.analyze_options = {
        "include_patterns": include,
        "exclude_patterns": exclude,
        "detect_services": arguments.get("detect_services", True),
    }

    # Record analyzed commit
    from codewiki.cli.utils.repo_validator import get_git_commit_hash

    session.analyzed_commit = get_git_commit_hash(repo_path) or None
    if session.analyzed_commit:
        cache.set_last_commit_id(session.analyzed_commit)
    try:
        cache.set_output_dir(str(output_dir))
    except Exception as e:
        logger.warning("Failed to persist output_dir to cache: %s", e)

    # Persist repo_path ↔ output_dir mapping (enables session-free SQLite access)
    try:
        from codewiki.src.config import meta_join, PROJECT_FILENAME

        meta_dir = Path(meta_join(output_dir, ""))
        meta_dir.mkdir(parents=True, exist_ok=True)
        # T1b: relative paths so project.json stays valid on teammates'
        # machines / other checkouts. Absolute paths would silently break
        # anywhere except the machine that wrote them (stale-session hijack).
        try:
            _rel_output = str(output_dir.resolve().relative_to(repo_path.resolve()))
        except ValueError:
            _rel_output = output_dir.name  # output_dir outside repo — best effort
        # cache_db is resolved by consumers against output_dir.parent; express
        # it relative to that anchor so it stays valid in both layouts
        # (standard: ".codewiki/analysis_cache.db"; centralized:
        # ".codewiki/<repo>/analysis_cache.db" under the workspace root).
        try:
            _cache_rel = os.path.relpath(default_cache_db(repo_path), output_dir.parent).replace(
                "\\", "/"
            )
        except ValueError:
            _cache_rel = ".codewiki/analysis_cache.db"
        project_info = {
            "repo_name": repo_path.name,
            "output_dir": _rel_output.replace("\\", "/"),
            "cache_db": _cache_rel,
        }
        Path(meta_join(output_dir, PROJECT_FILENAME)).write_text(
            json.dumps(project_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Failed to write project.json: %s", e)

    # Create workspace
    workspace = SessionWorkspace(repo_path, session.session_id)
    session.workspace = workspace
    SessionWorkspace.cleanup_legacy_sessions(repo_path)

    # -- Write workspace files --

    # Language stats (used inline in summary + response, not as separate file)
    langs: Dict[str, int] = {}
    for m in metas.values():
        lang = (m.language or "").strip()
        if not lang or lang.lower() in ("null", "none", "unknown"):
            lang = "unknown"
        langs[lang] = langs.get(lang, 0) + 1
    # component_index: use list_components tool (on-demand with filtering)
    # leaf_nodes: preview in summary.json; full list via leaf_nodes in session

    # 4. Incremental changes (from current run or saved metadata.json)
    if changes_info is None:
        changes_info = _detect_doc_changes(repo_path, output_dir, components=metas)
    if changes_info is not None:
        workspace.write_json("changes.json", changes_info)

    # 5. Summary
    summary = {
        "session_id": session.session_id,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "output_dir": str(output_dir),
        "total_components": len(metas),
        "total_leaf_nodes": len(leaf_nodes),
        "languages": langs,
        "leaf_nodes_preview": leaf_nodes[:20],
    }
    workspace.write_json("summary.json", summary)

    # 6. Schema
    schema_info = None
    try:
        from codewiki.mcp.tools.schema_generator import generate_schema

        module_names = []
        from codewiki.src.config import meta_resolve

        mtp = Path(meta_resolve(output_dir, "module_tree.json"))
        if mtp.exists():
            try:
                mt = json.loads(mtp.read_text(encoding="utf-8"))
                if isinstance(mt, dict):
                    module_names = list(mt.keys())
            except Exception:
                pass
        # schema_generator needs a dict; pass the lazy store (works for len() and iteration)
        schema_info = generate_schema(
            repo_path.name, metas, list(langs.keys()), output_dir, module_names
        )
        workspace.write_json("schema.json", schema_info)
    except Exception as e:
        logger.warning("Schema generation skipped: %s", e)

    # 7. Index/log
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log

        append_log(
            str(output_dir), "analyze_repo", f"分析仓库 {repo_path.name}，{len(metas)} 个组件"
        )
        rebuild_index(str(output_dir))
    except Exception as e:
        logger.warning("Index/log update failed: %s", e)

    # 7b. Extract and save overview refs for stale detection
    try:
        overview_refs = _extract_overview_refs(output_dir)
        if overview_refs:
            _save_overview_refs(output_dir, overview_refs)
            logger.info("Saved %d overview refs for stale detection", len(overview_refs))
    except Exception as e:
        logger.warning("Overview refs extraction failed: %s", e)

    # 7c. Update overview_stale in metadata.json
    try:
        from codewiki.src.config import meta_resolve, PROJECT_FILENAME

        meta_path = Path(meta_resolve(output_dir, "metadata.json"))
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            overview_stale = changes_info.get("overview_stale", False) if changes_info else False
            metadata["overview_stale"] = overview_stale
            meta_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as e:
        logger.warning("Failed to update overview_stale in metadata: %s", e)

    # 8. Symbol map (class name → source file, used by ingest_note for crosslinking)
    try:
        symbol_map = _build_symbol_map(metas)
        # Primary: SQLite (fast lookup, no full-file parse)
        cache.save_symbol_map(symbol_map)
        # Compat: keep a compact JSON copy for tools that read it directly
        from codewiki.src.config import meta_join

        meta_dir = Path(meta_join(output_dir, ""))
        meta_dir.mkdir(parents=True, exist_ok=True)
        symbol_map_path = Path(meta_join(output_dir, "symbol_map.json"))
        symbol_map_path.write_text(
            json.dumps(symbol_map, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        logger.info("Symbol map written: %d symbols (SQLite + JSON)", len(symbol_map))
    except Exception as e:
        logger.warning("Symbol map generation failed (non-fatal): %s", e)

    # 9. Update file fingerprints for incremental next run
    try:
        # Repo-relative paths on purpose: _fp_detect() keys its fingerprint
        # rows by relative path (os.walk output). Absolute paths would make
        # every file look changed on the next fingerprint poll.
        all_files = list({m.relative_path for m in metas.values() if m.relative_path})
        if all_files:
            cache.update_file_fingerprints(all_files, session.analyzed_commit or "")
    except Exception as e:
        logger.warning("Fingerprint update failed: %s", e)

    # Release source_code from memory
    for node in components.values():
        node.source_code = None

    # -- MCP response --
    result = {
        "session_id": session.session_id,
        "workspace_dir": str(workspace.root),
        "repo_name": repo_path.name,
        "output_dir": str(output_dir),
        "stats": {
            "total_components": len(metas),
            "total_leaf_nodes": len(leaf_nodes),
            "languages": langs,
        },
        "files": {
            "summary": str(workspace.root / "summary.json"),
            "schema": str(output_dir / "schema.yaml"),
        },
        "changes": changes_info,
        "cache_mode": "sqlite",
        "hint": (
            "Read the files above for full data. "
            "The schema.yaml at output_dir defines documentation conventions (required sections, "
            "documentation dimensions, line limits). Share it with the user — they can edit it "
            "before generating docs to customize output style and structure. "
            "Use read_code_components(repo_path, component_ids) to read source code. "
            "Use save_module_tree(repo_path, module_tree) after clustering. "
            "Call get_prompt('cluster') for clustering rules."
        ),
    }
    if cross_service_info:
        result["cross_service"] = cross_service_info
    if changes_info and not changes_info.get("no_changes"):
        result["hint"] = (
            "Incremental update detected. Only update affected modules. "
            + changes_info.get("hint", "")
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def _build_no_change_response(
    repo_path: Path,
    output_dir: Path,
    store: SessionStore,
    cache: AnalysisCache,
    changes_info: Dict,
) -> str:
    """Build session from cached data when no changes are detected."""
    metas = cache.get_all_metas()
    leaf_nodes = cache.get_leaf_nodes()
    lazy_store = LazyComponentStore(cache, metas)

    session = store.create(
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        components=lazy_store,
        leaf_nodes=leaf_nodes,
        cache=cache,
    )
    from codewiki.cli.utils.repo_validator import get_git_commit_hash

    session.analyzed_commit = get_git_commit_hash(repo_path) or None
    try:
        cache.set_output_dir(str(output_dir))
    except Exception as e:
        logger.warning("Failed to persist output_dir to cache: %s", e)

    workspace = SessionWorkspace(repo_path, session.session_id)
    session.workspace = workspace
    SessionWorkspace.cleanup_legacy_sessions(repo_path)

    langs = {}
    for m in metas.values():
        lang = (m.language or "").strip()
        if not lang or lang.lower() in ("null", "none", "unknown"):
            lang = "unknown"
        langs[lang] = langs.get(lang, 0) + 1
    workspace.write_json("changes.json", changes_info)

    summary = {
        "session_id": session.session_id,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "output_dir": str(output_dir),
        "total_components": len(metas),
        "total_leaf_nodes": len(leaf_nodes),
        "languages": langs,
        "leaf_nodes_preview": leaf_nodes[:20],
    }
    workspace.write_json("summary.json", summary)

    return json.dumps(
        {
            "session_id": session.session_id,
            "workspace_dir": str(workspace.root),
            "repo_name": repo_path.name,
            "output_dir": str(output_dir),
            "stats": {
                "total_components": len(metas),
                "total_leaf_nodes": len(leaf_nodes),
                "languages": langs,
            },
            "files": {
                "summary": str(workspace.root / "summary.json"),
            },
            "changes": changes_info,
            "cache_mode": "sqlite",
            "hint": "No changes detected since last analysis. Documentation is up to date.",
        },
        indent=2,
        ensure_ascii=False,
    )


def _run_monorepo_cross_service(
    repo_path: Path,
    output_dir: Path,
    cache: AnalysisCache,
) -> Dict[str, Any]:
    """Detect sub-services in a monorepo and run intra-repo cross-service matching.

    Loads the *full* route set from the SQLite cache (not just newly-parsed
    routes) so that incremental mode produces correct results.  Re-tags all
    routes with sub-service labels and writes the complete set back.

    Returns a cross_service info dict for the response, or an empty dict
    if fewer than 2 sub-services are detected.
    """
    from codewiki.src.be.dependency_analyzer.analysis.service_detector import (
        detect_services,
    )

    services = detect_services(repo_path)
    if len(services) < 2:
        return {}

    logger.info(
        "Monorepo cross-service: %d sub-services detected in %s",
        len(services),
        repo_path.name,
    )

    # Load the FULL route set from cache (includes unchanged routes in
    # incremental mode — the `routes` variable from build_dependency_graph
    # only contains newly-parsed files).
    try:
        all_routes = cache.get_all_routes()
    except Exception as e:
        logger.warning("Failed to load routes from cache: %s", e)
        return {}

    if not all_routes:
        return {}

    # Re-tag all routes with sub-service labels
    repo_name = repo_path.name
    retagged = _retag_routes_by_service(all_routes, services, str(repo_path), repo_name)

    # Write back the complete retagged set (replaces old repo_name values)
    try:
        cache.batch_insert_routes(retagged, incremental=False)
        logger.info("Re-tagged %d routes with sub-service labels", len(retagged))
    except Exception as e:
        logger.warning("Failed to update route cache with service labels: %s", e)

    # Convert to RouteNode objects and group by service
    from codewiki.src.be.dependency_analyzer.analysis.cross_service_matcher import (
        CrossServiceMatcher,
    )
    from codewiki.src.be.dependency_analyzer.models.cross_service import (
        RouteNode,
        RouteProtocol,
        RouteRole,
    )

    matcher = CrossServiceMatcher()
    service_routes: Dict[str, List[RouteNode]] = {}

    for rd in retagged:
        try:
            node = RouteNode(
                route_key=rd["route_key"],
                protocol=RouteProtocol(rd.get("protocol", "http")),
                method=rd.get("method"),
                path=rd.get("path", ""),
                role=RouteRole(rd.get("role", "server")),
                component_id=rd.get("component_id", ""),
                repo_name=rd.get("repo_name", repo_name),
                file_path=rd.get("file_path", ""),
                line_number=rd.get("line_number", 0),
                framework=rd.get("framework"),
                extra=rd.get("extra", {}),
            )
            svc = node.repo_name
            if svc not in service_routes:
                service_routes[svc] = []
            service_routes[svc].append(node)
        except Exception:
            continue

    for svc_name, svc_nodes in service_routes.items():
        matcher.add_repo_routes(svc_name, svc_nodes)

    topology = matcher.match()
    logger.info(
        "Intra-repo cross-service matching: %d routes → %d links, %d unmatched",
        len(topology.routes),
        len(topology.links),
        len(topology.unmatched_routes),
    )

    # Render topology as Markdown
    from codewiki.src.be.dependency_analyzer.analysis.topology_visualizer import (
        TopologyVisualizer,
    )

    viz = TopologyVisualizer()
    cross_service_md = viz.render_overview_section(topology)

    # Persist results to <output_dir>/.meta/
    try:
        from codewiki.src.config import meta_join

        meta_dir = Path(meta_join(output_dir, ""))
        meta_dir.mkdir(parents=True, exist_ok=True)

        links_data = [link.model_dump() for link in topology.links]
        (meta_dir / "cross_service_links.json").write_text(
            json.dumps(links_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        routes_data = [route.model_dump() for route in topology.routes]
        (meta_dir / "workspace_routes.json").write_text(
            json.dumps(routes_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Cross-service results persisted to %s", meta_dir)
    except Exception as e:
        logger.warning("Failed to persist cross-service results: %s", e)

    # Run InfraScanner for supplementary service discovery
    try:
        from codewiki.src.be.dependency_analyzer.analysis.infra_scanner import InfraScanner

        scanner = InfraScanner(str(repo_path))
        infra_services = scanner.scan()
        if infra_services:
            from codewiki.src.config import meta_join

            meta_dir = Path(meta_join(output_dir, ""))
            meta_dir.mkdir(parents=True, exist_ok=True)
            infra_data = {name: svc.to_dict() for name, svc in infra_services.items()}
            (meta_dir / "infra_services.json").write_text(
                json.dumps(infra_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as e:
        logger.debug("Infra scanner skipped: %s", e)

    return {
        "services_detected": sorted(services.keys()),
        "total_routes": len(topology.routes),
        "total_links": len(topology.links),
        "total_unmatched": len(topology.unmatched_routes),
        "cross_service_md": cross_service_md,
    }


def _retag_routes_by_service(
    routes: List[Dict],
    services: Dict,
    repo_path: str,
    fallback_repo_name: str,
) -> List[Dict]:
    """Re-assign repo_name on each route dict based on sub-service membership.

    Uses longest-prefix matching on the route's file_path (relative to
    ``repo_path``) to determine which sub-service it belongs to.  Routes
    that don't fall under any detected service get the label ``_root``.
    """
    from codewiki.src.be.dependency_analyzer.analysis.service_detector import (
        assign_service_label,
    )

    retagged: List[Dict] = []
    for rd in routes:
        rd = dict(rd)  # shallow copy to avoid mutating the original
        fp = rd.get("file_path", "")
        label = assign_service_label(fp, services, repo_path=repo_path, fallback="_root")
        rd["repo_name"] = label
        retagged.append(rd)
    return retagged


_LINKABLE_TYPES = {"class", "interface", "struct", "enum", "record", "annotation"}


def _build_symbol_map(metas: Dict[str, ComponentMeta]) -> Dict[str, List[str]]:
    """Build a mapping from symbol name to source file path(s).

    Only includes class-like component types.  Returns
    ``{name: [relative_path, ...]}``.
    """
    symbol_map: Dict[str, List[str]] = {}
    for meta in metas.values():
        if meta.component_type not in _LINKABLE_TYPES:
            continue
        if not meta.name or not meta.relative_path:
            continue
        if meta.name not in symbol_map:
            symbol_map[meta.name] = []
        if meta.relative_path not in symbol_map[meta.name]:
            symbol_map[meta.name].append(meta.relative_path)
    # Sort file lists for deterministic output
    for paths in symbol_map.values():
        paths.sort()
    return symbol_map


def _detect_doc_changes(
    repo_path: Path,
    output_dir: Path,
    components: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Detect documentation-level changes since last generation (legacy JSON fallback)."""
    from codewiki.src.config import meta_resolve

    mp = Path(meta_resolve(output_dir, "metadata.json"))
    mtp = Path(meta_resolve(output_dir, "module_tree.json"))
    if not mp.exists() or not mtp.exists():
        return None
    try:
        md = json.loads(mp.read_text(encoding="utf-8"))
        mt = json.loads(mtp.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Git detection from metadata.json
    changes = _detect_git_from_meta(repo_path, md, output_dir)
    if changes is None:
        changes = _detect_mtime_from_meta(repo_path, md)

    if changes is None:
        return None
    cf = changes["changed_files"]
    if not cf:
        return {
            "has_previous": True,
            "no_changes": True,
            "method": changes.get("method", "unknown"),
        }
    affected, cascade = _find_affected_modules(mt, cf, components=components)

    # Precise overview stale check: only mark overview stale if it actually
    # references affected modules (instead of always cascading)
    overview_stale = _check_overview_stale(output_dir, mt, affected)
    # Remove "overview" from cascade (added unconditionally by _find_affected_modules)
    cascade.discard("overview")
    if overview_stale:
        cascade.add("overview")

    return {
        "has_previous": True,
        "no_changes": False,
        "method": changes.get("method", "unknown"),
        "changed_files": cf,
        "affected_modules": sorted(affected),
        "cascade_modules": sorted(cascade),
        "overview_stale": overview_stale,
        "hint": f"Only {len(affected)} module(s) need updating."
        + (" Overview.md is stale." if overview_stale else ""),
    }


def _detect_git_from_meta(repo_path: Path, metadata: Dict, output_dir: Path) -> Optional[Dict]:
    try:
        import git

        repo = git.Repo(repo_path, search_parent_directories=True)
    except Exception:
        return None
    prev = metadata.get("generation_info", {}).get("commit_id")
    if not prev:
        return None
    try:
        cur = repo.head.commit.hexsha
    except Exception:
        return None
    git_root = Path(repo.working_dir).resolve()
    try:
        sp = repo_path.resolve().relative_to(git_root).as_posix()
    except ValueError:
        sp = ""
    if sp == ".":
        sp = ""

    od_rel = ""
    try:
        od_rel = Path(output_dir).resolve().relative_to(repo_path.resolve()).as_posix()
        if od_rel == ".":
            od_rel = ""
    except Exception:
        pass

    def _n(p: str) -> Optional[str]:
        if sp and not p.startswith(sp + "/"):
            return None
        p = p[len(sp) + 1 :] if sp else p
        if p.startswith(".codewiki/"):
            return None
        if od_rel and (p == od_rel or p.startswith(od_rel + "/")):
            return None
        return p

    ch, seen = [], set()

    def add(r):
        if r and (p := _n(r)) and p not in seen:
            ch.append(p)
            seen.add(p)

    if prev != cur:
        try:
            for d in repo.commit(prev).diff(cur):
                add(d.a_path)
                add(d.b_path)
        except Exception:
            logger.warning("Commit %s unreachable", prev)
            return None
    try:
        for d in list(repo.index.diff("HEAD")) + list(repo.index.diff(None)):
            add(d.a_path)
            add(d.b_path)
        for item in repo.untracked_files:
            add(item)
    except Exception:
        pass
    return {"changed_files": ch, "method": "git"}


def _detect_mtime_from_meta(repo_path: Path, metadata: Dict) -> Optional[Dict]:
    ts = metadata.get("generation_info", {}).get("timestamp")
    if not ts:
        return None
    try:
        from datetime import datetime

        prev = datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None
    exts = {
        ".py",
        ".java",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".hh",
        ".cs",
        ".kt",
        ".kts",
        ".go",
        ".php",
        ".rs",
    }
    ch = []
    for dp, dns, fns in os.walk(repo_path):
        dns[:] = [
            d
            for d in dns
            if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")
        ]
        for fn in fns:
            fp = Path(dp) / fn
            if fp.suffix.lower() not in exts:
                continue
            try:
                if fp.stat().st_mtime > prev:
                    ch.append(fp.relative_to(repo_path).as_posix())
            except OSError:
                continue
    return {"changed_files": ch, "method": "mtime"}


def _find_affected_modules(
    module_tree: Dict,
    changed_files: List[str],
    components: Optional[Dict[str, Any]] = None,
):
    """Find modules affected by changed files.

    When *components* is provided (a dict of comp_id → ComponentMeta/Node),
    uses graph-based transitive impact analysis: changed files are resolved
    to component IDs, then a reverse BFS finds all transitively affected
    components, which are mapped back to modules.  This catches cross-module
    callers that file-path matching would miss.

    Falls back to file-path substring matching + tree-ancestor cascading
    when *components* is None (legacy / disk-only context).
    """
    # --- Graph-based path (preferred) ----------------------------------
    if components:
        try:
            from codewiki.src.be.dependency_analyzer.topo_sort import (
                build_graph_from_components,
                resolve_files_to_components,
                transitive_impact,
            )

            start_ids = resolve_files_to_components(components, changed_files)
            if start_ids:
                graph = build_graph_from_components(components)
                result = transitive_impact(
                    graph,
                    set(start_ids),
                    max_depth=10,
                    direction="depended_by",
                )
                affected_ids = set(result["affected"].keys())

                # Map affected component IDs → modules
                affected: Set[str] = set()
                cascade: Set[str] = set()

                def _walk_graph(tree: Dict, parents: Optional[List[str]] = None):
                    if parents is None:
                        parents = []
                    for mn, mi in tree.items():
                        comps = mi.get("components", [])
                        hit = any(c in affected_ids for c in comps)
                        if hit:
                            affected.add(mn)
                            cascade.update(parents)
                        children = mi.get("children", {})
                        if isinstance(children, dict) and children:
                            _walk_graph(children, parents + [mn])

                _walk_graph(module_tree)
                if affected:
                    cascade.add("overview")
                return affected, cascade
        except Exception:
            logger.debug("Graph-based impact failed, falling back to path matching", exc_info=True)

    # --- File-path fallback (original logic) ---------------------------
    affected, cascade = set(), set()

    def _walk(tree, parents=None):
        if parents is None:
            parents = []
        for mn, mi in tree.items():
            comps = mi.get("components", [])
            hit = False
            for c in comps:
                cf = c.split("::")[0]
                for chf in changed_files:
                    if cf == chf or cf.endswith("/" + chf) or chf.endswith("/" + cf):
                        hit = True
                        break
                    if chf.startswith(cf + "/") or cf.startswith(chf + "/"):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                affected.add(mn)
                cascade.update(parents)
            children = mi.get("children", {})
            if isinstance(children, dict) and children:
                _walk(children, parents + [mn])

    _walk(module_tree)
    if affected:
        cascade.add("overview")
    return affected, cascade


def _extract_overview_refs(output_dir: Path) -> Set[str]:
    """Extract module names referenced in overview.md by parsing wiki-links and markdown links.

    Returns a set of module names (slugs) that overview.md links to.
    """
    import re

    overview_path = output_dir / "overview.md"
    if not overview_path.exists():
        return set()

    try:
        content = overview_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    refs: Set[str] = set()

    # Match [[Name]](file.md) wiki-links
    wikilink_re = re.compile(r"\[\[([^\]]+)\]\]\(([^\)]+\.md)\)")
    for m in wikilink_re.finditer(content):
        ref_name = m.group(1).strip()
        # Use the slug (lowercase, hyphenated) as the module identifier
        slug = ref_name.lower().replace(" ", "-").replace("_", "-")
        refs.add(slug)
        # Also add the raw name for matching
        refs.add(ref_name.lower().replace(" ", "_"))

    # Match [text](path.md) markdown links
    mdlink_re = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")
    for m in mdlink_re.finditer(content):
        ref_file = m.group(2)
        if ref_file.startswith(("http://", "https://")):
            continue
        # Extract the module name from the file path (stem)
        stem = Path(ref_file).stem.lower().replace("-", "_")
        refs.add(stem)
        # Also add hyphenated form
        refs.add(stem.replace("_", "-"))

    return refs


def _save_overview_refs(output_dir: Path, refs: Set[str]):
    """Save overview refs to .meta/overview_refs.json."""
    from codewiki.src.config import meta_join

    meta_dir = Path(meta_join(output_dir, ""))
    meta_dir.mkdir(parents=True, exist_ok=True)
    refs_path = meta_dir / "overview_refs.json"
    refs_path.write_text(
        json.dumps(sorted(refs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_overview_refs(output_dir: Path) -> Set[str]:
    """Load overview refs from .meta/overview_refs.json."""
    from codewiki.src.config import meta_join

    meta_dir = Path(meta_join(output_dir, ""))
    refs_path = meta_dir / "overview_refs.json"
    if not refs_path.exists():
        return set()
    try:
        data = json.loads(refs_path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def _check_overview_stale(
    output_dir: Path,
    module_tree: Optional[Dict],
    affected_modules: Set[str],
) -> bool:
    """Check if overview.md references any modules that have changed.

    Returns True if overview.md is stale (references affected modules).
    """
    if not affected_modules:
        return False

    overview_refs = _load_overview_refs(output_dir)
    if not overview_refs:
        # If no refs tracked yet, extract them now
        overview_refs = _extract_overview_refs(output_dir)
        _save_overview_refs(output_dir, overview_refs)

    if not overview_refs:
        return False

    # Check if any affected module is referenced in overview
    for mod in affected_modules:
        mod_lower = mod.lower()
        mod_slug = mod_lower.replace("_", "-")
        mod_under = mod_lower.replace("-", "_")
        if mod_lower in overview_refs or mod_slug in overview_refs or mod_under in overview_refs:
            return True

    return False
