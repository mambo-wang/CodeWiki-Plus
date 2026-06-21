"""MCP tool: analyze_repo — parse a repository and build the dependency graph.

This is the entry-point tool for the IDE-driven wiki generation pipeline.
It runs CodeWiki's Tree-sitter-based dependency analyzer (no LLM needed),
caches the results in a new session, and returns a component index the IDE
agent can use for clustering and documentation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


def _build_component_index(
    components: Dict[str, Any],
    offset: int = 0,
    limit: int = 100,
) -> Tuple[list, Dict[str, int]]:
    """Build a lightweight component index for the MCP response.

    Returns (index_list, pagination_info).  Each entry only carries *id*,
    *type*, and *file* — dependency details are available on demand via
    ``read_code_components``.
    """
    all_ids = list(components.keys())
    total = len(all_ids)
    limit = min(max(limit, 1), 200)  # clamp to [1, 200]
    page_ids = all_ids[offset : offset + limit]
    index: list[dict] = []
    for comp_id in page_ids:
        node = components[comp_id]
        index.append({
            "id": comp_id,
            "type": getattr(node, "component_type", "unknown"),
            "file": getattr(node, "relative_path", ""),
        })
    pagination = {
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total,
    }
    return index, pagination


# ---------------------------------------------------------------------------
#  Incremental update: detect changes since last generation
# ---------------------------------------------------------------------------

def _detect_changes(
    repo_path: Path,
    output_dir: Path,
) -> Optional[Dict[str, Any]]:
    """Detect changes since last documentation generation.

    Returns a changes dict with affected modules, or None if no previous
    generation exists (first run).

    Detection strategy:
      1. Git-based: compare stored commit_id with current HEAD, plus check
         uncommitted changes via ``git status``.
      2. Fallback: compare file mtime with stored ``timestamp`` in metadata.
    """
    metadata_path = output_dir / "metadata.json"
    module_tree_path = output_dir / "module_tree.json"

    if not metadata_path.exists() or not module_tree_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text())
        module_tree = json.loads(module_tree_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Try git-based detection first
    changes = _detect_via_git(repo_path, metadata)

    # Fallback to mtime-based detection
    if changes is None:
        changes = _detect_via_mtime(repo_path, metadata)

    if changes is None:
        return None

    changed_files = changes["changed_files"]
    if not changed_files:
        return {
            "has_previous": True,
            "no_changes": True,
            "method": changes.get("method", "unknown"),
            "message": "No changes detected since last generation. Documentation is up to date.",
        }

    affected, cascade = _find_affected_modules(module_tree, changed_files)

    return {
        "has_previous": True,
        "no_changes": False,
        "method": changes.get("method", "unknown"),
        "changed_files": changed_files[:50],
        "affected_modules": sorted(affected),
        "cascade_modules": sorted(cascade),
        "hint": (
            f"Only {len(affected)} module(s) need updating: {sorted(affected)}. "
            f"Parent modules to refresh: {sorted(cascade)}. "
            "Use edit_doc_file for targeted updates, write_doc_file for new modules."
        ),
    }


def _detect_via_git(
    repo_path: Path,
    metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Detect changes via git. Returns None if not in a git repo.

    Checks both committed changes (diff against stored commit_id) and
    uncommitted changes (``git status``).
    """
    try:
        import git
        repo = git.Repo(repo_path, search_parent_directories=True)
    except Exception:
        return None

    prev_commit = metadata.get("generation_info", {}).get("commit_id")
    try:
        current_commit = repo.head.commit.hexsha
    except Exception:
        return None

    changed: list[str] = []
    method = "git"

    # 1) Committed changes since last generation
    if prev_commit and prev_commit != current_commit:
        try:
            diff_index = repo.commit(prev_commit).diff(current_commit)
            seen: set[str] = set()
            for diff in diff_index:
                if diff.a_path and diff.a_path not in seen:
                    changed.append(diff.a_path)
                    seen.add(diff.a_path)
                if diff.b_path and diff.b_path not in seen:
                    changed.append(diff.b_path)
                    seen.add(diff.b_path)
        except Exception:
            pass

    # 2) Uncommitted changes (user may have edited but not committed)
    try:
        for item in repo.untracked_files:
            if item not in changed:
                changed.append(item)
        for file_path in [d.a_path for d in repo.index.diff(None)]:
            if file_path and file_path not in changed:
                changed.append(file_path)
    except Exception:
        pass

    return {"changed_files": changed, "method": method}


