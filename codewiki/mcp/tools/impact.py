"""MCP tool: analyze_impact — transitive dependency impact analysis.

Given one or more components (by ID or file path), traverse the dependency
graph to find all transitively affected components.  Supports three
traversal directions:

* ``depended_by`` (default) – "who depends on me, transitively?"
* ``depends_on`` – "what do I depend on, transitively?"
* ``both`` – union of the two.

Results are enriched with component metadata, aggregated by module, and
written to a workspace file (``impact_analysis.json``).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.workspace_result import write_result
from codewiki.src.be.dependency_analyzer.topo_sort import (
    build_graph_from_components,
    resolve_files_to_components,
    transitive_impact,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_comp_module_index(module_tree: Dict[str, Any]) -> Dict[str, str]:
    """Build a component-id → module-name inverted index in one tree walk."""
    index: Dict[str, str] = {}

    def _walk(tree: Dict) -> None:
        for mod_name, mod_info in tree.items():
            for cid in mod_info.get("components", []):
                index.setdefault(cid, mod_name)
            children = mod_info.get("children", {})
            if isinstance(children, dict) and children:
                _walk(children)

    _walk(module_tree)
    return index


def _enrich_component(
    comp_id: str,
    meta: Any,
    depth: int,
    comp_module_idx: Dict[str, str],
    path: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a result entry for a single affected component."""
    entry: Dict[str, Any] = {
        "component_id": comp_id,
        "name": getattr(meta, "name", comp_id),
        "component_type": getattr(meta, "component_type", "unknown"),
        "file_path": getattr(meta, "relative_path", "") or getattr(meta, "file_path", ""),
        "depth": depth,
    }
    if comp_module_idx:
        mod = comp_module_idx.get(comp_id)
        if mod:
            entry["module"] = mod
    if path is not None:
        entry["call_path"] = path
    return entry


# ------------------------------------------------------------------
# Main handler
# ------------------------------------------------------------------


def handle_analyze_impact(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Analyze transitive impact for given components or files.

    Parameters (via *arguments*)
    ----------------------------
    repo_path : str
        Repository path. Auto-restores the session from the SQLite
        cache if a previous analysis exists.
    component_ids : list[str], optional
        Component IDs to analyze.  Mutually complementary with *file_paths*.
    file_paths : list[str], optional
        Source file paths; resolved to component IDs automatically.
    direction : str
        ``"depended_by"`` | ``"depends_on"`` | ``"both"`` (default ``"depended_by"``).
    max_depth : int
        Maximum BFS depth (default 10).
    include_paths : bool
        Include shortest call-chain paths in the output (default False).
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    if session is None:
        return json.dumps(
            {
                "error": "Session not found. Provide a valid repo_path pointing to a previously analyzed repository."
            }
        )

    components = session.components
    module_tree = session.module_tree or {}
    comp_module_idx = _build_comp_module_index(module_tree) if module_tree else {}
    direction = arguments.get("direction", "depended_by")
    max_depth = min(int(arguments.get("max_depth", 10)), 50)
    include_paths = arguments.get("include_paths", False)

    # --- Resolve start nodes -------------------------------------------
    start_ids: Set[str] = set()

    raw_ids = arguments.get("component_ids") or []
    for cid in raw_ids:
        if cid in components:
            start_ids.add(cid)

    raw_files = arguments.get("file_paths") or []
    if raw_files:
        resolved = resolve_files_to_components(components, raw_files)
        start_ids.update(resolved)

    if not start_ids:
        return json.dumps(
            {
                "error": "No valid components found. Provide component_ids or file_paths "
                "that match components in the analyzed repository.",
            }
        )

    # --- Build graph & traverse ----------------------------------------
    graph = build_graph_from_components(components)
    result = transitive_impact(
        graph,
        start_ids,
        max_depth=max_depth,
        direction=direction,
        track_paths=include_paths,
    )

    affected: Dict[str, int] = result["affected"]
    paths: Dict[str, List[str]] = result.get("paths", {})

    # --- Enrich results ------------------------------------------------
    # Build a quick meta lookup (ComponentMeta, no SQLite round-trip)
    meta_map: Dict[str, Any] = dict(components.items())

    enriched: List[Dict[str, Any]] = []
    for comp_id, depth in sorted(affected.items(), key=lambda x: (x[1], x[0])):
        meta = meta_map.get(comp_id)
        if meta is None:
            continue
        enriched.append(
            _enrich_component(
                comp_id,
                meta,
                depth,
                comp_module_idx,
                path=paths.get(comp_id) if include_paths else None,
            )
        )

    # --- Module-level aggregation --------------------------------------
    module_impact: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"affected_count": 0, "max_depth": 0, "components": []}
    )
    for entry in enriched:
        mod = entry.get("module")
        if not mod:
            continue
        mi = module_impact[mod]
        mi["affected_count"] += 1
        mi["max_depth"] = max(mi["max_depth"], entry["depth"])
        mi["components"].append(entry["component_id"])

    # Sort modules by affected_count descending
    module_summary = {
        mod: {
            "affected_count": info["affected_count"],
            "max_depth": info["max_depth"],
            "components": info["components"][:20],  # cap for readability
        }
        for mod, info in sorted(
            module_impact.items(),
            key=lambda x: x[1]["affected_count"],
            reverse=True,
        )
    }

    # --- High-risk components (many direct dependents) -----------------
    reverse_count: Dict[str, int] = defaultdict(int)
    for node, deps in graph.items():
        for dep in deps:
            reverse_count[dep] += 1

    high_risk = [
        {
            "component_id": cid,
            "name": getattr(meta_map.get(cid), "name", cid),
            "direct_dependents": reverse_count.get(cid, 0),
            "depth": affected.get(cid, -1),
        }
        for cid in sorted(
            affected,
            key=lambda c: reverse_count.get(c, 0),
            reverse=True,
        )
        if reverse_count.get(cid, 0) >= 5
    ][:20]

    # --- Assemble & write ----------------------------------------------
    full_result: Dict[str, Any] = {
        "query": {
            "start_components": sorted(start_ids),
            "direction": direction,
            "max_depth": max_depth,
            "include_paths": include_paths,
        },
        "summary": {
            "total_affected": len(enriched),
            "start_count": len(start_ids),
            "modules_affected": len(module_summary),
            "high_risk_count": len(high_risk),
        },
        "affected_components": enriched,
        "module_impact": module_summary,
    }
    if high_risk:
        full_result["high_risk_components"] = high_risk

    response = write_result(
        session,
        "impact_analysis.json",
        full_result,
        summary={
            "total_affected": len(enriched),
            "start_count": len(start_ids),
            "modules_affected": len(module_summary),
            "high_risk_count": len(high_risk),
            "direction": direction,
            "hint": "Read the file for full impact data including per-component details.",
        },
    )

    # Graph freshness hint (only present when watch mode is active).
    from codewiki.mcp.tools.watch import attach_graph_stale

    response = attach_graph_stale(response, session)

    return json.dumps(response, indent=2, ensure_ascii=False)
