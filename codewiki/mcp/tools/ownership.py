"""为变更的未归属组件生成确定性 owner 候选，不修改模块树或调用 LLM。"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

ModulePath = tuple[str, ...]


def _attr(component: Any, name: str, default: Any = None) -> Any:
    if isinstance(component, Mapping):
        return component.get(name, default)
    return getattr(component, name, default)


def normalize_component_path(path: Any) -> str:
    """统一组件相对路径证据，避免 Windows 分隔符与 ``./`` 造成漏判。"""
    value = str(path or "").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    # Windows 位置证据按平台大小写语义比较；POSIX 保持原样。
    return os.path.normcase(value).replace("\\", "/")


def _parent_path(path: str) -> str:
    return PurePosixPath(path).parent.as_posix()


def build_owner_map(module_tree: Mapping[str, Any]) -> dict[str, ModulePath]:
    owners: dict[str, ModulePath] = {}

    def walk(tree: Mapping[str, Any], parents: tuple[str, ...] = ()) -> None:
        for name, raw_info in tree.items():
            if not isinstance(raw_info, Mapping):
                raise ValueError(f"module node {name!r} must be an object")
            info = raw_info
            current = (*parents, str(name))
            components = info.get("components", [])
            if not isinstance(components, list):
                raise ValueError(f"module node {name!r} components must be a list")
            for component_id in components:
                if not isinstance(component_id, str):
                    raise ValueError(f"module node {name!r} contains a non-string component ID")
                previous = owners.get(component_id)
                if previous is not None:
                    raise ValueError(
                        f"component {component_id!r} has multiple module owners: "
                        f"{previous!r} and {current!r}"
                    )
                owners[component_id] = current
            children = info.get("children", {})
            if not isinstance(children, Mapping):
                raise ValueError(f"module node {name!r} children must be an object")
            if children:
                walk(children, current)

    walk(module_tree)
    return owners


def resolve_owner(owners: Mapping[str, ModulePath], component_id: str) -> ModulePath | None:
    """把组件或其方法解析到最深的已知 owner。"""
    direct = owners.get(component_id)
    if direct is not None:
        return direct
    if "::" not in component_id:
        return None
    path, name = component_id.split("::", 1)
    while "." in name:
        name = name.rsplit(".", 1)[0]
        parent = f"{path}::{name}"
        if parent in owners:
            return owners[parent]
    return None


def strict_majority_candidates(votes: Counter[ModulePath]) -> list[dict[str, Any]]:
    total = sum(votes.values())
    if not total:
        return []
    top_votes = max(votes.values())
    leaders = sorted(path for path, count in votes.items() if count == top_votes)
    if len(leaders) > 1 or top_votes * 2 > total:
        return [{"module_path": list(path), "votes": top_votes, "total": total} for path in leaders]
    return []


def _same_location_votes(
    component_id: str,
    path: str,
    graph: Mapping[str, Any],
    owners: Mapping[str, ModulePath],
    *,
    same_file: bool,
) -> Counter[ModulePath]:
    votes: Counter[ModulePath] = Counter()
    for other_id, component in graph.items():
        if other_id == component_id:
            continue
        owner = resolve_owner(owners, other_id)
        if owner is None:
            continue
        other_path = normalize_component_path(_attr(component, "relative_path", ""))
        if same_file:
            matched = other_path == path
        else:
            matched = _parent_path(other_path) == _parent_path(path)
        if matched:
            votes[owner] += 1
    return votes


def neighbor_owner_votes(
    component_id: str,
    graph: Mapping[str, Any],
    owners: Mapping[str, ModulePath],
) -> Counter[ModulePath]:
    raw_dependencies = _attr(graph.get(component_id), "depends_on", set()) or set()
    neighbors = {str(item) for item in raw_dependencies}
    for other_id, component in graph.items():
        dependencies = _attr(component, "depends_on", set()) or set()
        if component_id in dependencies:
            neighbors.add(other_id)

    votes: Counter[ModulePath] = Counter()
    for neighbor in sorted(neighbors):
        if neighbor == component_id or neighbor not in graph:
            continue
        owner = resolve_owner(owners, neighbor)
        if owner is not None:
            votes[owner] += 1
    return votes


def _first_candidate_rule(
    component_id: str,
    path: str,
    graph: Mapping[str, Any],
    owners: Mapping[str, ModulePath],
) -> tuple[str | None, list[dict[str, Any]]]:
    same_file = _same_location_votes(component_id, path, graph, owners, same_file=True)
    if same_file:
        return "1:same_file", strict_majority_candidates(same_file)

    same_dir = _same_location_votes(component_id, path, graph, owners, same_file=False)
    if same_dir:
        return "2:same_dir", strict_majority_candidates(same_dir)

    neighbors = neighbor_owner_votes(component_id, graph, owners)
    if neighbors:
        return "3:neighbor_majority", strict_majority_candidates(neighbors)
    return None, []


def close_ownership(
    module_tree: Mapping[str, Any],
    current_components: Mapping[str, Any],
    previous_components: Mapping[str, Any] | None = None,
    changed_component_ids: Iterable[str] = (),
    deleted_component_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """返回稳定的 owner 候选，不修改组件图或模块树。"""
    owners = build_owner_map(module_tree)
    previous = previous_components or {}
    deleted_ids = set(deleted_component_ids)
    targets = sorted(set(changed_component_ids) | deleted_ids)
    effective: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for component_id in targets:
        if resolve_owner(owners, component_id) is not None:
            continue
        deleted = component_id in deleted_ids
        graph = previous if deleted else current_components
        component = graph.get(component_id)
        if component is None:
            continue
        path = normalize_component_path(_attr(component, "relative_path", ""))
        rule, candidates = _first_candidate_rule(component_id, path, graph, owners)
        resolved = len(candidates) == 1
        effective[component_id] = {
            "component_id": component_id,
            "relative_path": path,
            "deleted": deleted,
            "resolved": resolved,
            "rule": rule,
            "candidates": candidates,
        }
        if deleted and not resolved:
            if candidates:
                reason = "ambiguous_owner"
            elif rule is not None:
                reason = "no_strict_majority"
            else:
                reason = "no_owner_evidence"
            unresolved.append(
                {
                    "component_id": component_id,
                    "relative_path": path,
                    "reason": reason,
                }
            )

    return {
        "effective_owner_candidates": effective,
        "unresolved_deletions": unresolved,
    }
