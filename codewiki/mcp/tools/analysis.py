"""MCP tool: analyze_repo — parse a repository and build the dependency graph.

This is the entry-point tool for the IDE-driven wiki generation pipeline.
It runs CodeWiki's Tree-sitter-based dependency analyzer (no LLM needed),
caches results in SQLite and creates a new session with lazy-loaded components.

Incremental mode: on subsequent calls, detects changed files via Git (commit
diff + staged + unstaged/untracked) or file fingerprints, and only re-parses
changed files.
"""

from __future__ import annotations

import json, logging, os
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.cache import AnalysisCache, ComponentMeta, LazyComponentStore
from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.workspace import SessionWorkspace

logger = logging.getLogger(__name__)


def _read_source_from_disk(node) -> str:
    """Re-read component source from the original file using line range."""
    fp = getattr(node, "file_path", "")
    sl = getattr(node, "start_line", 0); el = getattr(node, "end_line", 0)
    if not fp: return ""
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if sl > 0 and el > 0: return "".join(lines[max(0, sl - 1):el])
        return "".join(lines)
    except Exception as e:
        logger.warning("Failed to read source for %s: %s", fp, e); return ""


def handle_analyze_repo(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Run dependency analysis, cache to SQLite, create session with lazy store."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        return json.dumps({"error": f"Repository not found: {repo_path}"})

    output_dir = Path(arguments.get("output_dir", str(repo_path / "docs"))).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    import tempfile
    from codewiki.src.config import Config
    # Use a temp dir for the legacy JSON output — we write to SQLite instead
    _tmp = Path(tempfile.mkdtemp(prefix="codewiki_"))
    config = Config(
        repo_path=str(repo_path), output_dir=str(_tmp),
        dependency_graph_dir=str(_tmp / "dependency_graphs"),
        docs_dir=str(output_dir), max_depth=2,
        llm_base_url="not-needed", llm_api_key="not-needed",
        main_model="unused", cluster_model="unused",
    )

    include = arguments.get("include_patterns"); exclude = arguments.get("exclude_patterns")
    if include or exclude:
        ai: Dict[str, Any] = {}
        if include: ai["include_patterns"] = [p.strip() for p in include.split(",")]
        if exclude: ai["exclude_patterns"] = [p.strip() for p in exclude.split(",")]
        config.agent_instructions = ai

    # Get or create shared cache for this repo
    cache = store.get_cache(str(repo_path))

    # Incremental check
    incremental = arguments.get("incremental", True)
    changes_info = None

    if incremental and cache.is_fresh():
        changes_info = cache.detect_changes()
        if changes_info and changes_info.get("no_changes"):
            # No changes — reuse cached data
            return _build_no_change_response(repo_path, output_dir, store, cache, changes_info)
        if changes_info and changes_info.get("changed_files"):
            changed = changes_info["changed_files"]
            logger.info("Incremental mode: %d files changed", len(changed))
            # Remove stale components
            for cf in changed:
                cache.remove_by_file(cf)
            # We'll do a full re-parse on the remaining + changed files.
            # For simplicity: do full re-parse (Tree-sitter is fast per-file
            # but incremental file-level parsing requires filtering the parser input).
            # TODO: pass changed_files to DependencyParser for selective re-parse.

    # Full parse (writes legacy JSONs to _tmp — clean up afterwards)
    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    import shutil
    builder = DependencyGraphBuilder(config)
    try:
        components, leaf_nodes = builder.build_dependency_graph()
    finally:
        shutil.rmtree(str(_tmp), ignore_errors=True)

    # Write to SQLite cache
    try:
        cache.batch_insert_components(components, leaf_nodes)
        logger.info("Components cached to SQLite")
    except Exception as e:
        logger.warning("SQLite cache write failed (continuing in memory): %s", e)

    # Build LazyComponentStore from ComponentMeta
    metas: Dict[str, ComponentMeta] = {}
    for comp_id, node in components.items():
        metas[comp_id] = ComponentMeta(
            id=node.id, name=node.name, component_type=node.component_type,
            file_path=node.file_path, relative_path=node.relative_path,
            start_line=node.start_line, end_line=node.end_line,
            language=(node.language or "").strip() or "unknown", depends_on=node.depends_on,
            node_type=node.node_type, base_classes=node.base_classes,
            class_name=node.class_name, display_name=node.display_name,
            qualified_name=node.qualified_name, has_docstring=node.has_docstring,
            parameters=node.parameters,
        )
    lazy_store = LazyComponentStore(cache, metas)

    # Create session
    session = store.create(
        repo_path=str(repo_path), output_dir=str(output_dir),
        components=lazy_store, leaf_nodes=leaf_nodes, cache=cache,
    )

    # Record analyzed commit
    from codewiki.cli.utils.repo_validator import get_git_commit_hash
    session.analyzed_commit = get_git_commit_hash(repo_path) or None
    if session.analyzed_commit:
        cache.set_last_commit_id(session.analyzed_commit)

    # Create workspace
    workspace = SessionWorkspace(repo_path, session.session_id)
    session.workspace = workspace

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
        changes_info = _detect_doc_changes(repo_path, output_dir)
    if changes_info is not None:
        workspace.write_json("changes.json", changes_info)

    # 5. Summary
    summary = {"session_id": session.session_id, "repo_name": repo_path.name,
               "repo_path": str(repo_path), "output_dir": str(output_dir),
               "total_components": len(metas), "total_leaf_nodes": len(leaf_nodes),
               "languages": langs, "leaf_nodes_preview": leaf_nodes[:20]}
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
                if isinstance(mt, dict): module_names = list(mt.keys())
            except Exception: pass
        # schema_generator needs a dict; pass the lazy store (works for len() and iteration)
        schema_info = generate_schema(repo_path.name, metas, list(langs.keys()), output_dir, module_names)
        workspace.write_json("schema.json", schema_info)
    except Exception as e:
        logger.warning("Schema generation skipped: %s", e)

    # 7. Index/log
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(str(output_dir), "analyze_repo", f"分析仓库 {repo_path.name}，{len(metas)} 个组件")
        rebuild_index(str(output_dir))
    except Exception as e:
        logger.warning("Index/log update failed: %s", e)

    # 8. Symbol map (class name → source file, used by ingest_note for crosslinking)
    try:
        symbol_map = _build_symbol_map(metas)
        from codewiki.src.config import meta_join
        meta_dir = Path(meta_join(output_dir, ""))
        meta_dir.mkdir(parents=True, exist_ok=True)
        symbol_map_path = Path(meta_join(output_dir, "symbol_map.json"))
        symbol_map_path.write_text(
            json.dumps(symbol_map, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Symbol map written: %d symbols", len(symbol_map))
    except Exception as e:
        logger.warning("Symbol map generation failed (non-fatal): %s", e)

    # 9. Update file fingerprints for incremental next run
    try:
        all_files = list({m.file_path for m in metas.values() if m.file_path})
        if all_files:
            cache.update_file_fingerprints(all_files, session.analyzed_commit or "")
    except Exception as e:
        logger.warning("Fingerprint update failed: %s", e)

    # Release source_code from memory
    for node in components.values(): node.source_code = None

    # -- MCP response --
    result = {
        "session_id": session.session_id,
        "workspace_dir": str(workspace.root),
        "repo_name": repo_path.name, "output_dir": str(output_dir),
        "stats": {"total_components": len(metas), "total_leaf_nodes": len(leaf_nodes), "languages": langs},
        "files": {
            "summary": str(workspace.root / "summary.json"),
            "schema": str(workspace.root / "schema.json") if schema_info else None,
        },
        "changes": changes_info,
        "cache_mode": "sqlite",
        "hint": (
            "Read the files above for full data. "
            "Use read_code_components(session_id, component_ids) to read source code. "
            "Use save_module_tree(session_id, module_tree) after clustering. "
            "Call get_prompt('cluster') for clustering rules."
        ),
    }
    if changes_info and not changes_info.get("no_changes"):
        result["hint"] = (
            "Incremental update detected. Only update affected modules. "
            + changes_info.get("hint", ""))
    return json.dumps(result, indent=2, ensure_ascii=False)


def _build_no_change_response(
    repo_path: Path, output_dir: Path, store: SessionStore,
    cache: AnalysisCache, changes_info: Dict,
) -> str:
    """Build session from cached data when no changes are detected."""
    metas = cache.get_all_metas()
    leaf_nodes = cache.get_leaf_nodes()
    lazy_store = LazyComponentStore(cache, metas)

    session = store.create(
        repo_path=str(repo_path), output_dir=str(output_dir),
        components=lazy_store, leaf_nodes=leaf_nodes, cache=cache,
    )
    from codewiki.cli.utils.repo_validator import get_git_commit_hash
    session.analyzed_commit = get_git_commit_hash(repo_path) or None

    workspace = SessionWorkspace(repo_path, session.session_id)
    session.workspace = workspace

    langs = {}
    for m in metas.values():
        lang = (m.language or "").strip()
        if not lang or lang.lower() in ("null", "none", "unknown"):
            lang = "unknown"
        langs[lang] = langs.get(lang, 0) + 1
    workspace.write_json("changes.json", changes_info)

    summary = {"session_id": session.session_id, "repo_name": repo_path.name,
               "repo_path": str(repo_path), "output_dir": str(output_dir),
               "total_components": len(metas), "total_leaf_nodes": len(leaf_nodes),
               "languages": langs, "leaf_nodes_preview": leaf_nodes[:20]}
    workspace.write_json("summary.json", summary)

    return json.dumps({
        "session_id": session.session_id,
        "workspace_dir": str(workspace.root),
        "repo_name": repo_path.name, "output_dir": str(output_dir),
        "stats": {"total_components": len(metas), "total_leaf_nodes": len(leaf_nodes), "languages": langs},
        "files": {
            "summary": str(workspace.root / "summary.json"),
        },
        "changes": changes_info,
        "cache_mode": "sqlite",
        "hint": "No changes detected since last analysis. Documentation is up to date.",
    }, indent=2, ensure_ascii=False)


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


def _detect_doc_changes(repo_path: Path, output_dir: Path) -> Optional[Dict[str, Any]]:
    """Detect documentation-level changes since last generation (legacy JSON fallback)."""
    from codewiki.src.config import meta_resolve
    mp = Path(meta_resolve(output_dir, "metadata.json"))
    mtp = Path(meta_resolve(output_dir, "module_tree.json"))
    if not mp.exists() or not mtp.exists(): return None
    try:
        md = json.loads(mp.read_text(encoding="utf-8"))
        mt = json.loads(mtp.read_text(encoding="utf-8"))
    except Exception: return None

    # Git detection from metadata.json
    changes = _detect_git_from_meta(repo_path, md, output_dir)
    if changes is None:
        changes = _detect_mtime_from_meta(repo_path, md)

    if changes is None: return None
    cf = changes["changed_files"]
    if not cf:
        return {"has_previous": True, "no_changes": True,
                "method": changes.get("method","unknown")}
    affected, cascade = _find_affected_modules(mt, cf)
    return {"has_previous": True, "no_changes": False,
            "method": changes.get("method","unknown"),
            "changed_files": cf, "affected_modules": sorted(affected),
            "cascade_modules": sorted(cascade),
            "hint": f"Only {len(affected)} module(s) need updating."}


def _detect_git_from_meta(repo_path: Path, metadata: Dict, output_dir: Path) -> Optional[Dict]:
    try:
        import git; repo = git.Repo(repo_path, search_parent_directories=True)
    except Exception: return None
    prev = metadata.get("generation_info", {}).get("commit_id")
    if not prev: return None
    try: cur = repo.head.commit.hexsha
    except Exception: return None
    git_root = Path(repo.working_dir).resolve()
    try: sp = repo_path.resolve().relative_to(git_root).as_posix()
    except ValueError: sp = ""
    if sp == ".": sp = ""

    od_rel = ""
    try:
        od_rel = Path(output_dir).resolve().relative_to(repo_path.resolve()).as_posix()
        if od_rel == ".": od_rel = ""
    except Exception: pass

    def _n(p: str) -> Optional[str]:
        if sp and not p.startswith(sp + "/"): return None
        p = p[len(sp)+1:] if sp else p
        if p.startswith(".codewiki/"): return None
        if od_rel and (p == od_rel or p.startswith(od_rel + "/")): return None
        return p

    ch, seen = [], set()
    def add(r): 
        if r and (p := _n(r)) and p not in seen: ch.append(p); seen.add(p)
    if prev != cur:
        try:
            for d in repo.commit(prev).diff(cur): add(d.a_path); add(d.b_path)
        except Exception:
            logger.warning("Commit %s unreachable", prev); return None
    try:
        for d in list(repo.index.diff("HEAD")) + list(repo.index.diff(None)):
            add(d.a_path); add(d.b_path)
        for item in repo.untracked_files: add(item)
    except Exception: pass
    return {"changed_files": ch, "method": "git"}


def _detect_mtime_from_meta(repo_path: Path, metadata: Dict) -> Optional[Dict]:
    ts = metadata.get("generation_info", {}).get("timestamp")
    if not ts: return None
    try:
        from datetime import datetime
        prev = datetime.fromisoformat(ts).timestamp()
    except Exception: return None
    exts = {".py",".java",".js",".jsx",".ts",".tsx",".c",".h",".cpp",".hpp",".cc",".hh",".cs",".kt",".kts"}
    ch = []
    for dp, dns, fns in os.walk(repo_path):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules","__pycache__","venv",".venv")]
        for fn in fns:
            fp = Path(dp) / fn
            if fp.suffix.lower() not in exts: continue
            try:
                if fp.stat().st_mtime > prev:
                    ch.append(fp.relative_to(repo_path).as_posix())
            except OSError: continue
    return {"changed_files": ch, "method": "mtime"}


def _find_affected_modules(module_tree: Dict, changed_files: List[str]):
    affected, cascade = set(), set()
    def _walk(tree, parents=None):
        if parents is None: parents = []
        for mn, mi in tree.items():
            comps = mi.get("components", [])
            hit = False
            for c in comps:
                cf = c.split("::")[0]
                for chf in changed_files:
                    if cf == chf or cf.endswith("/" + chf) or chf.endswith("/" + cf):
                        hit = True; break
                    if chf.startswith(cf + "/") or cf.startswith(chf + "/"):
                        hit = True; break
                if hit: break
            if hit:
                affected.add(mn); cascade.update(parents)
            children = mi.get("children", {})
            if isinstance(children, dict) and children: _walk(children, parents + [mn])
    _walk(module_tree)
    if affected: cascade.add("overview")
    return affected, cascade
