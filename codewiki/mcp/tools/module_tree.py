"""MCP tools: save_module_tree + get_processing_order.

The IDE agent decides how to group components into modules (clustering)
using its own LLM.  These tools persist that decision and compute the
leaf-first processing order for documentation generation.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path as _Path
from typing import Any

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.file_param import read_json_param
from codewiki.mcp.tools.workspace_result import resolve_session
from codewiki.mcp.workspace import SessionWorkspace
from codewiki.src.config import (
    FIRST_MODULE_TREE_FILENAME,
    MODULE_TREE_FILENAME,
    meta_join,
    meta_resolve,
)

logger = logging.getLogger(__name__)


def _get_processing_order(
    module_tree: dict[str, Any], parent_path: list[str] | None = None
) -> list[dict[str, Any]]:
    """Compute leaf-first processing order from a module tree.

    Returns a list of dicts with module path, name, leaf status, and
    component/children info.
    """
    order: list[dict[str, Any]] = []

    def _collect(tree: dict[str, Any], path: list[str]) -> None:
        for module_name, module_info in tree.items():
            current_path = path + [module_name]
            children = module_info.get("children", {})
            has_children = isinstance(children, dict) and len(children) > 0

            if has_children:
                _collect(children, current_path)
                order.append(
                    {
                        "module": module_name,
                        "path": current_path,
                        "is_leaf": False,
                        "children": list(children.keys()),
                        "components": module_info.get("components", []),
                    }
                )
            else:
                order.append(
                    {
                        "module": module_name,
                        "path": current_path,
                        "is_leaf": True,
                        "components": module_info.get("components", []),
                    }
                )

    _collect(module_tree, parent_path if parent_path is not None else [])
    return order


def _collect_component_ids(module_tree: dict[str, Any]) -> set:
    """Return the set of all component ids referenced across the module tree.

    Walks every module (and nested ``children``) and collects the entries of
    each module's ``components`` list.
    """
    ids: set = set()

    def _walk(tree: dict[str, Any]) -> None:
        for module_info in tree.values():
            ids.update(module_info.get("components", []) or [])
            children = module_info.get("children", {})
            if isinstance(children, dict) and children:
                _walk(children)

    _walk(module_tree)
    return ids


def _validate_module_tree(
    module_tree: dict[str, Any],
    known_ids: set,
) -> tuple[list[str], list[str]]:
    """Check the tree's component ids against the analysis component index.

    Returns ``(unmatched_ids, leftover_ids)``:
      * ``unmatched_ids``: ids referenced by the tree that do not exist in the
        index (typos / drift) -- they would be silently omitted from docs.
      * ``leftover_ids``: ids that exist in the index but are not assigned to
        any module (a coverage gap -- they get no module doc).

    Ported from upstream FSoft-AI4Code/CodeWiki (PR by LiberiFatali).
    """
    assigned = _collect_component_ids(module_tree)
    unmatched = sorted(assigned - known_ids)
    leftover = sorted(known_ids - assigned)
    return unmatched, leftover


def _save_and_compute_order(
    output_dir: str,
    module_tree: dict[str, Any],
    *,
    session: SessionState | None = None,
    workspace: SessionWorkspace | None = None,
) -> str:
    """Persist a module tree and compute the leaf-first processing order.

    Shared by ``handle_save_module_tree``.
    """
    # Save both immutable snapshot and mutable working copy
    first_path = meta_join(output_dir, FIRST_MODULE_TREE_FILENAME)
    working_path = meta_join(output_dir, MODULE_TREE_FILENAME)

    os.makedirs(os.path.dirname(first_path), exist_ok=True)

    with open(first_path, "w", encoding="utf-8") as f:
        json.dump(module_tree, f, indent=2, ensure_ascii=False)
    with open(working_path, "w", encoding="utf-8") as f:
        json.dump(module_tree, f, indent=2, ensure_ascii=False)

    # Cache in session if available
    if session is not None:
        session.module_tree = module_tree

    # Resolve the workspace once: explicit arg first, then the session's.
    ws = workspace
    if ws is None and session is not None and session.workspace is not None:
        ws = session.workspace

    # Validate the tree against the analysis component index so orphaned /
    # stale ids surface loudly instead of being silently dropped from docs.
    validation = None
    warning = ""
    if session is not None:
        known_ids = set(session.components.keys())
        unmatched_ids, leftover_ids = _validate_module_tree(module_tree, known_ids)
        validation = {
            "unmatched_ids": unmatched_ids,
            "unmatched_count": len(unmatched_ids),
            "leftover_component_ids": leftover_ids,
            "leftover_component_count": len(leftover_ids),
        }
        if ws is not None:
            ws.write_json("module_tree_validation.json", validation)
        if unmatched_ids or leftover_ids:
            warnings: list[str] = []
            if unmatched_ids:
                warnings.append(
                    f"{len(unmatched_ids)} component id(s) in the module tree do not "
                    f"exist in the analysis index and will be omitted from docs: "
                    f"{unmatched_ids}"
                )
            if leftover_ids:
                warnings.append(
                    f"{len(leftover_ids)} indexed component(s) are assigned to no "
                    f"module and will receive no documentation: {leftover_ids}"
                )
            warning = " ".join(warnings)
            logger.warning("save_module_tree: %s", warning)

    # Compute processing order and write to workspace file
    order = _get_processing_order(module_tree)
    order_file = None
    if ws is not None:
        order_path = ws.write_json("processing_order.json", order)
        order_file = str(order_path)

    # Count total components assigned and total modules (recursively)
    total_assigned = 0
    total_modules = 0

    def _count(tree):
        nonlocal total_assigned, total_modules
        for m in tree.values():
            total_modules += 1
            total_assigned += len(m.get("components", []))
            _count(m.get("children", {}))

    _count(module_tree)

    result = {
        "status": "saved",
        "module_count": total_modules,
        "total_components_assigned": total_assigned,
        "tree_path": working_path,
        "first_tree_path": first_path,
        "processing_order_file": order_file,
        "hint": (
            "Read the processing_order.json file for the leaf-first generation order. "
            "Process leaf modules first (is_leaf=true), then parent modules. "
            "For each leaf module: get_prompt('system_leaf') + read_code_components + write_doc_file. "
            "For each parent module: get_prompt('overview_module') + write_doc_file."
        ),
    }
    if validation is not None:
        result["validation"] = validation
    if warning:
        result["warning"] = warning
    return json.dumps(result, indent=2, ensure_ascii=False)


def handle_save_module_tree(
    arguments: dict[str, Any],
    store: SessionStore,
) -> str:
    """Persist the IDE agent's clustering result as the module tree."""
    repo_path = arguments.get("repo_path")
    if not repo_path:
        return json.dumps({"error": "repo_path is required."})
    rp = (
        str(_Path(repo_path).expanduser().resolve())
        if _Path(repo_path).is_absolute()
        else str((_Path.cwd() / repo_path).expanduser().resolve())
    )

    # Try to reuse active session for workspace/caching, fall back to standalone
    session = resolve_session(arguments, store)

    # Respect explicit output_dir from arguments, then session, then default
    explicit_od = arguments.get("output_dir")
    if explicit_od:
        output_dir = (
            str(_Path(explicit_od).expanduser().resolve())
            if _Path(explicit_od).is_absolute()
            else str((_Path(rp) / explicit_od).expanduser().resolve())
        )
    elif session is not None and session.output_dir:
        output_dir = session.output_dir
    else:
        output_dir = str(_Path(rp) / "repowiki")

    workspace = (
        session.workspace if session is not None else SessionWorkspace(_Path(rp), "standalone")
    )

    module_tree = read_json_param(arguments, "module_tree")
    if module_tree is None:
        return json.dumps(
            {"error": "module_tree or module_tree_file is required."}, ensure_ascii=False
        )
    return _save_and_compute_order(output_dir, module_tree, session=session, workspace=workspace)


