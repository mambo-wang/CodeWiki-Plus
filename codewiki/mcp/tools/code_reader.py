"""MCP tools: read_code_components + view_repo_file.

These are read-only tools that let the IDE agent explore source code
within the analyzed repository.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)

# Truncation guard for very large responses
_MAX_RESPONSE_LEN = 32000


def _maybe_truncate(text: str, limit: int = _MAX_RESPONSE_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n<response clipped — use view_repo_file with view_range to read more>"


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
            results.append(f"## {cid} ({getattr(node, 'component_type', '')})\n```{fence}\n{code}\n```\n")

    output = "\n".join(results)
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
    abs_path = Path(session.repo_path) / rel_path

    if not abs_path.exists():
        return json.dumps({"error": f"Path not found: {rel_path}"})

    # Directory listing
    if abs_path.is_dir():
        out = subprocess.run(
            rf"find {abs_path} -maxdepth 2 -not -path '*/\.*'",
            shell=True,
            capture_output=True,
        )
        listing = out.stdout.decode("utf-8", errors="replace")
        listing = listing.replace(str(abs_path), rel_path)
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
