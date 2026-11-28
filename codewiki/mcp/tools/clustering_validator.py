"""B5：模块聚类的确定性质量诊断，不调用 LLM、不修改模块树。

token 口径是「模块完整 scope 文件的当前文本字符数 / chars_per_token」，
不是组件 ``source_code`` 切片之和，也不是计费精度。缺文件、不可读或逃逸
仓库的文件显式记为 ``unmeasured_files``，绝不按 0 token 参与微页判断。

默认阈值来自本仓 ``first_module_tree.json`` 的 22 个 leaf 实测：完整文件
估算中位数约 12464、P90 约 31725 token；取 1000/32000 作为可配置的决策
提示。0 表示关闭对应诊断，阈值不是跨仓库通用结论。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from stat import S_ISREG
from typing import Any, Protocol

from codewiki.mcp.tools.injection_budget import estimate_tokens
from codewiki.mcp.tools.ownership import normalize_component_path

_DEFAULT_CONFIG = {
    "enabled": True,
    "chars_per_token": 4,
    "min_leaf_tokens": 1000,
    "max_leaf_tokens": 32000,
}


class ComponentItems(Protocol):
    """B5 只需要的轻量组件集合接口（兼容 LazyComponentStore 与 dict）。"""

    def items(self) -> Iterable[tuple[str, Any]]: ...


def _attr(component: Any, name: str, default: Any = None) -> Any:
    if isinstance(component, Mapping):
        return component.get(name, default)
    return getattr(component, name, default)


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def load_clustering_validation_config(schema: Mapping[str, Any] | None) -> dict[str, Any]:
    """从 ``schema.yaml conventions.clustering_validation`` 解析诊断配置。"""
    cfg = dict(_DEFAULT_CONFIG)
    conventions = (schema or {}).get("conventions") or {}
    raw = conventions.get("clustering_validation") if isinstance(conventions, Mapping) else None
    if not isinstance(raw, Mapping):
        return cfg
    if raw.get("enabled") is not None:
        cfg["enabled"] = bool(raw["enabled"])
    try:
        chars_per_token = int(raw.get("chars_per_token") or 0)
    except (TypeError, ValueError):
        chars_per_token = 0
    if chars_per_token > 0:
        cfg["chars_per_token"] = chars_per_token
    for key in ("min_leaf_tokens", "max_leaf_tokens"):
        if raw.get(key) is not None:
            cfg[key] = _nonnegative_int(raw[key], cfg[key])
    return cfg


def _validated_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    cfg = dict(_DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    for key in ("chars_per_token", "min_leaf_tokens", "max_leaf_tokens"):
        try:
            cfg[key] = int(cfg[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if cfg[key] < 0:
            raise ValueError(f"{key} must be non-negative")
    if cfg["chars_per_token"] <= 0:
        raise ValueError("chars_per_token must be positive")
    minimum = cfg["min_leaf_tokens"]
    maximum = cfg["max_leaf_tokens"]
    if minimum and maximum and minimum > maximum:
        raise ValueError("min_leaf_tokens must not exceed max_leaf_tokens")
    cfg["enabled"] = bool(cfg.get("enabled", True))
    return cfg


def _component_file(component_id: str, component: Any) -> str:
    raw = _attr(component, "relative_path", "") or component_id.split("::", 1)[0]
    return normalize_component_path(raw)


def measure_scope_file_tokens(
    repo_path: str | Path,
    components: ComponentItems,
    chars_per_token: int,
    *,
    cache: MutableMapping[str, tuple[tuple[int, int, int, int], int]] | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    """读取组件涉及文件的完整文本；不可测文件返回显式原因。

    文件按块计数，不在内存中拼出完整源码。可选缓存以路径为键，以
    ``(mtime_ns, size, inode, chars_per_token)`` 为版本，重复保存且文件未变时
    跳过读取；缓存仅存在会话内存，不作为跨会话事实源。
    """
    root = Path(repo_path).expanduser().resolve()
    files = sorted(
        {
            path
            for component_id, component in components.items()
            if (path := _component_file(str(component_id), component))
        }
    )
    counts: dict[str, int] = {}
    unmeasured: dict[str, str] = {}
    for relative in files:
        candidate = Path(relative)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except ValueError:
            unmeasured[relative] = "outside_repo"
            continue
        except (OSError, RuntimeError):
            unmeasured[relative] = "unreadable"
            continue
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            unmeasured[relative] = "missing"
            continue
        except OSError:
            unmeasured[relative] = "unreadable"
            continue
        if not S_ISREG(stat.st_mode):
            unmeasured[relative] = "not_file"
            continue
        cache_key = str(resolved)
        signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino, chars_per_token)
        cached = cache.get(cache_key) if cache is not None else None
        if cached is not None and cached[0] == signature:
            counts[relative] = cached[1]
            continue
        length = 0
        try:
            with resolved.open("r", encoding="utf-8", errors="replace") as source:
                while chunk := source.read(1024 * 1024):
                    length += len(chunk)
        except OSError:
            unmeasured[relative] = "unreadable"
            continue
        count = estimate_tokens(length, chars_per_token)
        counts[relative] = count
        if cache is not None:
            cache[cache_key] = (signature, count)
    return counts, unmeasured


def validate_clustering(
    module_tree: Mapping[str, Any],
    components: ComponentItems,
    file_token_counts: Mapping[str, int],
    *,
    unmeasured_files: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """诊断微页、超大 leaf、同文件跨 leaf、漏文件与未知组件。

    输入树只读；所有路径与诊断顺序稳定。父模块可聚合 children 的 scope，
    但只有 leaf 是互斥文档 owner，父模块直接登记组件不构成第二 leaf owner。
    """
    cfg = _validated_config(config)
    normalized_counts = {
        normalize_component_path(path): max(0, int(value))
        for path, value in file_token_counts.items()
    }
    reasons = {
        normalize_component_path(path): str(reason)
        for path, reason in (unmeasured_files or {}).items()
    }

    # LazyComponentStore.items() yields lightweight path metadata; indexing it
    # would deserialize a full Node from SQLite for every assigned component.
    component_records = {str(raw_id): component for raw_id, component in components.items()}

    # 历史树可能使用 Windows 分隔符；仅当规范化 ID 唯一时才兼容解析。
    normalized_ids: dict[str, list[str]] = {}
    for component_id in component_records:
        normalized_ids.setdefault(component_id.replace("\\", "/"), []).append(component_id)

    def resolve_component(raw_id: Any) -> str | None:
        component_id = str(raw_id)
        if component_id in component_records:
            return component_id
        matches = normalized_ids.get(component_id.replace("\\", "/"), [])
        return matches[0] if len(matches) == 1 else None

    file_components: dict[str, set[str]] = {}
    unlocated_component_ids: set[str] = set()
    for component_id, component in component_records.items():
        path = _component_file(component_id, component)
        if path:
            file_components.setdefault(path, set()).add(component_id)
        else:
            unlocated_component_ids.add(component_id)

    nodes: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    unknown_component_ids: set[str] = set()
    assigned_files: set[str] = set()
    leaf_file_owners: dict[str, set[tuple[str, ...]]] = {}
    unmeasured_uses: dict[str, set[tuple[str, ...]]] = {}

    def walk(tree: Mapping[str, Any], parents: tuple[str, ...] = ()) -> None:
        for name in tree:
            if not isinstance(name, str):
                raise ValueError("module names must be strings")
        for name in sorted(tree):
            info = tree[name]
            if not isinstance(info, Mapping):
                raise ValueError(f"module node {name!r} must be an object")
            raw_components = info.get("components", [])
            children = info.get("children", {})
            if not isinstance(raw_components, list):
                raise ValueError(f"module node {name!r} components must be a list")
            if not isinstance(children, Mapping):
                raise ValueError(f"module node {name!r} children must be an object")
            path = (*parents, name)
            files: set[str] = set()
            for raw_id in raw_components:
                component_id = resolve_component(raw_id)
                if component_id is None:
                    unknown_component_ids.add(str(raw_id))
                    continue
                file_path = _component_file(component_id, component_records[component_id])
                if file_path:
                    files.add(file_path)
            assigned_files.update(files)
            node = {
                "path": path,
                "files": files,
                "is_leaf": not children,
                "has_component_ids": bool(raw_components),
            }
            nodes.append(node)
            if children:
                walk(children, path)
            else:
                leaves.append(node)
                for file_path in files:
                    leaf_file_owners.setdefault(file_path, set()).add(path)

    walk(module_tree)

    # Parent scope is the union of its own and descendant files. Reverse DFS
    # order ensures children have already computed their aggregate scope.
    children_by_parent: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for node in nodes:
        if node["path"]:
            children_by_parent.setdefault(node["path"][:-1], []).append(node)
    for node in reversed(nodes):
        aggregate = set(node["files"])
        for child in children_by_parent.get(node["path"], []):
            aggregate.update(child["scope_files"])
        node["scope_files"] = aggregate
    module_estimates = []
    for node in nodes:
        files = sorted(node["scope_files"])
        measured = [file_path for file_path in files if file_path in normalized_counts]
        module_estimates.append(
            {
                "module_path": list(node["path"]),
                "is_leaf": node["is_leaf"],
                "file_count": len(files),
                "estimated_tokens": sum(normalized_counts[file_path] for file_path in measured),
                "measured_file_count": len(measured),
                "unmeasured_file_count": len(files) - len(measured),
                "token_estimate_is_partial": len(measured) < len(files),
            }
        )

    for node in nodes:
        for file_path in node["files"]:
            if file_path not in normalized_counts:
                unmeasured_uses.setdefault(file_path, set()).add(node["path"])

    micro_pages: list[dict[str, Any]] = []
    oversized_leaves: list[dict[str, Any]] = []
    for node in leaves:
        files = sorted(node["files"])
        measured = [file_path for file_path in files if file_path in normalized_counts]
        estimated = sum(normalized_counts[file_path] for file_path in measured)
        partial = len(measured) < len(files)
        entry = {
            "module_path": list(node["path"]),
            "files": files,
            "file_count": len(files),
            "estimated_tokens": estimated,
            "unmeasured_file_count": len(files) - len(measured),
            "token_estimate_is_partial": partial,
        }
        # 完全无法测量的非空 leaf 不伪装成 0-token 微页；未知 ID 另有诊断。
        if not node["has_component_ids"] and cfg["min_leaf_tokens"]:
            micro_pages.append(
                {
                    **entry,
                    "suggestion": "Assign indexed components to this leaf, or remove the empty module.",
                }
            )
        elif (
            measured
            and not partial
            and cfg["min_leaf_tokens"]
            and estimated < cfg["min_leaf_tokens"]
        ):
            micro_pages.append(
                {
                    **entry,
                    "suggestion": "Merge this leaf with a related module, or add the missing source files to its scope.",
                }
            )
        if measured and cfg["max_leaf_tokens"] and estimated > cfg["max_leaf_tokens"]:
            oversized_leaves.append(
                {
                    **entry,
                    "suggestion": "Split this leaf by a cohesive responsibility before generating its source-heavy prompt.",
                }
            )

    split_files = [
        {
            "file": file_path,
            "leaf_modules": [list(path) for path in sorted(leaf_file_owners[file_path])],
            "component_ids": sorted(file_components.get(file_path, set())),
            "suggestion": "Assign all components from this file to one leaf module, or split the source file first.",
        }
        for file_path in sorted(leaf_file_owners)
        if len(leaf_file_owners[file_path]) > 1
    ]
    uncovered_files = [
        {
            "file": file_path,
            "component_ids": sorted(file_components[file_path]),
            "suggestion": "Assign these indexed components to a module, or explicitly exclude the file from documentation scope.",
        }
        for file_path in sorted(set(file_components) - assigned_files)
    ]
    unmeasured = [
        {
            "file": file_path,
            "reason": reasons.get(file_path, "not_measured"),
            "module_paths": [list(path) for path in sorted(unmeasured_uses.get(file_path, set()))],
        }
        for file_path in sorted(set(reasons) | set(unmeasured_uses))
    ]
    unknown = sorted(unknown_component_ids)
    unlocated = sorted(unlocated_component_ids)
    issue_count = sum(
        len(items)
        for items in (
            micro_pages,
            oversized_leaves,
            split_files,
            uncovered_files,
            unmeasured,
            unknown,
            unlocated,
        )
    )
    return {
        "mode": "observe",
        "status": "issues" if issue_count else "ok",
        "token_basis": "full_scope_file_text",
        "chars_per_token": cfg["chars_per_token"],
        "thresholds": {
            "min_leaf_tokens": cfg["min_leaf_tokens"],
            "max_leaf_tokens": cfg["max_leaf_tokens"],
        },
        "module_count": len(nodes),
        "leaf_count": len(leaves),
        "indexed_file_count": len(file_components),
        "module_estimates": module_estimates,
        "micro_pages": micro_pages,
        "oversized_leaves": oversized_leaves,
        "split_files": split_files,
        "uncovered_files": uncovered_files,
        "unknown_component_ids": unknown,
        "unlocated_component_ids": unlocated,
        "unmeasured_files": unmeasured,
        "summary": {
            "issue_count": issue_count,
            "micro_page_count": len(micro_pages),
            "oversized_leaf_count": len(oversized_leaves),
            "split_file_count": len(split_files),
            "uncovered_file_count": len(uncovered_files),
            "unknown_component_count": len(unknown),
            "unlocated_component_count": len(unlocated),
            "unmeasured_file_count": len(unmeasured),
        },
        "suggestion": (
            "Review the diagnostics and re-save a corrected module tree before generation; "
            "this validator did not modify the tree."
            if issue_count
            else "No deterministic clustering issues found; continue with the submitted tree."
        ),
    }
