"""wiki_stats tool family (split from knowledge_loop.py, 2026-09 #1).

Corpus statistics: note counts, cold-note candidates, promotion
candidates (stable + adopted + old enough).
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
from codewiki.mcp.tools.note_freshness import _freshness_distribution, _note_age_days
from codewiki.mcp.tools.note_query import _extract_frontmatter_block
from codewiki.mcp.tools.note_writer import _norm_status
logger = logging.getLogger(__name__)

_PROMOTION_PAGE_TYPES: Dict[str, str] = {}  # filled below from the table

from codewiki.mcp.tools.note_types import (  # noqa: E402
    DEFAULT_NOTE_TYPES as _NT_TABLE,
)

_PROMOTION_PAGE_TYPES.update(
    {t: str(spec.get("promote_to") or "") for t, spec in _NT_TABLE.items()}
)


def handle_wiki_stats(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return per-document retrieval statistics (hit count ranking).

    T2: reads the team-wide telemetry aggregate
    (``telemetry.aggregate_usage`` over all users' jsonl event streams)
    instead of the retired SQLite retrieval_stats table. Supports optional
    sorting, limit, and include_zero_hit (cross-references with the
    file system to find documents that were never retrieved).
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)

    od = arguments.get("output_dir")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        rp = arguments.get("repo_path")
        if rp:
            output_dir = Path(rp).expanduser().resolve() / "repowiki"
        else:
            return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    from codewiki.mcp.tools import telemetry

    usage = telemetry.aggregate_usage(output_dir)
    if not usage:
        # P2: aggregation counters stay visible even before any query stats exist.
        try:
            from codewiki.mcp.tools import aggregation_state as agg

            _agg = agg.aggregation_summary(output_dir)
        except Exception:
            _agg = None
        # 新鲜度分布不依赖检索统计，照常给出（健康度指标）。
        try:
            _fresh = _freshness_distribution(output_dir)
        except Exception:
            _fresh = None
        return json.dumps(
            {
                "error": "No retrieval stats found. Run query_wiki first to generate stats.",
                "telemetry_dir": str(output_dir / ".meta" / "telemetry"),
                **({"aggregation": _agg} if _agg else {}),
                **({"freshness": _fresh} if _fresh else {}),
            }
        )

    sort_by = arguments.get("sort_by", "hit_count")
    order = arguments.get("order", "desc")
    limit = min(200, max(1, arguments.get("limit", 50)))
    include_zero_hit = arguments.get("include_zero_hit", False)
    min_hits = arguments.get("min_hits", 0)

    # Validate sort column (file_path / hit_count / last_hit / first_hit;
    # the legacy last_query ordering key is gone — events carry no query text).
    def _sort_value(fp: str):
        entry = usage.get(fp, {})
        return {
            "hit_count": entry.get("hits", 0),
            "last_hit": entry.get("last_hit") or "",
            "first_hit": entry.get("first_hit") or "",
            "file_path": fp,
        }.get(sort_by, entry.get("hits", 0))

    eligible = [fp for fp, e in usage.items() if int(e.get("hits", 0)) >= int(min_hits)]
    eligible.sort(
        key=_sort_value,
        reverse=(order != "asc"),
    )
    # total query count proxy: distinct days on which any hit event was
    # recorded (the exact query log is gone with the SQLite table).
    total_queries = (
        len(set().union(*(e.get("hit_days") or set() for e in usage.values()))) if usage else 0
    )

    stats = []
    for fp in eligible[:limit]:
        e = usage[fp]
        stats.append(
            {
                "file_path": fp,
                "hit_count": int(e.get("hits", 0)),
                "last_hit": e.get("last_hit"),
                "first_hit": e.get("first_hit"),
                "hit_rate": (
                    round(int(e.get("hits", 0)) / total_queries, 4) if total_queries > 0 else 0
                ),
            }
        )

    # Optionally include zero-hit documents (files on disk with no events)
    zero_hit = []
    if include_zero_hit:
        # Scan wiki/ and notes/ for all .md files
        all_files = set()
        for subdir in ["wiki", "notes"]:
            scan_dir = output_dir / subdir
            if scan_dir.exists():
                for md_file in scan_dir.rglob("*.md"):
                    rel = str(md_file.relative_to(output_dir)).replace("\\", "/")
                    all_files.add(rel)

        hit_files = set(usage.keys())
        for f in sorted(all_files - hit_files):
            zero_hit.append({"file_path": f, "hit_count": 0})

    # P2 (§4.5): expose aggregation counters so agents/users can see when
    # consolidation is due without waiting for a threshold-crossing hint.
    aggregation = None
    try:
        from codewiki.mcp.tools import aggregation_state as agg

        aggregation = agg.aggregation_summary(output_dir)
    except Exception:
        pass

    # 新鲜度机制专项: due/fresh distribution (same judgment as lint stale_notes)
    freshness = None
    try:
        freshness = _freshness_distribution(output_dir)
    except Exception:
        freshness = None

    # 使用信号反馈 (U 线): once-hot-now-cold docs — retrieval health signal.
    cold = None
    try:
        cold = _cold_candidates(output_dir)
    except Exception:
        cold = None

    # P1 C 线: notes that have earned promotion to a formal wiki page —
    # stable + repeatedly adopted + old enough + not yet promoted.
    # (Mounted on the main return only: without a stats db there is no
    # adoption data either, so the early-return branch would always be [].)
    promotion = None
    try:
        promotion = _promotion_candidates(output_dir)
    except Exception:
        promotion = None

    return json.dumps(
        {
            "total_distinct_queries": total_queries,
            "returned": len(stats),
            "sort_by": sort_by,
            "order": order,
            "stats": stats,
            **({"zero_hit_files": zero_hit} if include_zero_hit else {}),
            **({"aggregation": aggregation} if aggregation else {}),
            **({"freshness": freshness} if freshness else {}),
            **({"cold_candidates": cold} if cold else {}),
            **({"promotion_candidates": promotion} if promotion else {}),
        },
        indent=2,
        ensure_ascii=False,
    )


def _cold_candidates(output_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Usage-signal health metric (U-line): docs that were hot
    (hit_count >= cold_min_hits) but have not been retrieved for more than
    cold_days. Mirrors the usage_ranking cold-penalty definition in the BM25
    paths so the stats view and the ranking behaviour never diverge.
    Returns None when no telemetry data exists or nothing is cold.
    """
    from codewiki.mcp.tools import telemetry

    usage = telemetry.aggregate_usage(output_dir)
    if not usage:
        return None

    cold_days, cold_min_hits = 180, 3
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir)) or {}
        ur = (schema.get("conventions") or {}).get("usage_ranking") or {}
        cold_days = int(ur.get("cold_days", cold_days))
        cold_min_hits = int(ur.get("cold_min_hits", cold_min_hits))
    except Exception:
        pass

    from datetime import datetime, timedelta

    rows = [
        (fp, int(entry.get("hits", 0)), entry.get("last_hit"))
        for fp, entry in usage.items()
        if int(entry.get("hits", 0)) >= cold_min_hits and entry.get("last_hit")
    ]

    today = datetime.now()
    cutoff = today - timedelta(days=cold_days)
    out: List[Dict[str, Any]] = []
    for fp, hit_count, last_hit in rows:
        try:
            lh_dt = datetime.strptime(str(last_hit)[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if lh_dt < cutoff:
            out.append(
                {
                    "file_path": fp,
                    "hit_count": hit_count,
                    "last_hit": last_hit,
                    "days_since_last_hit": (today - lh_dt).days,
                }
            )
    out.sort(key=lambda x: -x["days_since_last_hit"])
    return out


# P1 C-line (docs/知识飞轮增强设计方案-P1三项.md §4.3): note → wiki page
# promotion routing.  The default target page_type per note type; an empty
# string leaves the choice to the agent (mapping is a default, not a mandate).
# V4: derived from the authoritative note_types table (note_types.py);
# schema-level overrides are resolved at the consumption site via
# ``note_types.promotion_targets``.
_PROMOTION_PAGE_TYPES: Dict[str, str] = {}  # filled below from the table

from codewiki.mcp.tools.note_types import (  # noqa: E402
    DEFAULT_NOTE_TYPES as _NT_TABLE,
)

_PROMOTION_PAGE_TYPES.update(
    {t: str(spec.get("promote_to") or "") for t, spec in _NT_TABLE.items()}
)



def _promotion_candidates(output_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """P1 C-line: notes that have earned promotion to a formal wiki page.

    Candidate = stable note, adopted_count >= min_adopted (default 3),
    age >= min_age_days (default 14, from metadata.date or verified[-1].at),
    and NOT already marked metadata.promoted_to.

    Frontmatter is parsed structurally via :func:`_extract_frontmatter_block`
    (yaml.safe_load), so the nested ``metadata:`` block — whether emitted as
    indented ``key: value`` rows or flow style — and the ``verified`` list are
    read as real YAML structures, not line-level guesses.  Returns ``None``
    when the bundle has no notes/ directory; otherwise a (possibly empty)
    list sorted by adopted_count desc, each entry carrying
    file/title/type/adopted_count/age_days/suggested_page_type.
    """
    from codewiki.src.config import NOTES_DIR

    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return None

    # Thresholds from schema.yaml conventions.promotion (cold-candidates style)
    min_adopted, min_age_days = 3, 14
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir)) or {}
        promo = (schema.get("conventions") or {}).get("promotion") or {}
        min_adopted = int(promo.get("min_adopted", min_adopted))
        min_age_days = int(promo.get("min_age_days", min_age_days))
    except Exception:
        pass

    # A-line adoption counts: missing db/table → {} → nothing can qualify.
    try:
        from codewiki.mcp.tools.adoption import load_adoption_counts

        adopted_counts = load_adoption_counts(Path(output_dir))
    except Exception as e:
        logger.debug("promotion_candidates adoption load failed: %s", e)
        return []

    today = datetime.now()
    out: List[Dict[str, Any]] = []
    for note_file in sorted(notes_dir.glob("*.md")):
        try:
            text = note_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _extract_frontmatter_block(text)
        if not fm:
            continue
        # Only confirmed notes are promotion material.
        if _norm_status(fm.get("status")) != "stable":
            continue
        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        adopted = adopted_counts.get(rel_path, 0)
        if adopted < min_adopted:
            continue
        # Already promoted — the note stays as an audit anchor; never re-promote.
        meta = fm.get("metadata")
        if isinstance(meta, dict) and meta.get("promoted_to"):
            continue
        age = _note_age_days(fm, today)
        if age < min_age_days:
            continue
        note_type = str(fm.get("type", "")).strip().lower()
        out.append(
            {
                "file": rel_path,
                "title": fm.get("title", note_file.stem),
                "type": note_type,
                "adopted_count": adopted,
                "age_days": age,
                "suggested_page_type": _PROMOTION_PAGE_TYPES.get(note_type, ""),
            }
        )
    out.sort(key=lambda x: -x["adopted_count"])
    return out


