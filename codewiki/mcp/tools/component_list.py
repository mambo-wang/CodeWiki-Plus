"""MCP tool: list_components — write the full component index to a workspace file.

After ``analyze_repo`` writes the component index to disk, this tool lets
the IDE agent retrieve a (optionally filtered) component list in a single
call.  The full result is written to a workspace file and only the file
path plus a compact summary are returned through the MCP stdio channel.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.workspace_result import write_result


def handle_list_components(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Write the session's component index to a workspace file.

    Arguments
    ---------
    session_id : str (required)
        Session ID from ``analyze_repo``.
    file_prefix : str (optional)
        Only include components whose ``file`` starts with this prefix.
    component_type : str (optional)
        Only include components of this type (e.g. ``class``,
        ``function``, ``interface``).

    Returns
    -------
    JSON string with ``file`` (workspace path), ``total`` count, and ``hint``.
    """
    session_id = arguments.get("session_id", "")
    session = store.get(session_id)
    if session is None:
        return json.dumps(
            {"error": f"Session {session_id} not found or expired."},
            ensure_ascii=False,
        )

    file_prefix = arguments.get("file_prefix", "")
    component_type = arguments.get("component_type", "")

    # Build the component list from the in-memory session.
    components: list = []
    for comp_id, node in session.components.items():
        comp_type = getattr(node, "component_type", "unknown")
        comp_file = getattr(node, "relative_path", "")

        if file_prefix and not comp_file.startswith(file_prefix):
            continue
        if component_type and comp_type != component_type:
            continue

        components.append(
            {"id": comp_id, "type": comp_type, "file": comp_file}
        )

    # Sort by file then component name for stable ordering
    components.sort(key=lambda c: (c["file"], c["id"]))

    total = len(components)

    # Write the full list to a workspace file
    response = write_result(
        session,
        "component_list.json",
        {"components": components},
        summary={
            "total": total,
            "hint": "Read the file for the full component list. Use read_code_components to fetch source code.",
        },
    )

    return json.dumps(response, indent=2, ensure_ascii=False)
