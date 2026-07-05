"""MCP tool: view_repo_file — read files or list directories in the repo.

Lets the IDE agent read already-generated ``.md`` docs (for parent
module synthesis) or browse source files for extra context — all
through MCP without direct disk access.  Path-traversal safe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from codewiki.mcp.session import SessionStore

# If a file exceeds this many characters, write it to the session
# workspace and return the path instead of inlining the content.
_MAX_INLINE_CHARS = 50_000


def handle_view_repo_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Read a file or list a directory within the repository.

    Arguments
    ---------
    session_id : str (required)
        Session ID from ``analyze_repo``.
    path : str (required)
        Relative path from the repository root.  Can point to a file
        (content returned) or a directory (listing returned).
        ``repowiki/`` and other output dirs are accessible since they
        live under ``repo_path``.

    Returns
    -------
    For files:  ``{"path": ..., "type": "file", "content": ..., "size": N}``
    For dirs:   ``{"path": ..., "type": "directory", "entries": [...]}`
    For large files: ``{"path": ..., "type": "file", "workspace_file": ..., "size": N, "truncated": true}``
    """
    session_id = arguments.get("session_id", "")
    session = store.get(session_id)
    if session is None:
        return json.dumps(
            {"error": f"Session {session_id} not found or expired."},
            ensure_ascii=False,
        )

    rel_path = arguments.get("path", "")
    if not rel_path:
        return json.dumps(
            {"error": "Argument 'path' is required."},
            ensure_ascii=False,
        )

    repo_root = Path(session.repo_path).resolve()

    # Resolve the target and guard against path traversal.
    target = (repo_root / rel_path).resolve()
    try:
        target.relative_to(repo_root)
    except ValueError:
        return json.dumps(
            {"error": f"Path '{rel_path}' is outside the repository root."},
            ensure_ascii=False,
        )

    if not target.exists():
        return json.dumps(
            {"error": f"Path not found: {rel_path}"},
            ensure_ascii=False,
        )

    # --- Directory listing ---
    if target.is_dir():
        entries = []
        for item in sorted(target.iterdir()):
            try:
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": stat.st_size if item.is_file() else None,
                })
            except OSError:
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": None,
                })
        return json.dumps(
            {
                "path": rel_path,
                "type": "directory",
                "entries": entries,
            },
            indent=2,
            ensure_ascii=False,
        )

    # --- File read ---
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return json.dumps(
            {"error": f"Failed to read file {rel_path}: {exc}"},
            ensure_ascii=False,
        )

    size = len(content)

    # Large files: write to workspace and return the path.
    if size > _MAX_INLINE_CHARS:
        if session.workspace is not None:
            safe_name = (
                rel_path.replace("/", "__").replace("\\", "__")[:180]
            )
            ws_path = session.workspace.root / f"view_{safe_name}"
            ws_path.write_text(content, encoding="utf-8")
            return json.dumps(
                {
                    "path": rel_path,
                    "type": "file",
                    "workspace_file": str(ws_path),
                    "size": size,
                    "truncated": True,
                },
                ensure_ascii=False,
            )
        # No workspace — return truncated content with a notice.
        return json.dumps(
            {
                "path": rel_path,
                "type": "file",
                "content": content[:_MAX_INLINE_CHARS],
                "size": size,
                "truncated": True,
                "notice": "Content truncated (no workspace available).",
            },
            indent=2,
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "path": rel_path,
            "type": "file",
            "content": content,
            "size": size,
        },
        indent=2,
        ensure_ascii=False,
    )