def handle_get_processing_order(
    arguments: dict[str, Any],
    store: SessionStore,
) -> str:
    """Write the leaf-first processing order to a workspace file and return its path."""
    repo_path = arguments.get("repo_path")
    if not repo_path:
        return json.dumps({"error": "repo_path is required."})
    rp = (
        str(_Path(repo_path).expanduser().resolve())
        if _Path(repo_path).is_absolute()
        else str((_Path.cwd() / repo_path).expanduser().resolve())
    )

    session = resolve_session(arguments, store)
    output_dir = (
        session.output_dir
        if session is not None and session.output_dir
        else str(_Path(rp) / "repowiki")
    )
    workspace = (
        session.workspace if session is not None else SessionWorkspace(_Path(rp), "standalone")
    )

    # Try session cache first, then disk
    module_tree = session.module_tree if session is not None else {}
    if not module_tree:
        tree_path = meta_resolve(output_dir, MODULE_TREE_FILENAME)
        if os.path.exists(tree_path):
            with open(tree_path, encoding="utf-8") as f:
                module_tree = json.load(f)
            if session is not None:
                session.module_tree = module_tree
        else:
            return json.dumps({"error": "Module tree not found. Call save_module_tree first."})

    order = _get_processing_order(module_tree)

    # Write to workspace file
    order_file = None
    if workspace is not None:
        order_path = workspace.write_json("processing_order.json", order)
        order_file = str(order_path)

    # Count all modules recursively
    def _count_modules(tree: dict[str, Any]) -> int:
        count = 0
        for info in tree.values():
            count += 1
            children = info.get("children", {})
            if isinstance(children, dict):
                count += _count_modules(children)
        return count

    result = {
        "module_count": _count_modules(module_tree),
        "processing_order_file": order_file,
        "hint": "Read the processing_order.json file for the full leaf-first order.",
    }
    return json.dumps(result, indent=2, ensure_ascii=False)
