"""Conflict case tools (ADR-0007, 冲突一等对象).

flag_conflict / adjudicate_conflict: give an unresolved contradiction
between two repowiki pages a first-class identity — a case file under
``conflicts/`` — instead of a one-line prompt reminder.

Design constraints (ADR-0007):
- Cases are governance metadata, NOT knowledge: they live in their own
  top-level ``conflicts/`` directory, are never indexed into the search
  corpus, and are excluded from the generic lint audits. Their health is
  owned by the dedicated ``open_conflicts`` lint check.
- Manual declaration only — no auto-detection. HL-Mem's automatic discovery
  rides on a slot registry base this repo does not have, and Mode C
  distillation measured weak-conflict candidates as mostly false positives.
- Adjudication reuses the existing reject_note primitive
  (``note_writer._apply_status_to_file``); the ledger is git — every case
  transition lands in a tracked frontmatter rewrite.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.src.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

# Adjudication action set (ADR-0007). keep_a/keep_b deprecate the loser via
# the reject_note primitive; coexist records both sides as valid; reject
# closes the case as a false positive with neither side touched.
CONFLICT_ACTIONS = ("keep_a", "keep_b", "coexist", "reject")

# Case frontmatter status: open | resolved. The reject action is a terminal
# *resolution* value, not a third status (ADR-0007 keeps status two-valued).
_CASE_STATUS = ("open", "resolved")


def _conflicts_dir(output_dir: Path) -> Path:
    from codewiki.src.config import CONFLICTS_DIR

    return output_dir / CONFLICTS_DIR


def _resolve_output_dir(arguments: Dict[str, Any], store: SessionStore) -> Optional[Path]:
    """repo_path derivation first, active session fallback (write-path rule)."""
    rp = arguments.get("repo_path")
    if rp:
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        return default_output_dir(Path(rp).expanduser().resolve())
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    if session:
        return Path(session.output_dir).expanduser().resolve()
    return None


def _norm_claimant(output_dir: Path, claimant: str) -> Optional[str]:
    """Normalize a claimant reference to a repowiki-relative posix path.

    Accepts ``notes/x.md``, ``wiki/modules/y.md``, or a bare ``x.md`` (which
    resolves against ``notes/``). Returns ``None`` on traversal or a missing
    file — the caller reports it, we never guess.
    """
    from codewiki.src.config import NOTES_DIR

    raw = str(claimant or "").strip().replace("\\", "/")
    if not raw:
        return None
    if "/" not in raw:
        raw = f"{NOTES_DIR}/{raw}"
    from codewiki.mcp.tools.note_writer import _resolve_within

    resolved = _resolve_within(output_dir, raw)
    if resolved is None or not resolved.is_file():
        return None
    return resolved.relative_to(output_dir).as_posix()


def _pair_key(claimants: List[str]) -> str:
    """Deterministic identity for a claimant pair (order-insensitive)."""
    return hashlib.sha256("||".join(sorted(claimants)).encode("utf-8")).hexdigest()[:16]


def _load_cases(output_dir: Path) -> List[Dict[str, Any]]:
    """Read every case file under conflicts/ (frontmatter + relpath)."""
    cdir = _conflicts_dir(output_dir)
    if not cdir.is_dir():
        return []
    cases: List[Dict[str, Any]] = []
    for p in sorted(cdir.glob("*.md")):
        try:
            fm, _body = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not isinstance(fm, dict) or not fm:
            continue
        cases.append(
            {
                "path": p,
                "relpath": p.relative_to(output_dir).as_posix(),
                "fm": fm,
            }
        )
    return cases


def load_open_conflicts(output_dir: Path) -> Dict[str, Dict[str, str]]:
    """Map claimant relpath → open case info, for retrieval annotation.

    Public seam consumed by note_query (query_wiki default path + by_file
    timeline): a result whose ``file`` is a claimant of an OPEN case gets an
    ``open_conflict`` marker so the agent never reads one side of an
    unresolved contradiction unawares. Fail-open: any error yields an empty
    map and the annotation layer skips silently.
    """
    mapping: Dict[str, Dict[str, str]] = {}
    try:
        for case in _load_cases(output_dir):
            fm = case["fm"]
            if str(fm.get("status") or "").lower() != "open":
                continue
            info = {
                "file": case["relpath"],
                "group_key": str(fm.get("group_key") or ""),
                "title": str(fm.get("title") or case["path"].stem),
            }
            for c in fm.get("claimants") or []:
                key = str(c or "").strip().replace("\\", "/")
                if key:
                    mapping[key] = info
    except Exception as e:  # fail-open: annotation must never break search
        logger.debug("load_open_conflicts failed: %s", e)
        return {}
    return mapping


def _case_body(description: str, claimants: List[str], flagged_by: str, created: str) -> str:
    lines = [
        f"# 冲突：{description}",
        "",
        f"> 状态：**open（未裁决）** · 创建 {created} · 由 {flagged_by} 声明",
        "",
        "## 当事笔记",
        "",
    ]
    for i, c in enumerate(claimants):
        label = "A" if i == 0 else "B"
        lines.append(f"- **claimant {label}**：[{c}](../{c})")
    lines += [
        "",
        "## 冲突描述",
        "",
        description,
        "",
        "## 裁决",
        "",
        "（未裁决。用 `adjudicate_conflict` 裁决，动作集：`keep_a` / `keep_b` / `coexist` / `reject`。）",
        "",
    ]
    return "\n".join(lines)


def handle_flag_conflict(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Declare a contradiction between two pages as a first-class conflict case."""
    output_dir = _resolve_output_dir(arguments, store)
    if output_dir is None:
        return json.dumps(
            {"error": "repo_path is required (or pass an active session)."},
            ensure_ascii=False,
        )

    raw_claimants = arguments.get("claimants") or []
    if not isinstance(raw_claimants, list) or len(raw_claimants) != 2:
        return json.dumps(
            {"error": "claimants must be a list of exactly 2 pages."},
            ensure_ascii=False,
        )
    claimants: List[str] = []
    for c in raw_claimants:
        norm = _norm_claimant(output_dir, str(c))
        if norm is None:
            return json.dumps(
                {"error": f"Claimant not found (or outside repowiki): {c}"},
                ensure_ascii=False,
            )
        claimants.append(norm)
    if claimants[0] == claimants[1]:
        return json.dumps({"error": "claimants must be two different pages."}, ensure_ascii=False)

    description = str(arguments.get("description") or "").strip()
    if not description:
        return json.dumps({"error": "description is required."}, ensure_ascii=False)

    group_key = str(arguments.get("group_key") or "").strip() or _pair_key(claimants)

    # Duplicate gate (same discipline as ingest_source): an OPEN case for the
    # same pair (or the same explicit group_key) already exists → return it.
    for case in _load_cases(output_dir):
        fm = case["fm"]
        if str(fm.get("status") or "").lower() != "open":
            continue
        existing = {str(c or "").strip().replace("\\", "/") for c in (fm.get("claimants") or [])}
        if set(claimants) == existing or str(fm.get("group_key") or "") == group_key:
            return json.dumps(
                {
                    "status": "exists",
                    "conflict_file": case["relpath"],
                    "claimants": claimants,
                    "group_key": group_key,
                    "message": (
                        "An open conflict case for this pair already exists "
                        f"({case['relpath']}). Adjudicate it instead of re-flagging."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )

    from codewiki.mcp.tools.note_writer import _okf_actor

    flagged_by = _okf_actor(arguments.get("by"))
    today = datetime.now().strftime("%Y-%m-%d")

    from codewiki.src.store import slugify

    slug = slugify(description) or "conflict"
    name = f"{today}-{slug}-{group_key[:8]}.md"
    case_path = _conflicts_dir(output_dir) / name
    case_path.parent.mkdir(parents=True, exist_ok=True)

    fm = {
        "type": "conflict",
        "title": description,
        "status": "open",
        "claimants": claimants,
        "group_key": group_key,
        "flagged_by": flagged_by,
        "created": today,
        "resolution": "",
        "resolved_by": "",
        "resolved_at": "",
    }
    body = _case_body(description, claimants, flagged_by, today)
    new_text = f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)}---\n{body}"

    from codewiki.src.store import atomic_write, locked

    with locked(case_path):
        atomic_write(case_path, new_text)

    relpath = case_path.relative_to(output_dir).as_posix()
    # Best-effort wiki log — a log failure never blocks the flag itself.
    try:
        from codewiki.mcp.tools.wiki_index import append_log

        append_log(str(output_dir), "flag_conflict", f"{relpath}: {description}")
    except Exception as e:
        logger.debug("conflict-case log skipped: %s", e)

    return json.dumps(
        {
            "status": "created",
            "conflict_file": relpath,
            "claimants": claimants,
            "group_key": group_key,
            "message": (
                "Conflict case created (status=open). query_wiki results hitting "
                "either claimant now carry an open_conflict marker until the case "
                "is adjudicated."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )


def handle_adjudicate_conflict(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Resolve an open conflict case (keep_a / keep_b / coexist / reject)."""
    output_dir = _resolve_output_dir(arguments, store)
    if output_dir is None:
        return json.dumps(
            {"error": "repo_path is required (or pass an active session)."},
            ensure_ascii=False,
        )

    conflict_file = str(arguments.get("conflict_file") or "").strip()
    if not conflict_file:
        return json.dumps({"error": "conflict_file is required."}, ensure_ascii=False)

    action = str(arguments.get("action") or "").strip()
    if action not in CONFLICT_ACTIONS:
        return json.dumps(
            {"error": f"action must be one of {list(CONFLICT_ACTIONS)}."}, ensure_ascii=False
        )

    reason = str(arguments.get("reason") or "").strip()

    from codewiki.src.config import CONFLICTS_DIR

    raw = conflict_file.replace("\\", "/")
    if not raw.startswith(f"{CONFLICTS_DIR}/"):
        raw = f"{CONFLICTS_DIR}/{raw}"
    from codewiki.mcp.tools.note_writer import _resolve_within

    case_path = _resolve_within(output_dir, raw)
    if case_path is None or not case_path.is_file():
        return json.dumps(
            {"error": f"Conflict case not found: {conflict_file}"}, ensure_ascii=False
        )

    text = case_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)
    if not fm:
        return json.dumps(
            {"error": f"Conflict case has no readable frontmatter: {conflict_file}"},
            ensure_ascii=False,
        )
    if str(fm.get("status") or "").lower() != "open":
        return json.dumps(
            {
                "error": (
                    f"Case is not open (status={fm.get('status')}, "
                    f"resolution={fm.get('resolution')}). Only open cases can be adjudicated."
                )
            },
            ensure_ascii=False,
        )

    claimants = [str(c or "").strip().replace("\\", "/") for c in (fm.get("claimants") or [])]
    if len(claimants) != 2:
        return json.dumps(
            {"error": "Case frontmatter must carry exactly 2 claimants."}, ensure_ascii=False
        )

    deprecated: List[str] = []
    if action in ("keep_a", "keep_b"):
        # Reuse the reject_note primitive: the loser is deprecated with the
        # adjudication as its reason — no new state machine (ADR-0007).
        loser_rel = claimants[1] if action == "keep_a" else claimants[0]
        loser_path = _resolve_within(output_dir, loser_rel)
        if loser_path is None or not loser_path.is_file():
            return json.dumps(
                {"error": f"Losing claimant not found: {loser_rel}"}, ensure_ascii=False
            )
        from codewiki.mcp.tools.note_writer import _apply_status_to_file

        dep_reason = (
            f"conflict adjudicated ({action}): {reason}"
            if reason
            else f"conflict adjudicated ({action})"
        )
        result = json.loads(
            _apply_status_to_file(loser_path, output_dir, "deprecated", reason=dep_reason)
        )
        if "error" in result:
            return json.dumps(result, indent=2, ensure_ascii=False)
        deprecated.append(loser_rel)

    from codewiki.mcp.tools.note_writer import _okf_actor

    resolved_by = _okf_actor(arguments.get("by"))
    resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_fm = dict(fm)
    new_fm["status"] = "resolved"
    new_fm["resolution"] = action
    new_fm["reason"] = reason
    new_fm["resolved_by"] = resolved_by
    new_fm["resolved_at"] = resolved_at

    action_text = {
        "keep_a": f"保留 claimant A（{claimants[0]}），{claimants[1]} 已置 deprecated。",
        "keep_b": f"保留 claimant B（{claimants[1]}），{claimants[0]} 已置 deprecated。",
        "coexist": "双方并存：两条笔记各自成立，不做 deprecated。",
        "reject": "误报撤销：冲突不成立，双方保持原状。",
    }[action]
    # Keep the human-readable header in sync with the resolved frontmatter —
    # the case body must not still claim "open" after adjudication (review
    # finding: frontmatter resolved + body "open" misleads human readers).
    body = body.replace("> 状态：**open（未裁决）**", "> 状态：**resolved（已裁决）**", 1)
    body = body.replace(
        "（未裁决。用 `adjudicate_conflict` 裁决，动作集：`keep_a` / `keep_b` / `coexist` / `reject`。）",
        "已裁决，见文末「裁决记录」。",
        1,
    )
    adjudication = (
        f"\n---\n\n## 裁决记录\n\n- 动作：`{action}`\n- 裁决人：{resolved_by}\n"
        f"- 时间：{resolved_at}\n- 结果：{action_text}\n"
    )
    if reason:
        adjudication += f"- 理由：{reason}\n"
    new_text = f"---\n{yaml.safe_dump(new_fm, allow_unicode=True, sort_keys=False)}---\n{body}{adjudication}"

    from codewiki.src.store import atomic_write, locked

    with locked(case_path):
        atomic_write(case_path, new_text)

    relpath = case_path.relative_to(output_dir).as_posix()
    try:
        from codewiki.mcp.tools.wiki_index import append_log

        append_log(str(output_dir), "adjudicate_conflict", f"{relpath}: {action}")
    except Exception as e:
        logger.debug("conflict-case log skipped: %s", e)

    return json.dumps(
        {
            "status": "resolved",
            "conflict_file": relpath,
            "resolution": action,
            "claimants": claimants,
            "deprecated": deprecated,
            "resolved_by": resolved_by,
            "message": f"Conflict case resolved ({action})."
            + (f" Reason: {reason}" if reason else ""),
        },
        indent=2,
        ensure_ascii=False,
    )
