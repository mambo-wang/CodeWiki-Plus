"""MCP tool: read_code_components — write component source code to disk.

Instead of transmitting source code through the MCP stdio channel (which
required aggressive truncation), this tool writes complete, untruncated
source files to the session workspace.  The IDE agent then reads them
directly from disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)


def _read_source_from_disk(node) -> str:
    """Re-read component source from the original file using line range."""
    file_path = getattr(node, "file_path", "")
    start_line = getattr(node, "start_line", 0)
    end_line = getattr(node, "end_line", 0)
    if not file_path:
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if start_line > 0 and end_line > 0:
            # Lines are 1-indexed in the Node model
            selected = lines[max(0, start_line - 1):end_line]
            return "".join(selected)
        # Fallback: return full file if line range is missing
        return "".join(lines)
    except Exception as e:
        logger.warning("Failed to read source for %s: %s", file_path, e)
        return ""


def handle_read_code_components(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Write the source code for given component IDs to workspace files.

    Returns a compact JSON with file paths — no source code inline.
    """
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    if session.workspace is None:
        return json.dumps({"error": "Session workspace not initialized."})

    component_ids: List[str] = arguments["component_ids"]
    components = session.components
    workspace = session.workspace

    written_files: Dict[str, str] = {}  # filename -> component_id
    not_found: List[str] = []

    for cid in component_ids:
        node = components.get(cid)
        if node is None:
            not_found.append(cid)
            continue
        lang = getattr(node, "language", "")
        source = getattr(node, "source_code", None)
        if not source:
            # Source code was released from memory; re-read from disk
            source = _read_source_from_disk(node)
        source = source.strip()
        file_path = workspace.write_component_source(cid, source, lang)
        written_files[file_path.name] = cid

    result = {
        "written": len(written_files),
        "not_found_count": len(not_found),
        "not_found": not_found,
        "source_dir": str(workspace.root / "sources"),
        "files": written_files,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)
