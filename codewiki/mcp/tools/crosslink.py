"""MCP tool: list_dependencies — expose component dependency data.

Provides dependency relationships (depends_on / depended_by) between components,
with optional module-level aggregation for crosslinking documentation.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)

_DEFAULT_HIGH_IMPACT_THRESHOLD = 5


def _read_high_impact_threshold(output_dir: str) -> int:
    """Read lint.high_impact_threshold from schema.yaml, defaulting to 5."""
    try:
        import yaml
        from codewiki.src.config import SCHEMA_FILENAME
        schema_path = Path(output_dir) / SCHEMA_FILENAME
        if schema_path.exists():
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
            return schema.get("lint", {}).get(
                "high_impact_threshold", _DEFAULT_HIGH_IMPACT_THRESHOLD
            )
    except Exception:
        pass
    return _DEFAULT_HIGH_IMPACT_THRESHOLD


def _build_reverse_index(components: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Build a depended_by (reverse) index from components' depends_on."""
    reverse: Dict[str, Set[str]] = defaultdict(set)
    for comp_id, node in components.items():
        deps = getattr(node, "depends_on", None)
        if deps:
            for dep in deps:
                reverse[dep].add(comp_id)
    return dict(reverse)


def _component_to_module(
    component_id: str,
    module_tree: Dict[str, Any],
) -> Optional[str]:
    """Map a component ID to its module name via the module tree."""
    def _walk(tree: Dict) -> Optional[str]:
        for mod_name, mod_info in tree.items():
            comp_list = mod_info.get("components", [])
            if component_id in comp_list:
                return mod_name
            children = mod_info.get("children", {})
            if isinstance(children, dict) and children:
                found = _walk(children)
                if found:
                    return found
        return None
    return _walk(module_tree)


def _build_module_dependency_graph(
    components: Dict[str, Any],
    module_tree: Dict[str, Any],
) -> Dict[str, Dict[str, List[str]]]:
    """Aggregate component-level dependencies into module-level graph."""
    graph: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: {
        "depends_on": set(), "depended_by": set()
    })
    reverse = _build_reverse_index(components)

    for comp_id, node in components.items():
        source_module = _component_to_module(comp_id, module_tree)
        if not source_module:
            continue
        # depends_on direction
        deps = getattr(node, "depends_on", None) or set()
        for dep_id in deps:
            target_module = _component_to_module(dep_id, module_tree)
            if target_module and target_module != source_module:
                graph[source_module]["depends_on"].add(target_module)
                graph[target_module]["depended_by"].add(source_module)

    # Convert sets to sorted lists
    return {
        mod: {
            "depends_on": sorted(info["depends_on"]),
            "depended_by": sorted(info["depended_by"]),
        }
        for mod, info in sorted(graph.items())
    }


def handle_list_dependencies(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return dependency relationships for components or modules."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    components = session.components
    module_tree = session.module_tree

    direction = arguments.get("direction", "both")  # depends_on | depended_by | both
    module_level = arguments.get("module_level", False)
    offset = max(0, arguments.get("offset", 0))
    limit = min(200, max(1, arguments.get("limit", 100)))

    # Build reverse index
    reverse_index = _build_reverse_index(components)

    # Filter by specific component_ids if provided
    target_ids = arguments.get("component_ids")
    if target_ids:
        source_ids = [cid for cid in target_ids if cid in components]
    else:
        source_ids = sorted(components.keys())

    # Build dependency entries
    entries: List[Dict[str, Any]] = []
    for comp_id in source_ids:
        node = components.get(comp_id)
        if node is None:
            continue

        source_module = _component_to_module(comp_id, module_tree) if module_tree else None

        if direction in ("depends_on", "both"):
            deps = getattr(node, "depends_on", None) or set()
            for dep_id in sorted(deps):
                target_module = (
                    _component_to_module(dep_id, module_tree)
                    if module_tree else None
                )
                entry: Dict[str, Any] = {
                    "source": comp_id,
                    "target": dep_id,
                    "direction": "depends_on",
                }
                if source_module:
                    entry["source_module"] = source_module
                if target_module:
                    entry["target_module"] = target_module
                entries.append(entry)

        if direction in ("depended_by", "both"):
            dependents = reverse_index.get(comp_id, set())
            for dep_id in sorted(dependents):
                target_module = (
                    _component_to_module(dep_id, module_tree)
                    if module_tree else None
                )
                entry = {
                    "source": comp_id,
                    "target": dep_id,
                    "direction": "depended_by",
                }
                if source_module:
                    entry["source_module"] = source_module
                if target_module:
                    entry["target_module"] = target_module
                entries.append(entry)

    # Module-level graph
    module_graph = None
    if module_level and module_tree:
        module_graph = _build_module_dependency_graph(components, module_tree)

    # Pagination
    total = len(entries)
    page = entries[offset: offset + limit]

    result: Dict[str, Any] = {
        "dependencies": page,
        "pagination": {
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total,
        },
    }
    if module_graph is not None:
        result["module_dependency_graph"] = module_graph

    # High-impact components (depended_by >= threshold from schema.yaml)
    threshold = _read_high_impact_threshold(session.output_dir)
    high_impact = [
        {"component_id": cid, "depended_by_count": len(deps)}
        for cid, deps in sorted(
            reverse_index.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
        if len(deps) >= threshold
    ][:20]
    if high_impact:
        result["high_impact_components"] = high_impact

    return json.dumps(result, indent=2, ensure_ascii=False)
