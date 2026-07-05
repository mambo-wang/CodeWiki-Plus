"""MCP tool: list_components — paginated component index browser.

After ``analyze_repo`` writes the full component index to disk,
this tool lets the IDE agent browse it via MCP without reading files
directly.  Supports optional filtering by file prefix and component
type, with the same pagination pattern as ``list_dependencies``.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from codewiki.mcp.session import SessionStore


def handle_list_components(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return a paginated slice of the session's component index.

    Arguments
    ---------
    session_id : str (required)
        Session ID from ``analyze_repo``.
    offset : int (default 0)
        Zero-based offset into the sorted component list.
    limit : int (default 100, clamped to [1, 200])
        Maximum number of components to return.
    file_prefix : str (optional)
        Only include components whose ``file`` starts with this prefix.
        Useful for efficiently browsing a single package or directory.
    component_type : str (optional)
        Only include components of this type (e.g. ``class``,
        ``function``, ``interface``).

    Returns
    -------
    JSON string with ``components`` list and ``pagination`` info.
    """
    session_id = arguments.get("session_id", "")
    session = store.get(session_id)
    if session is None:
        return json.dumps(
            {"error": f"Session {session_id} not found or expired."},
            ensure_ascii=False,
        )

    offset = max(0, arguments.get("offset", 0))
    limit = min(200, max(1, arguments.get("limit", 100)))
    file_prefix = arguments.get("file_prefix", "")
    component_type = arguments.get("component_type", "")

    # Build the component list from the in-memory session (no disk read).
    components: list = []
    for comp_id, node in session.components.items():
        comp_type = getattr(node, "component_type", "unknown")
        comp_file = getattr(node, "relative_path", "")

        # Apply optional filters
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
    page = components[offset: offset + limit]

    return json.dumps(
        {
            "components": page,
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total,
            },
        },
        indent=2,
        ensure_ascii=False,
    )