def _detect_via_mtime(
    repo_path: Path,
    metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Fallback: detect changed files by comparing mtime with generation timestamp."""
    timestamp_str = metadata.get("generation_info", {}).get("timestamp")
    if not timestamp_str:
        return None

    try:
        from datetime import datetime
        prev_time = datetime.fromisoformat(timestamp_str).timestamp()
    except (ValueError, TypeError):
        return None

    # Language extensions recognized by CodeWiki
    source_extensions = {
        ".py", ".java", ".js", ".jsx", ".ts", ".tsx",
        ".c", ".h", ".cpp", ".hpp", ".cc", ".hh",
        ".cs", ".kt", ".kts",
    }

    changed: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Skip hidden dirs and common non-source dirs
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")
        ]
        for filename in filenames:
            filepath = Path(dirpath) / filename
            if filepath.suffix.lower() not in source_extensions:
                continue
            try:
                if filepath.stat().st_mtime > prev_time:
                    rel_path = str(filepath.relative_to(repo_path))
                    changed.append(rel_path)
            except OSError:
                continue

    return {"changed_files": changed, "method": "mtime"}


def _find_affected_modules(
    module_tree: Dict[str, Any],
    changed_files: List[str],
) -> Tuple[set, set]:
    """Map changed files to affected modules using module_tree.json.

    Uses substring matching (same as the CLI ``_invalidate_affected_modules``).
    Returns (affected_modules, cascade_parent_modules).
    """
    affected: set[str] = set()
    cascade: set[str] = set()

    def _walk(tree: Dict, parents: list[str] | None = None):
        if parents is None:
            parents = []
        for mod_name, mod_info in tree.items():
            components = mod_info.get("components", [])
            hit = False
            for comp in components:
                if any(cf in comp or comp in cf for cf in changed_files):
                    hit = True
                    break
            if hit:
                affected.add(mod_name)
                cascade.update(parents)

            children = mod_info.get("children", {})
            if isinstance(children, dict) and children:
                _walk(children, parents + [mod_name])

    _walk(module_tree)

    # overview.md depends on all child docs, always refresh if anything changed
    if affected:
        cascade.add("overview")

    return affected, cascade


def handle_analyze_repo(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Run the dependency analysis and return the session + component index."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        return json.dumps({"error": f"Repository not found: {repo_path}"})

    output_dir = Path(arguments.get("output_dir", str(repo_path / "docs"))).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build a minimal Config for the dependency analyzer (no LLM fields used)
    from codewiki.src.config import Config
    config = Config(
        repo_path=str(repo_path),
        output_dir=str(output_dir / "temp"),
        dependency_graph_dir=str(output_dir / "temp" / "dependency_graphs"),
        docs_dir=str(output_dir),
        max_depth=2,
        llm_base_url="not-needed",
        llm_api_key="not-needed",
        main_model="unused",
        cluster_model="unused",
    )

    # Apply optional include/exclude patterns
    include = arguments.get("include_patterns")
    exclude = arguments.get("exclude_patterns")
    if include or exclude:
        agent_instructions: Dict[str, Any] = {}
        if include:
            agent_instructions["include_patterns"] = [p.strip() for p in include.split(",")]
        if exclude:
            agent_instructions["exclude_patterns"] = [p.strip() for p in exclude.split(",")]
        config.agent_instructions = agent_instructions

    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    builder = DependencyGraphBuilder(config)
    components, leaf_nodes = builder.build_dependency_graph()

    session = store.create(
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        components=components,
        leaf_nodes=leaf_nodes,
    )

    # Pagination for the component index
    offset = int(arguments.get("offset", 0))
    limit = int(arguments.get("limit", 100))
    index, pagination = _build_component_index(components, offset=offset, limit=limit)

    # Language stats
    languages: Dict[str, int] = {}
    for node in components.values():
        lang = getattr(node, "language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1

    # Incremental update: detect changes since last generation
    changes = _detect_changes(repo_path, output_dir)

    result = {
        "session_id": session.session_id,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "output_dir": str(output_dir),
        "languages": languages,
        "total_components": len(components),
        "total_leaf_nodes": len(leaf_nodes),
        "leaf_nodes": leaf_nodes[:50],
        "component_index": index,
        "pagination": pagination,
        "changes": changes,
        "hint": (
            "Use read_code_components(session_id, component_ids) to read source code. "
            "Use save_module_tree(session_id, module_tree) after clustering. "
            "Call get_prompt('cluster') for clustering rules."
        ),
    }
    if pagination["has_more"]:
        result["hint"] += (
            f" Component index has {pagination['total']} items; "
            f"call analyze_repo again with offset={offset + limit} to see the next page."
        )
    if changes and not changes.get("no_changes"):
        result["hint"] = (
            "Incremental update detected. Only update affected modules listed in "
            "'changes.affected_modules'. Use edit_doc_file for targeted updates. "
            "Refresh cascade parent modules in 'changes.cascade_modules'."
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def handle_list_components(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return a paginated slice of the component index from an existing session."""
    session = store.get(arguments["session_id"])
    if session is None:
        return json.dumps({"error": "Session not found or expired."})

    offset = int(arguments.get("offset", 0))
    limit = int(arguments.get("limit", 100))
    index, pagination = _build_component_index(
        session.components, offset=offset, limit=limit,
    )

    result = {
        "session_id": session.session_id,
        "component_index": index,
        "pagination": pagination,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)
