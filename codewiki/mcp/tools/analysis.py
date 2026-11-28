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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, overload

from codewiki.mcp.cache import (
    AnalysisCache,
    ComponentMeta,
    LazyComponentStore,
    default_cache_db,
    resolve_analysis_meta_file,
)
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import job_state
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


def _collect_artifact_facts(
    repo_path: Path,
    output_dir: Path,
    *,
    include_patterns: str | None,
    exclude_patterns: str | None,
) -> Dict[str, Any]:
    """Collect and persist C3 facts without letting failures block source analysis."""

    from codewiki.mcp.tools.artifact_facts import (
        ArtifactFactOptions,
        analyze_artifact_facts,
        artifact_facts_path,
        unavailable_artifact_facts,
    )

    def _patterns(value: str | None) -> tuple[str, ...]:
        return tuple(item.strip() for item in (value or "").split(",") if item.strip())

    try:
        path = artifact_facts_path(repo_path, output_dir)
        previous: Dict[str, Any] | None = None
        previous_text: str | None = None
        if path.exists():
            try:
                previous_text = path.read_text(encoding="utf-8")
                loaded = json.loads(previous_text)
                previous = loaded if isinstance(loaded, dict) else {}
            except (OSError, UnicodeError, ValueError):
                previous = {}
                previous_text = None
        result = analyze_artifact_facts(
            repo_path,
            previous=previous,
            options=ArtifactFactOptions(
                include_patterns=_patterns(include_patterns),
                exclude_patterns=_patterns(exclude_patterns),
            ),
        )
        if previous is not None and previous_text is None:
            result["status"] = "partial"
            result["warnings"].append("previous_index_unreadable")
            result["warnings"] = sorted(set(result["warnings"]))
        serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            if serialized != previous_text:
                from codewiki.src.store import atomic_write

                atomic_write(path, serialized)
        except Exception as exc:  # noqa: BLE001 - persistence must not discard valid facts
            result["status"] = "partial"
            result["warnings"].append(f"persist_failed:{type(exc).__name__}")
            result["warnings"] = sorted(set(result["warnings"]))
            logger.warning("Artifact facts persistence failed (non-fatal): %s", exc)
        return result
    except Exception as exc:  # noqa: BLE001 - C3 is an optional fail-open fact layer
        logger.warning("Artifact facts collection failed (non-fatal): %s", exc)
        return unavailable_artifact_facts(type(exc).__name__)


