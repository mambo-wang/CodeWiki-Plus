"""Shared helper: read big-data params from temp files.

When a tool parameter is too large to pass through MCP stdio
(e.g. a 100KB module tree or a 500-line document), the IDE agent
writes the data to a temp file and passes the path via a
``<param>_file`` companion parameter.

Usage in a handler::

    content = _read_param(arguments, "content")
    # If arguments has "content_file", reads from that path.
    # Otherwise falls back to inline "content" value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def read_param(
    arguments: dict[str, Any],
    param_name: str,
) -> Optional[str]:
    """Read a string parameter, supporting ``<param>_file`` fallback.

    If ``arguments[param_name + "_file"]`` exists, read the file at
    that path and return its contents.  Otherwise return
    ``arguments[param_name]`` (which may be None).

    The file path must be absolute (starts with ``/``).
    """
    file_key = param_name + "_file"
    file_path = arguments.get(file_key)
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            # Resolve relative to cwd (shouldn't happen, but be safe)
            p = p.resolve()
        return p.read_text(encoding="utf-8", errors="replace")
    return arguments.get(param_name)


def read_json_param(
    arguments: dict[str, Any],
    param_name: str,
) -> Optional[Any]:
    """Read a JSON parameter, supporting ``<param>_file`` fallback.

    Like :func:`read_param` but parses the result as JSON.
    """
    raw = read_param(arguments, param_name)
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw  # already parsed (inline JSON object)
    return json.loads(raw)
