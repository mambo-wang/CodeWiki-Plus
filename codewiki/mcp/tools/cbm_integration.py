"""CBM (codebase-memory-mcp) integration — delegate to CBM when available.

When the CBM binary is installed, this module calls its MCP tools
(``trace_path``, ``get_architecture``, ``detect_changes``) to enrich
CodeWiki's analysis with deep graph queries. Falls back gracefully to
local Route matching when CBM is absent or unreachable.

Architecture:
    cbm_client.py  — singleton MCP client (subprocess management)
    cbm_integration.py (this file) — high-level delegation functions
    registry.py    — dispatch-level enrichment hook (post-handler)

All public functions are async and return Optional[Dict]:
    - Dict on success (CBM responded)
    - None on failure/unavailable (caller uses local fallback)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from codewiki.mcp.cbm_client import get_cbm_client, is_cbm_enabled

logger = logging.getLogger(__name__)


def _project_name(repo_path: str) -> str:
    """Derive CBM index/project name from a repo path.

    CBM uses path separators replaced with dashes as the project key,
    e.g. ``/home/user/repos/foo`` → ``home-user-repos-foo``.
    """
    import re

    return re.sub(r"[/\\]+", "-", repo_path).strip("-")


def is_cbm_available() -> bool:
    """Check if CBM binary is installed and delegation is enabled.

    This is a fast, synchronous check (no subprocess spawn).
    Used by callers to decide whether to attempt CBM delegation.
    """
    return is_cbm_enabled()


async def cbm_trace_cross_service(
    function_name: str,
    repo_path: str = "",
    direction: str = "both",
    depth: int = 3,
) -> Optional[Dict[str, Any]]:
    """Call CBM's trace_path tool in cross_service mode.

    Returns the parsed JSON result from CBM, or None if unavailable.
    The caller should merge this into local Route matching results.
    """
    if not is_cbm_enabled():
        return None

    client = get_cbm_client()
    args: Dict[str, Any] = {
        "function_name": function_name,
        "mode": "cross_service",
        "direction": direction,
        "depth": min(depth, 5),  # CBM max depth is 5
    }
    if repo_path:
        args["project"] = _project_name(repo_path)
    result = await client.call(
        "trace_path",
        args,
        timeout_seconds=30.0,
    )

    if result is not None:
        logger.debug(
            "CBM trace_path(cross_service) for %s: %d paths",
            function_name,
            len(result.get("paths", result.get("results", []))),
        )
    return result


async def cbm_get_architecture(
    repo_path: str,
    aspects: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Call CBM's get_architecture tool for Leiden clusters, hotspots, cycles.

    Typical aspects: ["clusters", "hotspots", "cycles", "boundaries", "layers"]
    Returns the parsed JSON result from CBM, or None if unavailable.
    """
    if not is_cbm_enabled():
        return None

    if aspects is None:
        aspects = ["clusters", "hotspots", "cycles"]

    client = get_cbm_client()
    result = await client.call(
        "get_architecture",
        {
            "aspects": aspects,
            "project": _project_name(repo_path),
        },
        timeout_seconds=60.0,  # Architecture analysis can be slow
    )

    if result is not None:
        logger.debug(
            "CBM get_architecture for %s: aspects=%s",
            repo_path,
            list(result.keys()) if isinstance(result, dict) else "non-dict",
        )
    return result


async def cbm_detect_changes(
    repo_path: str,
    scope: str = "impact",
    direction: str = "inbound",
    depth: int = 2,
    since: str = "HEAD~1",
) -> Optional[Dict[str, Any]]:
    """Call CBM's detect_changes tool for git-diff blast radius analysis.

    Returns symbol-level impact with risk grading, or None if unavailable.
    """
    if not is_cbm_enabled():
        return None

    client = get_cbm_client()
    result = await client.call(
        "detect_changes",
        {
            "project": _project_name(repo_path),
            "scope": scope,
            "direction": direction,
            "depth": depth,
            "since": since,
        },
        timeout_seconds=30.0,
    )

    if result is not None:
        logger.debug(
            "CBM detect_changes: %s", list(result.keys()) if isinstance(result, dict) else ""
        )
    return result


async def cbm_search_graph(
    query: str = "",
    name_pattern: str = "",
    min_degree: int = 0,
) -> Optional[Dict[str, Any]]:
    """Call CBM's search_graph for BM25/regex/semantic search over code symbols.

    Returns search results or None if unavailable.
    """
    if not is_cbm_enabled():
        return None

    args: Dict[str, Any] = {}
    if query:
        args["query"] = query
    if name_pattern:
        args["name_pattern"] = name_pattern
    if min_degree > 0:
        args["min_degree"] = min_degree

    if not args:
        return None

    client = get_cbm_client()
    return await client.call("search_graph", args, timeout_seconds=15.0)


def merge_cbm_and_local_results(
    local_topology: Dict[str, Any],
    cbm_results: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge local Route matching results with CBM trace results.

    When CBM provides additional cross-service edges (from deeper graph
    analysis), they are appended to the local results. Duplicate edges
    (same route_key + same repos) are deduplicated.
    """
    if cbm_results is None:
        return local_topology

    # CBM trace_path returns paths with caller/callee info
    # Normalize to the local link format for merging
    cbm_paths = cbm_results.get("paths", cbm_results.get("results", []))
    local_links = local_topology.get("links", [])

    existing_keys = {
        f"{link.get('client_repo')}:{link.get('server_repo')}:{link.get('route_key')}"
        for link in local_links
    }

    for path_entry in cbm_paths:
        # CBM cross_service paths have caller_project/callee_project/route info
        link = {
            "client_repo": path_entry.get("caller_project", path_entry.get("client_repo", "")),
            "server_repo": path_entry.get("callee_project", path_entry.get("server_repo", "")),
            "route_key": path_entry.get("route_key", path_entry.get("route", "")),
            "client_function": path_entry.get(
                "caller_function", path_entry.get("client_function", "")
            ),
            "server_function": path_entry.get(
                "callee_function", path_entry.get("server_function", "")
            ),
            "protocol": path_entry.get("protocol", "http"),
            "source": "cbm",  # Mark origin for debugging
        }
        key = f"{link['client_repo']}:{link['server_repo']}:{link['route_key']}"
        if key not in existing_keys:
            local_links.append(link)
            existing_keys.add(key)

    local_topology["links"] = local_links

    # Attach CBM metadata if present
    if "clusters" in cbm_results:
        local_topology["cbm_clusters"] = cbm_results["clusters"]
    if "hotspots" in cbm_results:
        local_topology["cbm_hotspots"] = cbm_results["hotspots"]

    return local_topology
