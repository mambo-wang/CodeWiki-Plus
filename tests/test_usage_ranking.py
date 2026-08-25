"""Tests for the usage-signal feedback line (U 线, docs/知识飞轮增强设计方案-P0三项.md §3).

Covers:
  - U1 heat model: neutral new docs, log-saturating boost, cold penalty only
    for "hot then cold" docs, 0.8 floor, bad-date fail-safe;
  - config fallback chain (schema conventions.usage_ranking → defaults);
  - heat applied on BOTH BM25 paths (SQLite cache + legacy JSON index) at the
    same position as authority (after BM25, before the note title floor);
  - exemptions: apply_usage=False and usage_ranking.enabled=false leave the
    ordering untouched while the ``usage`` field is still returned;
  - two-path consistency: same fixture → same file order on both paths;
  - U2 lint linkage: stale_notes output sorted by (overdue_days desc,
    last_hit asc) with hit_count surfaced in the message (judgment untouched).
"""
from __future__ import annotations

import inspect
import math
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from codewiki.mcp.cache import (
    AnalysisCache,
    USAGE_RANKING_DEFAULTS,
    compute_usage_heat,
    load_usage_ranking_config,
)
from codewiki.mcp.tools import wiki_search
from codewiki.mcp.tools.wiki_lint import _check_stale_notes

TODAY = datetime.now()
QUERY = "gateway timeout retry"
SHARED_BODY = "gateway timeout retry budget configuration"

CFG = USAGE_RANKING_DEFAULTS


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_note(notes_dir: Path, name: str, title: str, body: str,
             ntype: str = "general", status: str = "stable") -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    p = notes_dir / name
    p.write_text(
        f"---\ntype: {ntype}\ntitle: {title}\nstatus: {status}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return p


def _write_stats(od: Path, rows: dict) -> None:
    """Seed telemetry hit events with {rel_path: (hit_count, last_hit)}.

    T2 migration: the old SQLite retrieval_stats table is retired; usage
    signals now live in per-user JSONL event streams. Callers keep calling
    _write_stats with the same shape — one aggregated hit line per doc
    carries the whole count.
    """
    from tests.telemetry_seed import seed_hits
    seed_hits(od, rows)


def _write_stale_note(od: Path, name: str, *, stale_after: str,
                      title: str | None = None) -> Path:
    notes = od / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    fm = {
        "type": "decision",
        "title": title or name,
        "status": "stable",
        "stale_after": stale_after,
    }
    p = notes / name
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\nbody\n",
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# 1. Heat model (pure function)
# --------------------------------------------------------------------------- #
def test_heat_no_record_is_neutral():
    assert compute_usage_heat(0, None, CFG) == 1.0
    assert compute_usage_heat(None, None, CFG) == 1.0
    # even an ancient last_hit cannot punish a doc with no hits
    assert compute_usage_heat(0, _days_ago(400), CFG) == 1.0


def test_heat_boost_hit_10():
    expected = 1.0 + min(0.15, 0.03 * math.log(11))  # ≈ 1.0719
    assert compute_usage_heat(10, _days_ago(1), CFG) == pytest.approx(expected)
    assert compute_usage_heat(10, _days_ago(1), CFG) <= 1.15
    # log saturation: huge hit counts cap at boost_cap
    assert compute_usage_heat(100000, _days_ago(1), CFG) == pytest.approx(1.15)


def test_heat_cold_penalty():
    # hit=3 (>= cold_min_hits), last_hit 200 days ago (> cold_days=180)
    heat = compute_usage_heat(3, _days_ago(200), CFG)
    assert 0.8 <= heat <= 0.85  # 1 + 0.03*ln(4) - 0.2 = 0.8416


def test_heat_below_cold_min_hits_not_penalized():
    # hit=1 never reaches cold_min_hits: an ancient last_hit changes nothing.
    boosted = 1.0 + 0.03 * math.log(2)  # ≈ 1.0208 — boost still applies
    assert compute_usage_heat(1, _days_ago(300), CFG) == pytest.approx(boosted)
    assert compute_usage_heat(1, _days_ago(300), CFG) == \
        compute_usage_heat(1, _days_ago(1), CFG)


def test_heat_cold_boundary_strictly_greater():
    # exactly cold_days ago is NOT cold; one day more IS
    warm = compute_usage_heat(5, _days_ago(1), CFG)
    assert compute_usage_heat(5, _days_ago(180), CFG) == pytest.approx(warm)
    assert compute_usage_heat(5, _days_ago(181), CFG) < warm


def test_heat_floor_at_08():
    cfg = {**CFG, "cold_penalty": 0.5}  # 1.15 - 0.5 would be 0.65 -> clamped
    assert compute_usage_heat(100, _days_ago(300), cfg) == 0.8


def test_heat_bad_last_hit_is_not_cold():
    assert compute_usage_heat(5, "not-a-date", CFG) == \
        compute_usage_heat(5, _days_ago(1), CFG)
    assert compute_usage_heat(5, None, CFG) == compute_usage_heat(5, _days_ago(1), CFG)


# --------------------------------------------------------------------------- #
# 2. Config fallback chain
# --------------------------------------------------------------------------- #
def test_config_defaults_when_schema_missing():
    assert load_usage_ranking_config(None) == dict(USAGE_RANKING_DEFAULTS)
    assert load_usage_ranking_config({}) == dict(USAGE_RANKING_DEFAULTS)
    assert load_usage_ranking_config({"conventions": {}}) == dict(USAGE_RANKING_DEFAULTS)


def test_config_overrides_from_schema():
    cfg = load_usage_ranking_config({"conventions": {"usage_ranking": {
        "enabled": False, "boost_cap": 0.2, "cold_days": 90, "cold_min_hits": 5,
    }}})
    assert cfg["enabled"] is False
    assert cfg["boost_cap"] == 0.2
    assert cfg["cold_days"] == 90
    assert cfg["cold_min_hits"] == 5
    assert cfg["cold_penalty"] == 0.2  # untouched key keeps the default


def test_config_malformed_values_fall_back_per_key():
    cfg = load_usage_ranking_config({"conventions": {"usage_ranking": {
        "boost_cap": "not-a-float", "cold_days": "x", "enabled": "yes",
    }}})
    assert cfg["boost_cap"] == 0.15
    assert cfg["cold_days"] == 180
    assert cfg["enabled"] is True  # non-bool keeps the default


# --------------------------------------------------------------------------- #
# 3. Ranking effect — legacy JSON path
# --------------------------------------------------------------------------- #
def test_json_path_orders_hot_doc_first(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (10, _days_ago(1))})  # B never retrieved

    wiki_search.build_full_index(od)  # no session / no DB -> legacy JSON index
    res = wiki_search.search(od, QUERY)
    assert [r["file"] for r in res] == ["notes/n-a.md", "notes/n-b.md"]
    # identical bodies -> identical BM25; heat decides the order
    assert res[0]["relevance_score"] > res[1]["relevance_score"]


