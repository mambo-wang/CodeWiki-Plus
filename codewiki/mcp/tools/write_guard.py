"""Observe/enforce gate for host-agent writes against ``change_plan``.

This is an operational contract, not a security boundary: a host with direct
filesystem access can bypass MCP.  Path traversal and symlink escapes remain the
responsibility of ``page_router`` before this module is called.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from codewiki.mcp.tools.change_plan import (
    OP_TYPES,
    SCHEMA_VERSION,
    STATUSES,
    compute_plan_hash,
    match_legacy_update_ops,
)
from codewiki.mcp.tools.page_router import PAGE_TYPE_DIRS


def _page_key(output_dir: str | Path, doc_path: Path) -> str:
    try:
        return doc_path.resolve().relative_to(Path(output_dir).resolve()).as_posix()
    except (OSError, ValueError):
        return doc_path.name


def _expected_page_key(filename: str, page_type: str, module_repo: str | None) -> str:
    stem = Path(filename).stem
    if stem == "overview":
        return "wiki/overview.md"
    if page_type == "module":
        prefix = "wiki/modules/"
        if module_repo:
            prefix += module_repo.strip("/") + "/"
        return prefix + stem + ".md"
    return f"wiki/{PAGE_TYPE_DIRS.get(page_type, PAGE_TYPE_DIRS['module'])}/{stem}.md"


def _matches_target(
    target: str,
    *,
    filename: str,
    page_key: str,
    page_type: str,
    module_repo: str | None,
) -> bool:
    """Match one explicit routed page, never a directory/glob or bare stem."""
    wanted = PurePosixPath(target.replace("\\", "/").strip()).as_posix()
    if wanted in {".", ""}:
        return False
    # An exact path is still scoped to the current centralized repo partition;
    # otherwise the host could authorize one repo's page with another's target.
    if page_type == "module" and Path(filename).stem != "overview":
        if not _is_module_page(page_key, module_repo):
            return False
    if wanted == page_key:
        return True
    supplied = PurePosixPath(filename.replace("\\", "/").strip()).as_posix()
    if wanted != supplied:
        return False
    expected = _expected_page_key(filename, page_type, module_repo)
    # A bare legacy ``Foo.md`` remains addressable, but an arbitrary nested
    # same-stem page must be named with its wiki-relative path.
    return page_key == expected or ("/" not in page_key and page_key == supplied)


def _is_module_page(page_key: str, module_repo: str | None) -> bool:
    parts = PurePosixPath(page_key).parts
    if len(parts) == 1:
        return True  # legacy root-level module page
    if len(parts) < 3 or parts[:2] != ("wiki", "modules"):
        return False
    if module_repo:
        return len(parts) == 4 and parts[2] == module_repo
    return True


def _matches_module(
    op: Mapping[str, Any],
    page_type: str,
    filename: str,
    page_key: str,
    module_repo: str | None,
) -> bool:
    if op.get("op") == "update_page" or page_type != "module":
        return False
    stem = Path(filename).stem
    if str(op.get("page") or "") != stem:
        return False
    planned_key = str(op.get("page_key") or "").replace("\\", "/").strip()
    if planned_key:
        return planned_key == page_key
    expected = _expected_page_key(filename, page_type, module_repo)
    # Legacy structural ops named only a stem. Address the canonical routed
    # page (or its root-level legacy form), never an arbitrary nested same-stem.
    return page_key in {expected, stem + ".md"}


def _matches_update(op: Mapping[str, Any], page_key: str) -> bool:
    if op.get("op") != "update_page":
        return False
    planned_key = str(op.get("page_key") or "").replace("\\", "/").strip()
    return bool(planned_key and planned_key == page_key)


def _valid_plan(plan: Mapping[str, Any]) -> bool:
    if type(plan.get("schema_version")) is not int or plan.get("schema_version") != SCHEMA_VERSION:
        return False
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return False
    for op in ops:
        if not isinstance(op, Mapping):
            return False
        if op.get("op") not in OP_TYPES:
            return False
        if not isinstance(op.get("page"), str) or not op.get("page"):
            return False
        if "status" in op and op.get("status") not in STATUSES:
            return False
        if op.get("page_key") is not None and not isinstance(op.get("page_key"), str):
            return False
    expected_hash = compute_plan_hash(dict(plan))
    return isinstance(plan.get("plan_hash"), str) and plan.get("plan_hash") == expected_hash


def evaluate_page_write(
    plan: Mapping[str, Any] | None,
    output_dir: str | Path,
    *,
    doc_path: Path,
    filename: str,
    page_type: str,
    mode: str = "observe",
    target: str | None = None,
    tool: str,
    module_repo: str | None = None,
) -> dict[str, Any]:
    """Classify a resolved page write and return its deterministic decision.

    ``failed`` and ``skipped`` are pending, matching ``plan_summary``.  A plan
    that is missing/corrupt is ``unavailable`` rather than proof of an unplanned
    write; observe preserves legacy behavior while enforce fails closed unless
    the host explicitly names the current target.
    """
    normalized_mode = str(mode or "observe").strip().lower()
    if normalized_mode not in {"observe", "enforce"}:
        raise ValueError("write_guard_mode must be 'observe' or 'enforce'")

    page_key = _page_key(output_dir, doc_path)
    target_matches = bool(
        target
        and _matches_target(
            target,
            filename=filename,
            page_key=page_key,
            page_type=page_type,
            module_repo=module_repo,
        )
    )
    decision: dict[str, Any] = {
        "mode": normalized_mode,
        "plan_status": "loaded" if plan is not None else "missing",
        "classification": "unavailable",
        "outcome": "allowed",
        "allowed_by": "observe" if normalized_mode == "observe" else None,
        "unplanned_write": False,
        "page_key": page_key,
        "reason": "change_plan_unavailable",
    }
    if plan is None or not _valid_plan(plan):
        decision["plan_status"] = "missing"
        if normalized_mode == "observe" or target_matches:
            if target_matches:
                decision["allowed_by"] = "current_target"
        else:
            decision["outcome"] = "blocked"
        return decision

    ops = plan["ops"]
    legacy_updates = {id(op) for op in match_legacy_update_ops(ops, page_key, filename)}
    matching = [
        op
        for op in ops
        if _matches_module(op, page_type, filename, page_key, module_repo)
        or _matches_update(op, page_key)
        or id(op) in legacy_updates
    ]
    writable = [op for op in matching if op.get("op") != "delete_subtree"]
    pending = [op for op in writable if str(op.get("status") or "pending") != "done"]

    allowed_by: str | None
    if pending:
        classification = "pending"
        allowed = True
        allowed_by = "pending_pages"
        reason = "pending_change_plan_operator"
    elif writable:
        classification = "planned_not_pending"
        allowed = normalized_mode == "observe"
        allowed_by = "observe" if allowed else None
        reason = "operator_already_done"
    elif matching:
        classification = "delete_only"
        allowed = normalized_mode == "observe"
        allowed_by = "observe" if allowed else None
        reason = "delete_operator_cannot_authorize_write"
    else:
        classification = "unplanned"
        allowed = normalized_mode == "observe"
        allowed_by = "observe" if allowed else None
        reason = "not_in_change_plan"

    if not allowed and target_matches and classification != "delete_only":
        allowed = True
        allowed_by = "current_target"
        reason = "explicit_current_target"
    elif not allowed and target:
        reason = "target_mismatch"

    decision.update(
        classification=classification,
        outcome="allowed" if allowed else "blocked",
        allowed_by=allowed_by,
        unplanned_write=classification == "unplanned",
        reason=reason,
    )
    if decision["unplanned_write"] and allowed:
        decision["warning"] = (
            "Page is outside change_plan; the write was explicitly allowed by "
            f"{allowed_by} and recorded as unplanned_write."
        )
    return decision
