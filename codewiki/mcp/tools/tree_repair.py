"""模块树确定性修复：重命名、删除、剪枝与受限新增归因。

本模块只操作内存中的副本。默认 observe 返回计划；只有调用方显式传
``apply=True`` 才返回修复后的树。它不写文件、不调用 LLM，也不执行重聚类。
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any, cast

from codewiki.mcp.tools.ownership import (
    ModulePath,
    build_owner_map,
    neighbor_owner_votes,
    normalize_component_path,
    resolve_owner,
    strict_majority_candidates,
)

DEFAULT_GROWTH_THRESHOLD = 0.33


def _attr(component: Any, name: str, default: Any = None) -> Any:
    if isinstance(component, Mapping):
        return component.get(name, default)
    return getattr(component, name, default)


def _parent(path: str) -> str:
    return PurePosixPath(path).parent.as_posix()


def _validate_tree(tree: Mapping[str, Any], path: tuple[str, ...] = ()) -> None:
    if not isinstance(tree, Mapping):
        raise ValueError(f"module node {'/'.join(path) or '<root>'} must be an object")
    for name, raw_info in tree.items():
        if not isinstance(name, str):
            raise ValueError("module names must be strings")
        node_path = (*path, name)
        if not isinstance(raw_info, Mapping):
            raise ValueError(f"module node {'/'.join(node_path)} must be an object")
        components = raw_info.get("components", [])
        if not isinstance(components, list) or not all(
            isinstance(component_id, str) for component_id in components
        ):
            raise ValueError(f"module node {'/'.join(node_path)} components must be a list")
        children = raw_info.get("children", {})
        if not isinstance(children, Mapping):
            raise ValueError(f"module node {'/'.join(node_path)} children must be an object")
        _validate_tree(children, node_path)


def _iter_nodes(
    tree: Mapping[str, Any], parents: tuple[str, ...] = ()
) -> Iterable[tuple[ModulePath, Mapping[str, Any]]]:
    for name, info in tree.items():
        path = (*parents, name)
        yield path, info
        children = info.get("children", {})
        if children:
            yield from _iter_nodes(children, path)


def _node_at(tree: Mapping[str, Any], path: ModulePath) -> Mapping[str, Any] | None:
    current: Mapping[str, Any] = tree
    node: Mapping[str, Any] | None = None
    for name in path:
        node = current.get(name)
        if not isinstance(node, Mapping):
            return None
        current = node.get("children", {})
    return node


def _is_leaf(info: Mapping[str, Any]) -> bool:
    return not info.get("children")


def _locations(tree: Mapping[str, Any], component_id: str) -> list[ModulePath]:
    return [path for path, info in _iter_nodes(tree) if component_id in info.get("components", [])]


def _assigned_ids(tree: Mapping[str, Any]) -> set[str]:
    return {
        component_id for _, info in _iter_nodes(tree) for component_id in info.get("components", [])
    }


def _normalize_changes(
    module_tree: Mapping[str, Any],
    components: Mapping[str, Any],
    previous_components: Mapping[str, Any] | None,
    component_changes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if component_changes is None:
        if previous_components is not None:
            from codewiki.mcp.tools.reference_index import classify_component_changes

            component_changes = classify_component_changes(previous_components, components)
        else:
            component_changes = {
                "added": sorted(set(components) - _assigned_ids(module_tree)),
                "deleted": [],
                "renamed": [],
            }
    added = sorted({str(item) for item in component_changes.get("added", []) or []})
    deleted = sorted({str(item) for item in component_changes.get("deleted", []) or []})
    renamed: list[dict[str, str]] = []
    for item in component_changes.get("renamed", []) or []:
        if not isinstance(item, Mapping):
            continue
        old_id = str(item.get("from") or "")
        new_id = str(item.get("to") or "")
        if old_id and new_id and old_id != new_id:
            renamed.append({"from": old_id, "to": new_id})
    renamed.sort(key=lambda item: (item["from"], item["to"]))
    return {"added": added, "deleted": deleted, "renamed": renamed}


def _candidate(
    component_id: str,
    tree: Mapping[str, Any],
    components: Mapping[str, Any],
    owners: Mapping[str, ModulePath],
) -> tuple[str | None, list[dict[str, Any]]]:
    component = components.get(component_id)
    if component is None:
        return None, []
    path = normalize_component_path(_attr(component, "relative_path", ""))

    same_file: Counter[ModulePath] = Counter()
    for other_id, owner in owners.items():
        other = components.get(other_id)
        if other_id == component_id or other is None:
            continue
        if normalize_component_path(_attr(other, "relative_path", "")) == path:
            same_file[owner] += 1
    if same_file:
        candidates = strict_majority_candidates(same_file)
        if len(candidates) == 1:
            return "1:same_file", candidates

    same_dir: Counter[ModulePath] = Counter()
    for other_id, owner in owners.items():
        other = components.get(other_id)
        if other_id == component_id or other is None:
            continue
        if _parent(normalize_component_path(_attr(other, "relative_path", ""))) != _parent(path):
            continue
        node = _node_at(tree, owner)
        if node is not None and _is_leaf(node):
            same_dir[owner] += 1
    if same_dir:
        candidates = [
            {"module_path": list(owner), "votes": votes}
            for owner, votes in sorted(same_dir.items())
        ]
        return "2:same_dir", candidates

    neighbor_votes = neighbor_owner_votes(component_id, components, owners)
    if neighbor_votes:
        return "3:neighbor_majority", strict_majority_candidates(neighbor_votes)
    return None, []


def _prune_empty(tree: dict[str, Any], path: ModulePath = ()) -> list[ModulePath]:
    removed: list[ModulePath] = []
    for name in list(tree):
        info = tree[name]
        children = info.get("children", {})
        removed.extend(_prune_empty(children, (*path, name)))
        if not info.get("components") and not children:
            removed.append((*path, name))
            del tree[name]
    return removed


def repair_module_tree(
    module_tree: Mapping[str, Any],
    current_components: Mapping[str, Any],
    previous_components: Mapping[str, Any] | None = None,
    component_changes: Mapping[str, Any] | None = None,
    *,
    tracked_component_ids: Iterable[str] | None = None,
    apply: bool = False,
    growth_threshold: float = DEFAULT_GROWTH_THRESHOLD,
) -> dict[str, Any]:
    """返回确定性修复计划；``apply=True`` 时附带修复后的树副本。"""
    if not 0 < growth_threshold <= 1:
        raise ValueError("growth_threshold must be in (0, 1]")
    if not all(isinstance(component_id, str) for component_id in current_components):
        raise ValueError("component ids must be strings")
    _validate_tree(module_tree)
    # Validate the submitted tree before rename/delete can hide a duplicate.
    build_owner_map(module_tree)
    changes = _normalize_changes(
        module_tree, current_components, previous_components, component_changes
    )
    tracked = (
        set(current_components) if tracked_component_ids is None else set(tracked_component_ids)
    )
    repaired = copy.deepcopy(dict(module_tree))
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. rename：只在同一位置替换，目标已被占用时保留原树并显式报告冲突。
    for item in changes["renamed"]:
        old_id, new_id = item["from"], item["to"]
        locations = _locations(repaired, old_id)
        if not locations:
            operations.append(
                {
                    "action": "rename",
                    "component_id": old_id,
                    "new_component_id": new_id,
                    "module_paths": [],
                    "status": "not_assigned",
                }
            )
            if new_id in current_components and new_id not in _assigned_ids(repaired):
                # A missing rename source must not make the current target vanish;
                # route it through the normal tracked add/orphan rules below.
                changes["added"].append(new_id)
            continue
        if new_id in _assigned_ids(repaired):
            operations.append(
                {
                    "action": "rename",
                    "component_id": old_id,
                    "new_component_id": new_id,
                    "module_paths": [list(path) for path in locations],
                    "status": "conflict",
                }
            )
            warnings.append(f"rename conflict: {old_id} -> {new_id}; target already assigned")
            continue
        for _, info in _iter_nodes(repaired):
            mutable_info = cast(dict[str, Any], info)
            components = mutable_info.get("components", [])
            mutable_info["components"] = [new_id if cid == old_id else cid for cid in components]
        operations.append(
            {
                "action": "rename",
                "component_id": old_id,
                "new_component_id": new_id,
                "module_paths": [list(path) for path in locations],
                "status": "planned",
            }
        )

    # 2. delete：只删除 diff 明确标出的组件，不把未知 ID 当成可猜的删除。
    for component_id in changes["deleted"]:
        locations = _locations(repaired, component_id)
        for _, info in _iter_nodes(repaired):
            mutable_info = cast(dict[str, Any], info)
            mutable_info["components"] = [
                cid for cid in mutable_info.get("components", []) if cid != component_id
            ]
        operations.append(
            {
                "action": "delete",
                "component_id": component_id,
                "module_paths": [list(path) for path in locations],
                "status": "planned" if locations else "not_assigned",
            }
        )

    # 3. prune：后序删除空节点，父节点随最后一个子节点一并消失。
    deleted_nodes = _prune_empty(repaired)
    operations.extend(
        {"action": "prune", "module_path": list(path), "status": "planned"}
        for path in deleted_nodes
    )

    # 4. add：同文件严格多数 → 同目录唯一 leaf → 一跳邻居严格多数。
    owners = build_owner_map(repaired)
    unplaced: list[str] = []
    added_by_path: dict[ModulePath, set[str]] = {}
    for component_id in sorted(set(changes["added"])):
        existing_owner = resolve_owner(owners, component_id)
        if existing_owner is not None:
            operations.append(
                {
                    "action": "add",
                    "component_id": component_id,
                    "rule": "already_assigned",
                    "module_path": list(existing_owner),
                    "candidates": [],
                    "status": "already_assigned",
                }
            )
            continue
        if component_id not in current_components:
            operations.append(
                {
                    "action": "add",
                    "component_id": component_id,
                    "rule": None,
                    "module_path": None,
                    "candidates": [],
                    "status": "missing_component",
                }
            )
            unplaced.append(component_id)
            continue
        if component_id not in tracked:
            operations.append(
                {
                    "action": "add",
                    "component_id": component_id,
                    "rule": "untracked",
                    "module_path": None,
                    "candidates": [],
                    "status": "untracked",
                }
            )
            unplaced.append(component_id)
            continue
        rule, candidates = _candidate(component_id, repaired, current_components, owners)
        if len(candidates) == 1:
            module_path = tuple(candidates[0]["module_path"])
            node = _node_at(repaired, module_path)
            assert node is not None
            node["components"].append(component_id)
            owners[component_id] = module_path
            added_by_path.setdefault(module_path, set()).add(component_id)
            status = "planned"
        else:
            module_path = None
            status = "orphan"
            unplaced.append(component_id)
        operations.append(
            {
                "action": "add",
                "component_id": component_id,
                "rule": rule,
                "module_path": list(module_path) if module_path is not None else None,
                "candidates": candidates,
                "status": status,
            }
        )

    # 5. growth：只标记新增占比，不创建新 leaf，也不调用聚类器。
    growth: dict[str, float] = {}
    growth_flagged: list[list[str]] = []
    for path, info in _iter_nodes(repaired):
        now = set(info.get("components", []))
        entered = added_by_path.get(path, set())
        if not _is_leaf(info) or not entered or not now:
            continue
        ratio = len(entered) / len(now)
        growth["/".join(path)] = round(ratio, 4)
        if ratio >= growth_threshold:
            growth_flagged.append(list(path))
            warnings.append(
                f"leaf growth threshold exceeded: {'/'.join(path)} "
                f"({len(entered)}/{len(now)} = {ratio:.2%})"
            )

    summary = {
        "renamed": sum(op["action"] == "rename" and op["status"] == "planned" for op in operations),
        "deleted": sum(op["action"] == "delete" and op["status"] == "planned" for op in operations),
        "pruned": len(deleted_nodes),
        "added": sum(op["action"] == "add" and op["status"] == "planned" for op in operations),
        "unplaced": len(unplaced),
    }
    result: dict[str, Any] = {
        "mode": "apply" if apply else "observe",
        "operations": operations,
        "summary": summary,
        "unplaced_component_ids": sorted(set(unplaced)),
        "deleted_nodes": [list(path) for path in deleted_nodes],
        "growth": growth,
        "growth_flagged": growth_flagged,
        "warnings": warnings,
    }
    if apply:
        result["repaired_tree"] = repaired
    return result
