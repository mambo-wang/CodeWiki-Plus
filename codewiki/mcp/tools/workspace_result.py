"""Shared helper: write large result data to workspace files.

All MCP tools that may return >4KB of data should use this helper to
write the result to a session workspace file and return only the file
path through the MCP stdio channel.  This keeps the stdio channel lean.

Usage in a handler::

    from codewiki.mcp.tools.workspace_result import write_result

    result_data = {...}  # the full result dict/list
    response = write_result(session, "my_result.json", result_data,
                            summary={"total": len(items), "hint": "..."})
    return json.dumps(response, ensure_ascii=False)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Threshold in bytes: results larger than this are written to file.
_FILE_THRESHOLD = 4096


def write_result(
    session: Any,
    filename: str,
    data: Any,
    *,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write *data* to a workspace file and return a compact response dict.

    Parameters
    ----------
    session : SessionState
        The current session (must have a workspace).
    filename : str
        Name for the workspace file (e.g. ``"component_list.json"``).
    data : dict | list | str
        The full result data to persist.
    summary : dict, optional
        Extra key-value pairs to include in the MCP response (e.g. counts,
        hints).  Merged into the response alongside ``file``.

    Returns
    -------
    dict
        A compact dict containing ``"file"`` (workspace path) plus any
        ``summary`` fields.  Suitable for ``json.dumps()``.
    """
    if session is None or getattr(session, "workspace", None) is None:
        # No workspace available — caller should fall back to inline return.
        # Return the data as-is wrapped in a dict so the caller can detect.
        return {"_inline": True, "data": data}

    workspace = session.workspace

    # Write JSON or text depending on data type
    if isinstance(data, str):
        file_path = workspace.write_text(filename, data)
    else:
        file_path = workspace.write_json(filename, data)

    logger.debug("Result written to workspace: %s (%d bytes)", file_path, file_path.stat().st_size)

    response: Dict[str, Any] = {"file": str(file_path)}
    if summary:
        response.update(summary)
    return response