def test_json_path_cold_doc_ranked_after_warm(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-cold.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-warm.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {
        "notes/n-cold.md": (5, _days_ago(200)),  # hot then cold -> penalised
        "notes/n-warm.md": (5, _days_ago(1)),     # same hits, still warm
    })

    wiki_search.build_full_index(od)
    res = wiki_search.search(od, QUERY)
    assert [r["file"] for r in res] == ["notes/n-warm.md", "notes/n-cold.md"]


def test_json_path_new_doc_neutral(tmp_path):
    # A never-retrieved doc outranks a cold doc (1.0 vs 0.85) on equal BM25
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-cold.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-new.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-cold.md": (5, _days_ago(200))})

    wiki_search.build_full_index(od)
    res = wiki_search.search(od, QUERY)
    assert [r["file"] for r in res] == ["notes/n-new.md", "notes/n-cold.md"]


def test_json_path_stats_recorded_after_first_search_reorders(tmp_path):
    # mtime cache: stats written AFTER a first search must be picked up
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    wiki_search.build_full_index(od)

    before = wiki_search.search(od, QUERY)
    assert {r["file"] for r in before} == {"notes/n-a.md", "notes/n-b.md"}

    _write_stats(od, {"notes/n-b.md": (10, _days_ago(1))})
    after = wiki_search.search(od, QUERY)
    assert [r["file"] for r in after] == ["notes/n-b.md", "notes/n-a.md"]


# --------------------------------------------------------------------------- #
# 4. Ranking effect — SQLite path
# --------------------------------------------------------------------------- #
def test_sqlite_path_orders_hot_doc_first(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (10, _days_ago(1))})

    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        res = cache.search(QUERY, output_dir=od)
        assert [r["file"] for r in res] == ["notes/n-a.md", "notes/n-b.md"]
        assert res[0]["relevance_score"] > res[1]["relevance_score"]

        # exemption: identical raw scores when usage weighting is off
        raw = cache.search(QUERY, output_dir=od, apply_usage=False)
        by_file = {r["file"]: r for r in raw}
        assert by_file["notes/n-a.md"]["relevance_score"] == \
            by_file["notes/n-b.md"]["relevance_score"]
    finally:
        cache.close()


