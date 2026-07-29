"""CBM (codebase-memory-mcp) integration — delegate to CBM when available.

When the CBM MCP server is connected, this module calls its tools
(``trace_path``, ``get_architecture``) to enrich cross-service analysis
with deep graph queries. Falls back gracefully to local Route matching.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def is_cbm_available() -> bool:
    """Check if codebase-memory-mcp tools are available."""
    try:
        from codewiki.mcp.server import server
        # Check if CBM tools are registered by trying to import the tool list
        # This is a heuristic — actual availability depends on MCP server config
        import importlib.util
        spec = importlib.util.find_spec("codebase_memory_mcp")
        return spec is not None
    except Exception:
        return False


def cbm_trace_cross_service(
    repo_path: str,
    route_key: str = "",
    max_depth: int = 3,
) -> Optional[Dict[str, Any]]:
    """Call CBM's trace_path tool for cross-service tracing.

    Returns None if CBM is not available or the call fails.
    """
    if not is_cbm_available():
        return None

    try:
        # CBM is typically accessed via MCP — this would need the MCP client
        # to call trace_path. For now, return None to trigger local fallback.
        logger.debug("CBM trace_path not yet wired to MCP client, using local fallback")
        return None
    except Exception as e:
        logger.warning("CBM trace_path failed: %s", e)
        return None


def cbm_get_architecture(
    repo_path: str,
) -> Optional[Dict[str, Any]]:
    """Call CBM's get_architecture tool for Leiden community detection.

    Returns None if CBM is not available or the call fails.
    """
    if not is_cbm_available():
        return None

    try:
        logger.debug("CBM get_architecture not yet wired to MCP client, using local fallback")
        return None
    except Exception as e:
        logger.warning("CBM get_architecture failed: %s", e)
        return None


def merge_cbm_and_local_results(
    local_topology: Dict[str, Any],
    cbm_results: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge local Route matching results with CBM results.

    When CBM provides additional cross-service edges (from deeper graph
    analysis), they are appended to the local results. Duplicate edges
    (same route_key + same repos) are deduplicated.
    """
    if cbm_results is None:
        return local_topology

    # Merge links — CBM may find edges that local matching missed
    cbm_links = cbm_results.get("links", [])
    local_links = local_topology.get("links", [])

    existing_keys = {
        f"{l.get('client_repo')}:{l.get('server_repo')}:{l.get('route_key')}"
        for l in local_links
    }

    for cbm_link in cbm_links:
        key = f"{cbm_link.get('client_repo')}:{cbm_link.get('server_repo')}:{cbm_link.get('route_key')}"
        if key not in existing_keys:
            local_links.append(cbm_link)
            existing_keys.add(key)

    local_topology["links"] = local_links
    return local_topology