def _merge_artifact_changes(
    changes_info: Optional[Dict[str, Any]], artifact_facts: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Merge artifact-only changes into the existing incremental change list."""

    changed = list(artifact_facts.get("changed_files", []))
    if changes_info is None:
        if not changed:
            return None
        return {
            "added_files": [],
            "modified_files": [],
            "deleted_files": [],
            "changed_files": changed,
            "artifact_changed_files": changed,
            "no_changes": False,
        }
    existing = list(changes_info.get("changed_files") or [])
    changes_info["changed_files"] = sorted(set(existing) | set(changed))
    changes_info["artifact_changed_files"] = changed
    if changed:
        changes_info["no_changes"] = False
    return changes_info


def _expand_semantic_manifest_changes(cache: AnalysisCache, changed_files: List[str]) -> List[str]:
    """把语义 manifest 变化扩展为对应语言的全部缓存源码文件。

    ``go.mod`` 决定 module/local replace，``pubspec.yaml`` 决定 package 名；
    它们变化时，未修改的 caller 也必须重解析，否则缓存会恢复旧解析边。
    """
    manifest_suffixes = {
        "go.mod": {".go"},
        "pubspec.yaml": {".dart"},
    }
    affected_suffixes: Set[str] = set()
    for path in changed_files:
        affected_suffixes.update(manifest_suffixes.get(Path(path).name, set()))
    if not affected_suffixes:
        return sorted(set(changed_files))
    affected_cached = {
        path
        for path in cache.get_cached_file_paths()
        if Path(path).suffix.lower() in affected_suffixes
    }
    return sorted(set(changed_files) | affected_cached)


def handle_analyze_repo(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Run dependency analysis, cache to SQLite, create session with lazy store."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        return json.dumps({"error": f"Repository not found: {repo_path}"})

    # output_dir is a pure function of repo_path under the active layout
    # (convergence: no explicit output_dir override on write paths — an
    # external process must not steer where this repo's knowledge lands).
    # Centralized member repos analyse into the workspace knowledge base;
    # everything else keeps <repo>/repowiki.
    from codewiki.mcp.tools.workspace_layout import default_output_dir

    output_dir = default_output_dir(repo_path)

    # Phase 4 second slice: session-start ff-only pull on the FIRST write
    # path this process touches.  analyze_repo may run before capture (or
    # standalone, e.g. CLI / direct handler calls), so it pulls the repo's
    # knowledge up to date before writing anything.  Once per process per
    # repo (git_sync._ff_pulled_repos); never raises.
    try:
        from codewiki.src.git_sync import session_ff_only

        _pull = session_ff_only(output_dir)
    except Exception as e:
        logger.debug("session_ff_only skipped: %s", e)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generation job ledger (ADR-0020): state and pointers only, never a
    # source of truth. Fail-open — a missing or unwritable ledger must not
    # block analysis.
    job_state.start_job(repo_path, output_dir, base_commit=_current_head(repo_path))

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
    previous_changed_components: Dict[str, Any] | None = None
    previous_components_for_ownership: Dict[str, Any] | None = None
    current_changed_components: Dict[str, Any] = {}
    component_changes: Dict[str, Any] = {"added": [], "deleted": [], "renamed": []}

    artifact_facts: Dict[str, Any] | None = None
    if incremental and cache.is_fresh():
        changes_info = cache.detect_changes()
        artifact_facts = _collect_artifact_facts(
            repo_path,
            output_dir,
            include_patterns=include,
            exclude_patterns=exclude,
        )
        changes_info = _merge_artifact_changes(changes_info, artifact_facts)
        if changes_info and changes_info.get("no_changes"):
            # No source or artifact changes — reuse cached data. Close the ledger
            # started above so it never lingers in ``analyzing`` (ADR-0020).
            job_state.finish_job(repo_path, output_dir)
            return _build_no_change_response(
                repo_path, output_dir, store, cache, changes_info, artifact_facts=artifact_facts
            )
        if changes_info and changes_info.get("changed_files"):
            changed = _expand_semantic_manifest_changes(cache, changes_info["changed_files"])
            changes_info["changed_files"] = changed
            logger.info("Incremental mode: %d files changed", len(changed))
            previous_changed_components = cache.get_components_by_files(set(changed))
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
            previous_components_for_ownership = dict(cached_unchanged_components)
            previous_components_for_ownership.update(previous_changed_components)

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

    if artifact_facts is None:
        artifact_facts = _collect_artifact_facts(
            repo_path,
            output_dir,
            include_patterns=include,
            exclude_patterns=exclude,
        )

    # Full parse (writes legacy JSONs to _tmp — clean up afterwards)
    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    import shutil

    builder = DependencyGraphBuilder(config)
    try:
        components, leaf_nodes, routes = builder.build_dependency_graph(
            skip_file_paths=skip_file_paths,
            cached_components=cached_unchanged_components,
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

    if changes_info is None:
        changes_info = _detect_doc_changes(repo_path, output_dir, components=components)
        if changes_info and changes_info.get("changed_files") and cache.is_fresh():
            changed = changes_info["changed_files"]
            previous_changed_components = cache.get_components_by_files(set(changed))
            previous_components_for_ownership = cache.get_all_metas()
    changes_info = _merge_artifact_changes(changes_info, artifact_facts)

    if previous_changed_components is not None:
        from codewiki.mcp.tools.reference_index import classify_component_changes

        assert changes_info is not None
        changed_paths = {str(path).replace("\\", "/") for path in changes_info["changed_files"]}
        current_changed_components = {
            component_id: node
            for component_id, node in components.items()
            if str(getattr(node, "relative_path", "") or "").replace("\\", "/") in changed_paths
        }
        component_changes = classify_component_changes(
            previous_changed_components, current_changed_components
        )

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
            metadata=node.metadata,
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
    # B3 在宿主随后保存树时复用与 changes.tree_repair 完全相同的 diff，
    # 不再实现第二份组件图差异逻辑。
    session.component_changes = component_changes
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
        from codewiki.src.store import atomic_write

        atomic_write(
            Path(meta_join(output_dir, PROJECT_FILENAME)),
            json.dumps(project_info, ensure_ascii=False, indent=2),
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
    if not current_changed_components and changes_info and changes_info.get("changed_files"):
        changed_paths = {str(path).replace("\\", "/") for path in changes_info["changed_files"]}
        current_changed_components = {
            component_id: node
            for component_id, node in metas.items()
            if str(getattr(node, "relative_path", "") or "").replace("\\", "/") in changed_paths
        }
    if changes_info is not None:
        changes_info["component_changes"] = component_changes
        _enrich_stale_pages(changes_info, output_dir)
        _enrich_stale_evidence(changes_info, output_dir)
        changes_info = _enrich_referencing_pages(
            changes_info,
            repo_path,
            output_dir,
            components=metas,
            previous_components=previous_changed_components,
            cache=cache,
        )
        changes_info = _enrich_ownership(
            changes_info,
            repo_path,
            output_dir,
            components=metas,
            previous_components=previous_components_for_ownership,
            changed_components=current_changed_components,
            deleted_component_ids=component_changes["deleted"],
        )
        changes_info = _enrich_tree_repair(
            changes_info,
            repo_path,
            output_dir,
            components=metas,
            component_changes=component_changes,
            tracked_component_ids=leaf_nodes,
        )
        workspace.write_json("changes.json", changes_info)

    # 5. Summary
    job_summary = job_state.job_summary(job_state.set_phase(repo_path, output_dir, "analyzed"))
    summary = {
        "session_id": session.session_id,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "output_dir": str(output_dir),
        "total_components": len(metas),
        "total_leaf_nodes": len(leaf_nodes),
        "languages": langs,
        "leaf_nodes_preview": leaf_nodes[:20],
        "artifact_facts": artifact_facts["summary"],
    }
    if job_summary is not None:
        summary["job"] = job_summary
    workspace.write_json("summary.json", summary)

    # 6. Schema
    schema_info = None
    try:
        from codewiki.mcp.tools.schema_generator import generate_schema

        module_names = []
        from codewiki.mcp.cache import resolve_analysis_meta_file

        mtp = resolve_analysis_meta_file(repo_path, output_dir, "module_tree.json")
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

    # 7c. Update overview_stale in metadata.json (or create the incremental
    # baseline anchor: generation_info.commit_id = HEAD at analysis time).
    try:
        from codewiki.mcp.cache import analysis_meta_dir

        meta_path = analysis_meta_dir(repo_path, output_dir) / "metadata.json"
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            overview_stale = changes_info.get("overview_stale", False) if changes_info else False
            metadata["overview_stale"] = overview_stale
        else:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            metadata = {
                "generation_info": {
                    "commit_id": _current_head(repo_path),
                    "timestamp": datetime.now().isoformat(),
                }
            }
        # ADR-0020: outward summary points back at the job ledger.
        if job_summary and job_summary.get("job_id"):
            metadata["job_id"] = job_summary["job_id"]
        from codewiki.src.store import locked_write

        locked_write(meta_path, json.dumps(metadata, ensure_ascii=False, indent=2))
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
        from codewiki.src.store import atomic_write

        atomic_write(
            symbol_map_path,
            json.dumps(symbol_map, ensure_ascii=False, separators=(",", ":")),
        )
        logger.info("Symbol map written: %d symbols (SQLite + JSON)", len(symbol_map))
    except Exception as e:
        logger.warning("Symbol map generation failed (non-fatal): %s", e)

    # 9. Update file fingerprints for incremental next run
    try:
        # Repo-relative paths on purpose: _fp_detect() keys its fingerprint
        # rows by relative path (os.walk output). Absolute paths would make
        # every file look changed on the next fingerprint poll.
        all_files = list(
            {m.relative_path for m in metas.values() if m.relative_path}
            | set(cache.get_cached_file_paths())
            | set(_go_analysis_paths(repo_path))
            | set(_dart_analysis_paths(repo_path))
            | set(_zig_analysis_paths(repo_path))
            | set(_lean_analysis_paths(repo_path))
        )
        if all_files:
            cache.update_file_fingerprints(all_files, session.analyzed_commit or "")
        deleted_paths = [
            path
            for path in (changes_info or {}).get("changed_files", [])
            if path and not (repo_path / path).exists()
        ]
        cache.remove_file_fingerprints(deleted_paths)
    except Exception as e:
        logger.warning("Fingerprint update failed: %s", e)

    # Release source_code from memory
    for node in components.values():
        node.source_code = None

    # -- MCP response --
    from codewiki.mcp.tools.artifact_facts import artifact_facts_path

    artifact_file = str(artifact_facts_path(repo_path, output_dir)).replace(os.sep, "/")
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
            "artifact_facts": artifact_file,
        },
        "artifact_facts": artifact_facts,
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
    if job_summary is not None:
        result["job"] = job_summary
    if changes_info and not changes_info.get("no_changes"):
        result["hint"] = (
            "Incremental update detected. Only update affected modules. "
            + changes_info.get("hint", "")
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def _go_analysis_paths(repo_path: Path) -> list[str]:
    """返回 Go module 语义依赖，确保 manifest-only 变化可被指纹检测。"""
    paths: list[str] = []
    for directory, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and name not in {"node_modules", "vendor", "testdata"}
        ]
        for filename in filenames:
            if filename != "go.mod":
                continue
            path = Path(directory, filename)
            try:
                paths.append(path.relative_to(repo_path).as_posix())
            except ValueError:
                continue
    return paths


def _dart_analysis_paths(repo_path: Path) -> list[str]:
    """返回 Dart 源码与 package 语义依赖，包含无组件的 directive-only 文件。"""
    paths: list[str] = []
    for directory, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and name not in {"node_modules", "build", ".dart_tool"}
        ]
        for filename in filenames:
            if filename == "pubspec.yaml" or (
                filename.endswith(".dart")
                and not filename.endswith((".g.dart", ".freezed.dart", ".gen.dart"))
            ):
                path = Path(directory, filename)
                try:
                    paths.append(path.relative_to(repo_path).as_posix())
                except ValueError:
                    continue
    return paths


def _zig_analysis_paths(repo_path: Path) -> list[str]:
    """返回参与 Zig 语义分析的源码，包含无组件的 import/re-export 文件。"""
    from codewiki.src.be.dependency_analyzer.analyzers.zig import is_skipped_zig_file

    paths: list[str] = []
    for directory, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".")
            and name not in {"node_modules", ".zig-cache", "zig-cache", "zig-out"}
        ]
        for filename in filenames:
            if not filename.endswith(".zig"):
                continue
            path = Path(directory, filename)
            relative = path.relative_to(repo_path).as_posix()
            if not is_skipped_zig_file(relative):
                paths.append(relative)
    return paths


def _lean_analysis_paths(repo_path: Path) -> list[str]:
    """返回参与 Lean 可见域分析的源码，包含无组件的 import-only 文件。"""
    from codewiki.src.be.dependency_analyzer.analyzers.lean import is_skipped_lean_file

    paths: list[str] = []
    for directory, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and name not in {"node_modules", ".lake", "lake-packages"}
        ]
        for filename in filenames:
            if not filename.endswith(".lean"):
                continue
            path = Path(directory, filename)
            relative = path.relative_to(repo_path).as_posix()
            if not is_skipped_lean_file(relative):
                paths.append(relative)
    return paths


def _build_no_change_response(
    repo_path: Path,
    output_dir: Path,
    store: SessionStore,
    cache: AnalysisCache,
    changes_info: Dict,
    *,
    artifact_facts: Dict[str, Any] | None = None,
) -> str:
    """Build session from cached data when no changes are detected."""
    if artifact_facts is None:
        artifact_facts = _collect_artifact_facts(
            repo_path,
            output_dir,
            include_patterns=None,
            exclude_patterns=None,
        )
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
    # 本次 fresh analyze 即使无代码变更，也拥有权威的空 diff；与仅从缓存
    # 恢复的查询会话不同，它仍可显式 apply 树修复。
    session.component_changes = {"added": [], "deleted": [], "renamed": []}
    from codewiki.cli.utils.repo_validator import get_git_commit_hash

    session.analyzed_commit = get_git_commit_hash(repo_path) or None

    workspace = SessionWorkspace(repo_path, session.session_id)
    session.workspace = workspace
    SessionWorkspace.cleanup_legacy_sessions(repo_path)

    langs: dict[str, int] = {}
    for m in metas.values():
        lang = (m.language or "").strip()
        if not lang or lang.lower() in ("null", "none", "unknown"):
            lang = "unknown"
        langs[lang] = langs.get(lang, 0) + 1
    # D2 stale_pages enriches here too (fingerprint drift may exist with no
    # code change), but the D1 evidence signal stays SILENT on this path
    # (ADR-0005): no_changes means "code didn't move" — evidence drift then
    # waits for an explicit lint_wiki(checks=["stale_evidence"]).
    _enrich_stale_pages(changes_info, output_dir)
    changes_info = _enrich_referencing_pages(
        changes_info,
        repo_path,
        output_dir,
        components=metas,
        cache=cache,
    )
    changes_info = _enrich_ownership(
        changes_info,
        repo_path,
        output_dir,
        components=metas,
    )
    changes_info = _enrich_tree_repair(
        changes_info,
        repo_path,
        output_dir,
        components=metas,
        component_changes=session.component_changes,
        tracked_component_ids=leaf_nodes,
    )
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
        "artifact_facts": artifact_facts["summary"],
    }
    job_summary = job_state.job_summary(job_state.load_job(repo_path, output_dir))
    if job_summary is not None:
        summary["job"] = job_summary
    workspace.write_json("summary.json", summary)

    from codewiki.mcp.tools.artifact_facts import artifact_facts_path

    response = {
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
            "summary": str(workspace.root / "summary.json").replace(os.sep, "/"),
            "artifact_facts": str(artifact_facts_path(repo_path, output_dir)).replace(os.sep, "/"),
        },
        "artifact_facts": artifact_facts,
        "changes": changes_info,
        "cache_mode": "sqlite",
        "hint": (
            "No changes detected since last analysis. Documentation is up to date."
            if artifact_facts.get("status") == "ok"
            else "No source changes detected since last analysis. Artifact facts are partial or "
            "unavailable; review artifact_facts.status, warnings, failures and omissions before "
            "treating build/deploy documentation as current."
        ),
    }
    if job_summary is not None:
        response["job"] = job_summary
    return json.dumps(response, indent=2, ensure_ascii=False)


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

        from codewiki.src.store import atomic_write

        links_data = [link.model_dump() for link in topology.links]
        atomic_write(
            meta_dir / "cross_service_links.json",
            json.dumps(links_data, ensure_ascii=False, indent=2),
        )
        routes_data = [route.model_dump() for route in topology.routes]
        atomic_write(
            meta_dir / "workspace_routes.json",
            json.dumps(routes_data, ensure_ascii=False, indent=2),
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
            from codewiki.src.store import atomic_write

            atomic_write(
                meta_dir / "infra_services.json",
                json.dumps(infra_data, ensure_ascii=False, indent=2),
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


def _enrich_stale_pages(
    changes_info: Optional[Dict[str, Any]], output_dir: Path
) -> Optional[Dict[str, Any]]:
    """Merge D2 page-manifest ``stale_pages`` into *changes_info* in place.

    Single post-step so both the SQLite incremental path
    (:meth:`AnalysisCache.detect_changes`) and the legacy JSON fallback
    (:func:`_detect_doc_changes`) emit ``stale_pages`` uniformly — the drift
    signal for shared-pool pages must not depend on which change source ran.
    """
    if not isinstance(changes_info, dict):
        return changes_info
    from codewiki.mcp.tools.page_manifest import detect_stale_pages

    cf = changes_info.get("changed_files") or []
    stale = detect_stale_pages(output_dir, cf)
    if stale:
        changes_info["stale_pages"] = sorted(stale)
    return changes_info


@overload
def _enrich_referencing_pages(
    changes_info: Dict[str, Any],
    repo_path: Path,
    output_dir: Path,
    *,
    components: Dict[str, Any],
    previous_components: Optional[Dict[str, Any]] = None,
    cache: AnalysisCache,
) -> Dict[str, Any]: ...


@overload
def _enrich_referencing_pages(
    changes_info: None,
    repo_path: Path,
    output_dir: Path,
    *,
    components: Dict[str, Any],
    previous_components: Optional[Dict[str, Any]] = None,
    cache: AnalysisCache,
) -> None: ...


def _enrich_referencing_pages(
    changes_info: Optional[Dict[str, Any]],
    repo_path: Path,
    output_dir: Path,
    *,
    components: Dict[str, Any],
    previous_components: Optional[Dict[str, Any]] = None,
    cache: AnalysisCache,
) -> Optional[Dict[str, Any]]:
    """附加反向引用信息，不改变文档正文。"""
    if not isinstance(changes_info, dict):
        return changes_info
    try:
        from codewiki.mcp.tools.reference_index import rebuild_index, referencing_pages

        path, index = rebuild_index(
            repo_path,
            output_dir,
            components,
            previous_components=previous_components,
            historical_symbols=cache.get_reference_symbols(),
        )
        cache.save_reference_symbols(index["symbols"])
        component_changes = changes_info.setdefault(
            "component_changes", {"added": [], "deleted": [], "renamed": []}
        )
        deleted = component_changes.get("deleted") or []
        renamed = component_changes.get("renamed") or []
        targets = set(deleted)
        targets.update(
            str(item.get("from")) for item in renamed if isinstance(item, dict) and item.get("from")
        )
        changes_info["referencing_pages"] = referencing_pages(
            index,
            component_ids=targets,
            page_keys=changes_info.get("deleted_pages") or [],
        )
        changes_info["reference_index_file"] = str(path).replace(os.sep, "/")
    except Exception:
        logger.warning("reference index build failed (non-fatal)", exc_info=True)
    return changes_info


def _load_incremental_module_tree(
    repo_path: Path, output_dir: Path
) -> tuple[dict[str, Any] | None, str, str | None]:
    """统一加载增量诊断使用的模块树，并显式区分缺失与损坏。"""
    tree_path = resolve_analysis_meta_file(repo_path, output_dir, "module_tree.json")
    if not tree_path.exists():
        return None, "missing", None
    try:
        module_tree = json.loads(tree_path.read_text(encoding="utf-8"))
        if not isinstance(module_tree, dict):
            raise ValueError("module tree root must be an object")
        return module_tree, "loaded", None
    except (OSError, ValueError, TypeError) as exc:
        return None, "invalid", str(exc)


def _enrich_ownership(
    changes_info: Dict[str, Any],
    repo_path: Path,
    output_dir: Path,
    *,
    components: Dict[str, Any],
    previous_components: Optional[Dict[str, Any]] = None,
    changed_components: Optional[Dict[str, Any]] = None,
    deleted_component_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """附加确定性 owner 候选；模块树缺失或损坏时不阻断分析。"""
    from codewiki.mcp.tools.ownership import close_ownership

    changed = changed_components or {}
    deleted = deleted_component_ids or []
    module_tree, status, warning = _load_incremental_module_tree(repo_path, output_dir)
    try:
        result = close_ownership(
            module_tree or {},
            components,
            previous_components=previous_components,
            changed_component_ids=changed,
            deleted_component_ids=deleted,
        )
    except (OSError, ValueError, TypeError) as exc:
        status, warning = "invalid", str(exc)
        result = close_ownership(
            {},
            components,
            previous_components=previous_components,
            changed_component_ids=changed,
            deleted_component_ids=deleted,
        )
    changes_info.update(result)
    changes_info["ownership_tree_status"] = status
    if warning:
        changes_info["ownership_warning"] = warning
        logger.warning("module tree load failed (ownership unresolved): %s", warning)
    return changes_info


def _enrich_tree_repair(
    changes_info: Dict[str, Any],
    repo_path: Path,
    output_dir: Path,
    *,
    components: Dict[str, Any],
    component_changes: Dict[str, Any],
    tracked_component_ids: List[str],
) -> Dict[str, Any]:
    """附加 B3 observe 修复计划，不修改磁盘上的模块树。"""
    from codewiki.mcp.tools.tree_repair import repair_module_tree

    module_tree, status, warning = _load_incremental_module_tree(repo_path, output_dir)
    try:
        plan = repair_module_tree(
            module_tree or {},
            components,
            component_changes=component_changes,
            tracked_component_ids=tracked_component_ids,
        )
    except (OSError, ValueError, TypeError) as exc:
        status, warning = "invalid", str(exc)
        plan = repair_module_tree(
            {},
            components,
            component_changes=component_changes,
            tracked_component_ids=tracked_component_ids,
        )
    if warning:
        plan["warnings"].append(warning)
    changes_info["tree_repair"] = plan
    changes_info["tree_repair_status"] = status
    if warning:
        changes_info["tree_repair_warning"] = warning
        logger.warning("module tree load failed (tree repair unavailable): %s", warning)
    return changes_info


def _enrich_stale_evidence(
    changes_info: Optional[Dict[str, Any]], output_dir: Path
) -> Optional[Dict[str, Any]]:
    """Merge D1 evidence-drift signal into *changes_info* in place (B6).

    Third drift signal alongside ``affected_modules`` (git-diff driven) and
    ``stale_pages`` (D2 manifest driven): pages whose ``repo://`` evidence no
    longer verifies get a page-level status summary in
    ``changes_info["stale_evidence_pages"]``.  Semantics differ from
    ``stale_pages`` (file-level change) — the two fields coexist without
    dedup; a page hit by both signals is honestly double-reported.

    Only the changed-code path enriches.  The ``no_changes`` short-circuit
    stays silent by design (ADR-0005): drift there waits for an explicit
    ``lint_wiki(checks=["stale_evidence"])``.

    The signal drives review, never rewriting: the hint guides the agent to
    re-verify claims and re-stamp evidence that still holds, not to blind-
    regenerate pages (evidence drift may be relocation, not semantic change).
    """
    if not isinstance(changes_info, dict):
        return changes_info
    if changes_info.get("no_changes"):
        return changes_info
    from codewiki.mcp.tools.evidence import collect_evidence_drift

    drift = collect_evidence_drift(output_dir)
    if not drift:
        return changes_info

    pages: Dict[str, Dict[str, int]] = {}
    for record in drift:
        counts = pages.setdefault(record["file"], {"stale": 0, "missing": 0, "unresolvable": 0})
        counts[record["status"]] += 1
    changes_info["stale_evidence_pages"] = {
        page: {k: v for k, v in counts.items() if v} for page, counts in sorted(pages.items())
    }
    total = sum(sum(c.values()) for c in changes_info["stale_evidence_pages"].values())
    changes_info["hint"] = (
        changes_info.get("hint", "")
        + f" {total} evidence entr{'y' if total == 1 else 'ies'} drifted across "
        f"{len(changes_info['stale_evidence_pages'])} page(s) — review whether the "
        "claims still hold: re-stamp evidence that does (stamp_evidence), correct "
        "pages that do not. Detail: lint_wiki(checks=['stale_evidence'])."
    )
    return changes_info


def _detect_doc_changes(
    repo_path: Path,
    output_dir: Path,
    components: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Detect documentation-level changes since last generation (legacy JSON fallback)."""
    from codewiki.mcp.cache import resolve_analysis_meta_file

    mp = resolve_analysis_meta_file(repo_path, output_dir, "metadata.json")
    mtp = resolve_analysis_meta_file(repo_path, output_dir, "module_tree.json")
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


def _current_head(repo_path: Path) -> Optional[str]:
    """HEAD sha of the repo's own git, or None when git is unavailable."""
    try:
        import git

        return git.Repo(repo_path).head.commit.hexsha
    except Exception:
        return None


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
        ".rb",
        ".scala",
        ".sc",
        ".dart",
        ".zig",
        ".lean",
        ".vue",
    }
    ch = []
    for dp, dns, fns in os.walk(repo_path):
        dns[:] = [
            d
            for d in dns
            if not d.startswith(".")
            and d
            not in (
                "node_modules",
                "__pycache__",
                "venv",
                ".venv",
                "zig-cache",
                "zig-out",
                ".lake",
                "lake-packages",
            )
        ]
        for fn in fns:
            fp = Path(dp) / fn
            if fn not in {"go.mod", "pubspec.yaml"} and fp.suffix.lower() not in exts:
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
    from codewiki.src.store import atomic_write

    refs_path = meta_dir / "overview_refs.json"
    atomic_write(refs_path, json.dumps(sorted(refs), ensure_ascii=False, indent=2))


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