def test_sqlite_path_cold_doc_ranked_after_warm(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-cold.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-warm.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {
        "notes/n-cold.md": (5, _days_ago(200)),
        "notes/n-warm.md": (5, _days_ago(1)),
    })

    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        res = cache.search(QUERY, output_dir=od)
        assert [r["file"] for r in res] == ["notes/n-warm.md", "notes/n-cold.md"]
    finally:
        cache.close()


# --------------------------------------------------------------------------- #
# 5. Exemptions: enabled=false and apply_usage=False
# --------------------------------------------------------------------------- #
def _score_by_file(res):
    return {r["file"]: r["relevance_score"] for r in res}


def test_enabled_false_matches_no_heat_ordering(tmp_path):
    od = tmp_path / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / "schema.yaml").write_text(yaml.safe_dump(
        {"conventions": {"usage_ranking": {"enabled": False}}}), encoding="utf-8")
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (10, _days_ago(1))})

    wiki_search.build_full_index(od)
    off = wiki_search.search(od, QUERY)
    exempt = wiki_search.search(od, QUERY, apply_usage=False)

    # ordering + scores identical to the apply_usage=False exemption run
    assert [r["file"] for r in off] == [r["file"] for r in exempt]
    assert _score_by_file(off) == _score_by_file(exempt)
    # heat did not distort the tie between identical-BM25 docs
    by_file = _score_by_file(off)
    assert by_file["notes/n-a.md"] == by_file["notes/n-b.md"]
    # usage field is still returned for transparency
    assert all("usage" in r for r in off)


def test_apply_usage_false_keeps_usage_field_but_no_heat(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (10, _days_ago(1))})

    wiki_search.build_full_index(od)
    res = wiki_search.search(od, QUERY, apply_usage=False)
    assert len(res) == 2
    by_file = {r["file"]: r for r in res}
    # no heat: identical-BM25 docs tie again
    assert by_file["notes/n-a.md"]["relevance_score"] == \
        by_file["notes/n-b.md"]["relevance_score"]
    # usage field still present and populated
    assert by_file["notes/n-a.md"]["usage"] == \
        {"hit_count": 10, "last_hit": _days_ago(1), "adopted_count": 0}
    assert by_file["notes/n-b.md"]["usage"] == {"hit_count": 0, "last_hit": None, "adopted_count": 0}


# --------------------------------------------------------------------------- #
# 6. usage field on result entries
# --------------------------------------------------------------------------- #
def test_usage_field_present_on_all_entries(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _mk_note(od / "notes", "n-b.md", "gateway timeout bravo", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (10, _days_ago(3))})

    wiki_search.build_full_index(od)
    res = wiki_search.search(od, QUERY)
    by_file = {r["file"]: r for r in res}
    assert set(by_file["notes/n-a.md"]["usage"].keys()) == {"hit_count", "last_hit", "adopted_count"}
    assert by_file["notes/n-a.md"]["usage"] == {"hit_count": 10, "last_hit": _days_ago(3), "adopted_count": 0}
    # never-retrieved docs carry a zero usage record
    assert by_file["notes/n-b.md"]["usage"] == {"hit_count": 0, "last_hit": None, "adopted_count": 0}


def test_sqlite_path_usage_field_present(tmp_path):
    od = tmp_path / "repowiki"
    _mk_note(od / "notes", "n-a.md", "gateway timeout alpha", SHARED_BODY)
    _write_stats(od, {"notes/n-a.md": (7, _days_ago(2))})

    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        res = cache.search(QUERY, output_dir=od)
        assert res and res[0]["usage"] == {"hit_count": 7, "last_hit": _days_ago(2), "adopted_count": 0}
    finally:
        cache.close()


def test_search_signature_defaults_apply_usage_true():
    # distill dedup recall (knowledge_loop) will pass apply_usage=False at
    # its existing apply_authority=False call sites — the parameter must
    # exist and default to True everywhere.
    ws_param = inspect.signature(wiki_search.search).parameters["apply_usage"]
    assert ws_param.default is True
    cache_param = inspect.signature(AnalysisCache.search).parameters["apply_usage"]
    assert cache_param.default is True


