"""MCP tool: query_cross_service — query cross-service links in a workspace.

Supports listing all links, filtering by service name, HTTP method, or path,
and tracing a specific route's call chain.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def handle_query_cross_service(
    arguments: Dict[str, Any],
) -> str:
    """Query cross-service links from a workspace's cached topology.

    Arguments:
        workspace_path: Path to the workspace directory.
        output_dir: Explicit output directory containing .meta/ with cross-service data.
        filter_type: One of "all", "by_service", "by_method", "by_path", "trace".
        filter_value: The value to filter by (service name, HTTP method, path prefix).
    """
    workspace_path = Path(arguments.get("workspace_path", ".")).resolve()
    filter_type = arguments.get("filter_type", "all")
    filter_value = arguments.get("filter_value", "")

    # Resolve meta directory: explicit output_dir first, then auto-derive
    explicit_od = arguments.get("output_dir")
    if explicit_od:
        meta_dir = Path(explicit_od).expanduser().resolve() / ".meta"
    else:
        meta_dir = workspace_path / "workspace-wiki" / ".meta"
        if not meta_dir.exists():
            meta_dir = workspace_path / "repowiki" / ".meta"
        if not meta_dir.exists():
            # Broader search: try common workspace subdirs
            for candidate in workspace_path.iterdir():
                if not candidate.is_dir() or candidate.name.startswith("."):
                    continue
                test_dir = candidate / ".meta"
                if test_dir.exists() and (test_dir / "cross_service_links.json").exists():
                    meta_dir = test_dir
                    break

    links_path = meta_dir / "cross_service_links.json"
    routes_path = meta_dir / "workspace_routes.json"

    links: List[Dict] = []
    routes: List[Dict] = []

    if links_path.exists():
        try:
            links = json.loads(links_path.read_text(encoding="utf-8"))
        except Exception as e:
            return json.dumps({"error": f"Failed to read links: {e}"})

    if routes_path.exists():
        try:
            routes = json.loads(routes_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if filter_type == "all":
        result = _format_all(links, routes)
    elif filter_type == "by_service":
        result = _filter_by_service(links, filter_value)
    elif filter_type == "by_method":
        result = _filter_by_method(links, filter_value)
    elif filter_type == "by_path":
        result = _filter_by_path(links, filter_value)
    elif filter_type == "trace":
        result = _trace_route(links, routes, filter_value)
    else:
        result = {"error": f"Unknown filter_type: {filter_type}"}

    return json.dumps(result, indent=2, ensure_ascii=False)


def _format_all(links: List[Dict], routes: List[Dict]) -> Dict:
    summary = {
        "total_links": len(links),
        "total_routes": len(routes),
        "protocols": {},
    }
    for link in links:
        proto = link.get("protocol", "http")
        summary["protocols"][proto] = summary["protocols"].get(proto, 0) + 1

    return {
        "summary": summary,
        "links": links,
        "unmatched_routes": [
            r for r in routes
            if not any(
                l.get("route_key") == r.get("route_key") for l in links
            )
        ],
    }


def _filter_by_service(links: List[Dict], service: str) -> Dict:
    matching = [
        l for l in links
        if service.lower() in l.get("client_repo", "").lower()
        or service.lower() in l.get("server_repo", "").lower()
    ]
    return {
        "service": service,
        "count": len(matching),
        "as_client": [l for l in matching if service.lower() in l.get("client_repo", "").lower()],
        "as_server": [l for l in matching if service.lower() in l.get("server_repo", "").lower()],
    }


def _filter_by_method(links: List[Dict], method: str) -> Dict:
    # MQ links serialize method as null — guard against None before .upper()
    matching = [l for l in links if (l.get("method") or "").upper() == method.upper()]
    return {"method": method.upper(), "count": len(matching), "links": matching}


def _filter_by_path(links: List[Dict], path_prefix: str) -> Dict:
    matching = [l for l in links if (l.get("path") or "").startswith(path_prefix)]
    return {"path_prefix": path_prefix, "count": len(matching), "links": matching}


def _trace_route(links: List[Dict], routes: List[Dict], route_key: str) -> Dict:
    """Trace a specific route: find all clients and servers involved."""
    matching_links = [l for l in links if l.get("route_key") == route_key]
    matching_routes = [r for r in routes if r.get("route_key") == route_key]

    clients = []
    servers = []
    for link in matching_links:
        clients.append({
            "repo": link.get("client_repo"),
            "function": link.get("client_function"),
            "component_id": link.get("client_component_id"),
        })
        servers.append({
            "repo": link.get("server_repo"),
            "function": link.get("server_function"),
            "component_id": link.get("server_component_id"),
        })

    return {
        "route_key": route_key,
        "links_count": len(matching_links),
        "clients": clients,
        "servers": servers,
        "route_details": matching_routes,
    }
