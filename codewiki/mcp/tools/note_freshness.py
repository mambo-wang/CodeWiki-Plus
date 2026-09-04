"""Freshness engine for OKF notes (architecture review 2026-09 #1).

Split from knowledge_loop.py: stale_after window evaluation, per-note
freshness judgement, and the corpus-wide freshness distribution.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.src.frontmatter import parse_frontmatter
from codewiki.src.retrieval import STOPWORDS as _STOPWORDS
from codewiki.mcp.tools.injection_budget import estimate_tokens
logger = logging.getLogger(__name__)

_FRESHNESS_FALLBACK_WINDOW_DAYS = 90
_FRESHNESS_FALLBACK_RETRIEVAL_DEFER_DAYS = 60


def load_freshness_config(schema: Optional[dict]) -> Dict[str, Any]:
    """Resolve freshness settings from a loaded schema.yaml with fallbacks.

    Returns ``{"default_window_days": int, "retrieval_defer_days": int,
    "by_type": {note_type: days}}``.  Missing sections fall back to
    ``conventions.default_stale_days`` and then to hardcoded defaults, so
    bundles without a ``freshness`` block behave exactly as before.
    """
    conv = (schema or {}).get("conventions") or {}
    fresh = conv.get("freshness") or {}
    if not isinstance(fresh, dict):
        fresh = {}

    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    legacy_default = _int(conv.get("default_stale_days"), _FRESHNESS_FALLBACK_WINDOW_DAYS)
    default_window = _int(fresh.get("default_window_days"), legacy_default)
    retrieval_defer = _int(
        fresh.get("retrieval_defer_days"),
        _FRESHNESS_FALLBACK_RETRIEVAL_DEFER_DAYS,
    )
    # V4（note_types 权威表）：仅当 schema 显式声明 conventions.note_types
    # 时才从表派生窗口；否则回退 freshness.by_type——避免默认表覆盖存量
    # schema 的自定义 by_type（向后兼容，无表时行为逐字节不变）。
    by_type: Dict[str, int] = {}
    if isinstance(conv.get("note_types"), dict) and conv["note_types"]:
        try:
            from codewiki.mcp.tools.note_types import freshness_windows

            by_type = dict(freshness_windows(schema))
        except Exception as e:  # table load must never break freshness resolution
            logger.debug("note_types derive skipped: %s", e)
    if not by_type:
        raw_by_type = fresh.get("by_type") or {}
        if isinstance(raw_by_type, dict):
            for key, value in raw_by_type.items():
                days = _int(value, default_window)
                by_type[str(key).strip().lower()] = days

    return {
        "default_window_days": default_window,
        "retrieval_defer_days": retrieval_defer,
        "by_type": by_type,
    }


def freshness_window_days(note_type: Any, schema: Optional[dict]) -> int:
    """Freshness window (days) for *note_type*, per schema freshness config."""
    cfg = load_freshness_config(schema)
    key = str(note_type or "").strip().lower()
    return cfg["by_type"].get(key, cfg["default_window_days"])


def _parse_day(value: Any) -> Optional[datetime]:
    """Parse ``YYYY-MM-DD`` (ignoring any time suffix) into a datetime."""
    if value is None:
        return None
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def evaluate_note_freshness(
    fm: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
    today: Optional[datetime] = None,
    last_hit: Any = None,
) -> Dict[str, Any]:
    """Judge one stable/confirmed note's freshness from its frontmatter.

    Judgment cascade (设计方案 §2, v2):
      1. due date = ``stale_after``; if absent, fall back to
         ``metadata.date`` + the note's type window (legacy behaviour);
      2. due date passed → ``due`` (review deadline missed), unless the note
         was retrieved within ``retrieval_defer_days`` → deferred → ``fresh``;
      3. otherwise → ``fresh``.

    *last_hit* is the retrieval-stats ``last_hit`` value (date string or
    None).  Returns ``{"state": "fresh"|"due", "due_date": "YYYY-MM-DD"|None,
    "deferred": bool}``.  Notes with neither ``stale_after`` nor ``date``
    carry no freshness signal and are reported ``fresh`` (nothing to judge).
    """
    cfg = cfg or load_freshness_config(None)
    today = today or datetime.now()

    due = _parse_day(fm.get("stale_after"))
    if due is None:
        note_date = _parse_day(fm.get("date"))
        if note_date is None:
            return {"state": "fresh", "due_date": None, "deferred": False}
        window = freshness_window_days(
            fm.get("type"),
            {
                "conventions": {
                    "freshness": {
                        "default_window_days": cfg["default_window_days"],
                        "by_type": cfg["by_type"],
                    }
                }
            },
        )
        due = note_date + timedelta(days=window)

    if due >= today.replace(hour=0, minute=0, second=0, microsecond=0):
        return {
            "state": "fresh",
            "due_date": due.strftime("%Y-%m-%d"),
            "deferred": False,
        }

    # Past due — retrieval-defer exemption (existing activity rule)
    hit = _parse_day(last_hit)
    if hit is not None:
        defer_floor = today - timedelta(days=cfg["retrieval_defer_days"])
        if hit > defer_floor:
            return {
                "state": "fresh",
                "due_date": due.strftime("%Y-%m-%d"),
                "deferred": True,
            }

    return {"state": "due", "due_date": due.strftime("%Y-%m-%d"), "deferred": False}


def _freshness_distribution(output_dir: Path) -> Optional[Dict[str, Any]]:
    """Count stable/confirmed notes by freshness state for wiki_stats.

    Reuses :func:`evaluate_note_freshness` — the exact same judgment as
    lint's ``stale_notes`` check — so the health indicator and the lint
    report can never drift apart (设计方案 §6: 复用判定函数，避免两套逻辑).

    Returns ``{"due": n, "fresh": m, "due_notes": [up to 20 rel paths]}``
    or ``None`` when the bundle has no notes/ directory.
    """
    from codewiki.src.config import NOTES_DIR

    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return None

    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
    except Exception:
        schema = {}
    cfg = load_freshness_config(schema)

    retrieval_map: Dict[str, str] = {}
    try:
        from codewiki.mcp.tools import telemetry

        for fp, entry in telemetry.aggregate_usage(output_dir).items():
            lh = entry.get("last_hit")
            if lh:
                retrieval_map[str(fp)] = str(lh)
    except Exception:
        pass

    try:
        from codewiki.mcp.tools.wiki_lint import _parse_note_frontmatter
    except Exception:
        return None

    today = datetime.now()
    due_notes: List[str] = []
    fresh_count = 0

    for note_file in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(note_file)
        if not fm:
            continue
        if str(fm.get("status", "")).lower() not in ("confirmed", "stable"):
            continue
        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        last_hit = retrieval_map.get(rel_path) or retrieval_map.get(f"notes/{note_file.name}")
        verdict = evaluate_note_freshness(fm, cfg, today=today, last_hit=last_hit)
        if verdict["state"] == "due":
            due_notes.append(rel_path)
        else:
            fresh_count += 1

    return {
        "due": len(due_notes),
        "fresh": fresh_count,
        "due_notes": due_notes[:20],
    }



def _note_age_days(fm: Dict[str, Any], today: datetime) -> int:
    """Age in days from ``metadata.date``, falling back to ``verified[-1].at``.

    ``verified`` may be a bare mapping or a YAML list of ``{by, at}`` entries
    (§5.2).  Parse failures yield 0 — an undatable note is treated as newborn,
    which is the safe direction for the min_age_days gate.
    """
    created = None
    meta = fm.get("metadata")
    if isinstance(meta, dict):
        created = _parse_day(meta.get("date"))
    if created is None:
        verified = fm.get("verified")
        if isinstance(verified, dict):
            verified = [verified]
        if isinstance(verified, list) and verified:
            last = verified[-1]
            if isinstance(last, dict):
                created = _parse_day(last.get("at"))
    if created is None:
        return 0
    return max(0, (today - created).days)