# --------------------------------------------------------------------------- #
# 7. Two-path consistency: same fixture, same order
# --------------------------------------------------------------------------- #
def test_sqlite_and_json_paths_agree_on_order(tmp_path):
    def _populate(od: Path) -> None:
        _mk_note(od / "notes", "n-hot.md", "gateway timeout alpha", SHARED_BODY)
        _mk_note(od / "notes", "n-cold.md", "gateway timeout bravo", SHARED_BODY)
        _mk_note(od / "notes", "n-new.md", "gateway timeout charlie", SHARED_BODY)
        _write_stats(od, {
            "notes/n-hot.md": (10, _days_ago(1)),
            "notes/n-cold.md": (5, _days_ago(200)),
        })

    od_json = tmp_path / "alpha" / "repowiki"   # parent has no .codewiki -> JSON
    od_sql = tmp_path / "beta" / "repowiki"
    _populate(od_json)
    _populate(od_sql)

    wiki_search.build_full_index(od_json)      # legacy JSON index
    cache = AnalysisCache(tmp_path / "beta",
                          db_path=tmp_path / "beta" / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od_sql)

        res_json = wiki_search.search(od_json, QUERY)
        res_sql = cache.search(QUERY, output_dir=od_sql)

        # same file set, same order (heat decides: hot > new > cold)
        assert [r["file"] for r in res_json] == \
            ["notes/n-hot.md", "notes/n-new.md", "notes/n-cold.md"]
        assert [r["file"] for r in res_sql] == [r["file"] for r in res_json]
        # per-file scores agree (JSON index rounds avg_doc_len; allow slack)
        scores_json = _score_by_file(res_json)
        scores_sql = _score_by_file(res_sql)
        for fk in scores_json:
            assert abs(scores_json[fk] - scores_sql[fk]) < 0.05
        # usage transparency agrees too
        for rj, rs in zip(res_json, res_sql):
            assert rj["usage"] == rs["usage"]
    finally:
        cache.close()


# --------------------------------------------------------------------------- #
# 8. U2: lint stale_notes review-priority ordering
# --------------------------------------------------------------------------- #
def test_stale_notes_sorted_by_overdue_then_last_hit(tmp_path):
    od = tmp_path / "repowiki"
    od.mkdir(parents=True)
    # overdue 40 days, retrieved 5 times (most overdue -> first)
    _write_stale_note(od, "old.md", stale_after=_days_ago(40))
    # overdue 10 days, retrieved twice
    _write_stale_note(od, "new.md", stale_after=_days_ago(10))
    # overdue 5 days, never retrieved (least recently "hit" -> first of its group)
    _write_stale_note(od, "nv.md", stale_after=_days_ago(5))
    # overdue 5 days, last hit 100 / 70 days ago (both beyond the defer window)
    _write_stale_note(od, "c.md", stale_after=_days_ago(5))
    _write_stale_note(od, "d.md", stale_after=_days_ago(5))
    _write_stats(od, {
        "notes/old.md": (5, _days_ago(90)),
        "notes/new.md": (2, _days_ago(70)),
        "notes/c.md": (1, _days_ago(100)),
        "notes/d.md": (1, _days_ago(70)),
    })

    issues = [i for i in _check_stale_notes(od) if i["check"] == "stale_notes"]
    assert [i["file"] for i in issues] == [
        "notes/old.md",   # overdue 40 (primary key: overdue_days desc)
        "notes/new.md",   # overdue 10
        "notes/nv.md",    # overdue 5, never retrieved ("" sorts first)
        "notes/c.md",     # overdue 5, last hit 100d ago
        "notes/d.md",     # overdue 5, last hit 70d ago
    ]
    # hit_count surfaced in the message
    by_file = {i["file"]: i for i in issues}
    assert "(retrieved 5 times total)" in by_file["notes/old.md"]["message"]
    assert "(retrieved 2 times total)" in by_file["notes/new.md"]["message"]
    assert "(retrieved 0 times total)" in by_file["notes/nv.md"]["message"]


def test_stale_notes_judgment_unchanged(tmp_path):
    # Retrieval within the defer window still exempts a note (existing
    # behavior preserved — U2 only reorders output, never the verdict).
    od = tmp_path / "repowiki"
    od.mkdir(parents=True)
    _write_stale_note(od, "deferred.md", stale_after=_days_ago(10))
    _write_stale_note(od, "due.md", stale_after=_days_ago(10))
    _write_stats(od, {
        "notes/deferred.md": (3, _days_ago(2)),   # recent hit -> deferred
        "notes/due.md": (3, _days_ago(90)),       # stale hit -> due
    })
    issues = [i for i in _check_stale_notes(od) if i["check"] == "stale_notes"]
    assert [i["file"] for i in issues] == ["notes/due.md"]
