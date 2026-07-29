"""URL path canonicalization — normalize framework-specific parameter syntax.

Borrowed from CBM's ``cbm_route_canon_path()`` (pass_route_nodes.c:59-129).
All parameter placeholders are unified to ``{}`` so that different
frameworks can match against the same Route key.
"""
from __future__ import annotations

import re


def canonicalize_path(path: str) -> str:
    """Normalize URL path parameter placeholders to ``{}``.

    Supported syntaxes
    ------------------
    - ``:name``   (Express / Rails)
    - ``{name}``  (Spring / Axum / OpenAPI)
    - ``<name>`` or ``<type:name>`` (Flask / Rocket)
    - ``${...}``  (JS template literals)

    Trailing slashes are stripped (except for the root ``/``).
    Query strings and fragments are discarded.
    """
    if not path:
        return "/"

    # Strip query string and fragment
    q = path.find("?")
    if q != -1:
        path = path[:q]
    f = path.find("#")
    if f != -1:
        path = path[:f]

    # JS template literals  ${...}  →  {}
    # (must run before the generic {name} rule, which would otherwise
    # reduce "${id}" to "${}" and leave the "$" behind)
    path = re.sub(r"\$\{[^}]+\}", "{}", path)
    # Express / Rails  :name  →  {}
    path = re.sub(r":([a-zA-Z_]\w*)", "{}", path)
    # Spring / Axum / OpenAPI  {name}  →  {}
    path = re.sub(r"\{[^}]+\}", "{}", path)
    # Flask / Rocket  <name> or <int:name>  →  {}
    path = re.sub(r"<[^>]+>", "{}", path)

    # Strip trailing slash (keep root "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return path


def make_route_key(method: str, path: str) -> str:
    """Build a CBM-compatible Route QN: ``__route__METHOD__path``."""
    return f"__route__{method.upper()}__{canonicalize_path(path)}"


def make_mq_route_key(broker: str, topic_or_queue: str) -> str:
    """Build an MQ Route key: ``__mq__broker__topic``."""
    return f"__mq__{broker.lower()}__{topic_or_queue}"
