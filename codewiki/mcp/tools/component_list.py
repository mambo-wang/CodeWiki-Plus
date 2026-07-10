"""MCP tool: list_components — write the component index to a workspace file.

After ``analyze_repo`` writes the component index to disk, this tool lets
the IDE agent retrieve a (optionally filtered) component list in a single
call.  Supports two modes:

- **Full mode** (default): writes every component ``{id, type, file}`` to
  ``component_list.json``.
- **Summary mode** (``summary: true``): aggregates by file, writing
  ``{count, types, classes}`` per file to ``component_summary.json``.
  This is ~8× smaller and sufficient for module-clustering decisions.

The full result is written to a workspace file and only the file path
plus a compact summary are returned through the MCP stdio channel.
"""

from __future__ import annotations

import json
from collections import defaultdict
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
    summary : bool (optional, default False)
        If true, return a compact file-level summary instead of
        individual component entries.  Useful for module clustering.

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
    summary_mode = arguments.get("summary", False)

    # Collect filtered components from the in-memory session.
    raw_entries: list = []
    for comp_id, node in session.components.items():
        comp_type = getattr(node, "component_type", "unknown")
        comp_file = getattr(node, "relative_path", "")

        if file_prefix and not comp_file.replace("\\", "/").startswith(file_prefix.replace("\\", "/")):
            continue
        if component_type and comp_type != component_type:
            continue

        raw_entries.append(
            {"id": comp_id, "type": comp_type, "file": comp_file}
        )

    total = len(raw_entries)

    if summary_mode:
        return _build_summary(session, raw_entries, total)
    else:
        return _build_full(session, raw_entries, total)


# ------------------------------------------------------------------ #
#  Full mode                                                          #
# ------------------------------------------------------------------ #

def _build_full(session, entries: list, total: int) -> str:
    """Write every component entry to component_list.json."""
    entries.sort(key=lambda c: (c["file"], c["id"]))

    response = write_result(
        session,
        "component_list.json",
        {"components": entries},
        summary={
            "total": total,
            "hint": "Read the file for the full component list. "
                    "Use read_code_components to fetch source code.",
        },
    )
    return json.dumps(response, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ #
#  Summary mode                                                       #
# ------------------------------------------------------------------ #

# Component types considered "class-like" for the summary.
_CLASS_LIKE_TYPES = frozenset({"class", "interface", "struct", "enum", "trait", "protocol"})


def _build_summary(session, entries: list, total: int) -> str:
    """Aggregate components by file and write component_summary.json."""
    file_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "types": defaultdict(int), "classes": []}
    )

    for entry in entries:
        f = entry["file"]
        t = entry["type"]
        file_data[f]["count"] += 1
        file_data[f]["types"][t] += 1
        if t in _CLASS_LIKE_TYPES:
            # Extract the short class name from the component ID.
            # e.g. "src/foo.py::MyClass::method" → "MyClass"
            #      "src/foo.py::MyClass"         → "MyClass"
            parts = entry["id"].split("::")
            class_name = parts[1] if len(parts) >= 2 else parts[0]
            if class_name not in file_data[f]["classes"]:
                file_data[f]["classes"].append(class_name)

    # Build the output dict with sorted keys for stable ordering.
    files_out: Dict[str, Any] = {}
    for f in sorted(file_data):
        info = file_data[f]
        # Normalize to forward slashes for cross-platform consistency
        normalized_f = f.replace("\\", "/")
        files_out[normalized_f] = {
            "count": info["count"],
            "types": dict(info["types"]),
            "classes": info["classes"],
        }

    response = write_result(
        session,
        "component_summary.json",
        {"files": files_out, "total_components": total},
        summary={
            "total_files": len(files_out),
            "total_components": total,
            "mode": "summary",
            "hint": "Read the file for the per-file summary. "
                    "Use list_components(file_prefix=<dir>) for exact IDs "
                    "when generating docs for a specific module.",
        },
    )
    return json.dumps(response, indent=2, ensure_ascii=False)
