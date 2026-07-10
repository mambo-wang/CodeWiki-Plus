"""MCP tool: read_code_components — write component source code to disk.

Works with LazyComponentStore: .get(cid) lazy-loads a Node from SQLite,
then re-reads source_code from disk if not in memory.
"""

from __future__ import annotations

import json, logging
from pathlib import Path
from typing import Any, Dict, List

from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)


def _read_source_from_disk(node) -> str:
    file_path = getattr(node, "file_path", "")
    start_line = getattr(node, "start_line", 0)
    end_line = getattr(node, "end_line", 0)
    if not file_path: return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if start_line > 0 and end_line > 0:
            return "".join(lines[max(0, start_line - 1):end_line])
        return "".join(lines)
    except Exception as e:
        logger.warning("Failed to read source for %s: %s", file_path, e)
        return ""


def handle_read_code_components(
    arguments: Dict[str, Any], store: SessionStore,
) -> str:
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})
    if session.workspace is None:
        return json.dumps({"error": "Session workspace not initialized."})

    component_ids: List[str] = arguments["component_ids"]
    workspace = session.workspace
    components = session.components  # LazyComponentStore

    written_files: Dict[str, str] = {}
    not_found: List[str] = []

    for cid in component_ids:
        node = components.get(cid)
        if node is None:
            not_found.append(cid); continue
        lang = getattr(node, "language", "")
        source = getattr(node, "source_code", None)
        if not source:
            source = _read_source_from_disk(node)
        source = source.strip()
        fp = workspace.write_component_source(cid, source, lang)
        written_files[fp.name] = cid

    return json.dumps({
        "written": len(written_files),
        "not_found_count": len(not_found), "not_found": not_found,
        "source_dir": str(workspace.root / "sources"),
        "files": written_files,
    }, indent=2, ensure_ascii=False)
