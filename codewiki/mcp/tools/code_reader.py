"""MCP tools: read_code_components + view_repo_file.

These are read-only tools that let the IDE agent explore source code
within the analyzed repository.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)

# Truncation guard for very large responses (leave room for LLM output)
_MAX_RESPONSE_LEN = 24000

# Max components per read_code_components call
_MAX_COMPONENTS_PER_CALL = 20

# Max chars of source code per component (large files truncated)
_MAX_COMPONENT_SOURCE_LEN = 8000


def _maybe_truncate(text: str, limit: int = _MAX_RESPONSE_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n<response clipped — use view_repo_file with view_range to read more>"


def _is_within(path: Path, base: Path) -> bool:
    """Return True if *path* resolves to somewhere inside *base*."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def handle_read_code_components(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return the source code for a list of component IDs."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    component_ids: List[str] = arguments["component_ids"]
    # Cap the number of components to avoid oversized responses
    if len(component_ids) > _MAX_COMPONENTS_PER_CALL:
        component_ids = component_ids[:_MAX_COMPONENTS_PER_CALL]

    components = session.components
    results = []
    for cid in component_ids:
        node = components.get(cid)
        if node is None:
            results.append(f"# Component {cid} not found\n")
        else:
            lang = getattr(node, "language", "")
            fence = lang if lang else ""
            code = getattr(node, "source_code", "").strip()
            if len(code) > _MAX_COMPONENT_SOURCE_LEN:
                code = code[:_MAX_COMPONENT_SOURCE_LEN] + (
                    f"\n\n... <truncated {len(code) - _MAX_COMPONENT_SOURCE_LEN} chars; "
                    f"use view_repo_file to read the full source>"
                )
            results.append(f"## {cid} ({getattr(node, 'component_type', '')})\n```{fence}\n{code}\n```\n")

    output = "\n".join(results)
    if len(arguments["component_ids"]) > _MAX_COMPONENTS_PER_CALL:
        output = f"<only first {_MAX_COMPONENTS_PER_CALL} components shown; call again with the remaining IDs>\n\n" + output
    return _maybe_truncate(output)


def handle_view_repo_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Read-only view of a file or directory inside the repository."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    rel_path = arguments["path"]
    repo_base = Path(session.repo_path).resolve()
    abs_path = (repo_base / rel_path).resolve()

    # Path traversal guard
    if not _is_within(abs_path, repo_base):
        return json.dumps({"error": "Path escapes repository directory."})

    if not abs_path.exists():
        return json.dumps({"error": f"Path not found: {rel_path}"})

    # Directory listing — use pathlib instead of shelling out
    if abs_path.is_dir():
        entries: list[str] = []
        for child in sorted(abs_path.iterdir()):
            if child.name.startswith("."):
                continue
            rel_child = child.relative_to(repo_base)
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{rel_child}{suffix}")
        # Also list one level deeper if there aren't too many entries
        if len(entries) <= 50:
            expanded: list[str] = []
            for child in sorted(abs_path.iterdir()):
                if child.name.startswith("."):
                    continue
                rel_child = child.relative_to(repo_base)
                suffix = "/" if child.is_dir() else ""
                expanded.append(f"{rel_child}{suffix}")
                if child.is_dir():
                    for sub in sorted(child.iterdir()):
                        if sub.name.startswith("."):
                            continue
                        rel_sub = sub.relative_to(repo_base)
                        sub_suffix = "/" if sub.is_dir() else ""
                        expanded.append(f"  {rel_sub}{sub_suffix}")
            entries = expanded
        listing = "\n".join(entries)
        return f"Directory listing for {rel_path}:\n{listing}"

    # File view
    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return json.dumps({"error": f"Cannot read file: {e}"})

    view_range = arguments.get("view_range")
    lines = content.split("\n")

    if view_range:
        if len(view_range) != 2:
            return json.dumps({"error": "view_range must be [start, end]"})
        start, end = view_range
        start = max(1, min(start, len(lines)))
        if end == -1:
            end = len(lines)
        end = max(start, min(end, len(lines)))
        selected = lines[start - 1 : end]
        numbered = "\n".join(f"{i + start:6}\t{line}" for i, line in enumerate(selected))
        return f"File: {rel_path} (lines {start}-{end})\n{numbered}"

    numbered = "\n".join(f"{i + 1:6}\t{line}" for i, line in enumerate(lines))
    return _maybe_truncate(f"File: {rel_path} ({len(lines)} lines)\n{numbered}")
