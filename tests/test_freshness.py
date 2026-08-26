"""Tests for the 新鲜度机制专项 (type-aware freshness windows).

Covers docs/新鲜度机制设计方案.md acceptance criteria:
  - Fallback chain: by_type[type] -> default_window_days -> default_stale_days -> 90
  - ingest/confirm write stale_after using the note's TYPE window (not flat 90)
  - confirm_note renews stale_after -> confirmed old notes are no longer stale
  - lint stale_notes judges by stale_after (not creation date) + retrieval-defer
  - lint reads conventions.freshness from schema.yaml (dispatch no longer hardcoded)
  - backfill script is idempotent and converts verified[] into freshness
  - wiki_stats exposes freshness {due, fresh} reusing the same judgment
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.knowledge_loop import (
    _freshness_distribution,
    evaluate_note_freshness,
    freshness_window_days,
    handle_confirm_note,
    handle_ingest_note,
    handle_wiki_stats,
    load_freshness_config,
)
from codewiki.mcp.tools.wiki_lint import _check_stale_notes, handle_lint_wiki


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_wiki(tmp_path, freshness=None, default_stale_days=90) -> Path:
    od = tmp_path / "repowiki"
    od.mkdir(parents=True, exist_ok=True)
    (od / "notes").mkdir(exist_ok=True)
    conv = {"default_stale_days": default_stale_days}
    if freshness is not None:
        conv["freshness"] = freshness
    (od / "schema.yaml").write_text(
        yaml.safe_dump({"conventions": conv}), encoding="utf-8"
    )
    return od


def _write_note(od: Path, name: str, *, ntype="decision", status="stable",
                stale_after=None, date=None, verified=None,
                title="T") -> Path:
    fm = {"type": ntype, "title": title, "status": status}
    if date:
        fm["metadata"] = {"date": date}
    if stale_after:
        fm["stale_after"] = stale_after
    if verified:
        fm["verified"] = verified
    p = od / "notes" / name
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
        + "---\n\nbody\n",
        encoding="utf-8",
    )
    return p


def _stats_due(issues) -> list:
    return [i for i in issues if i["check"] == "stale_notes"]


def _touch(od: Path, rel_path: str, last_hit: str) -> None:
    """Seed one hit event (T2: telemetry jsonl replaces the stats table)."""
    from tests.telemetry_seed import seed_hits
    seed_hits(od, {rel_path: (1, last_hit)})


TODAY = datetime.now()
PAST = (TODAY - timedelta(days=30)).strftime("%Y-%m-%d")
FUTURE = (TODAY + timedelta(days=30)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# 1. Config fallback chain (F2 helper)
# --------------------------------------------------------------------------- #
def test_fallback_chain_by_type():
    schema = {"conventions": {"default_stale_days": 90, "freshness": {
        "default_window_days": 180, "by_type": {"workaround": 45}}}}
    assert freshness_window_days("workaround", schema) == 45
    assert freshness_window_days("WORKAROUND", schema) == 45  # case-insensitive


def test_fallback_chain_default_window():
    schema = {"conventions": {"default_stale_days": 90, "freshness": {
        "default_window_days": 180}}}
    assert freshness_window_days("unknown_type", schema) == 180


def test_fallback_chain_legacy_default_stale_days():
    # No freshness section -> falls back to default_stale_days (backward compat)
    assert freshness_window_days("decision", {"conventions": {"default_stale_days": 120}}) == 120


def test_fallback_chain_hardcoded():
    assert freshness_window_days("decision", {}) == 90
    assert freshness_window_days(None, None) == 90


def test_load_freshness_config_retrieval_defer():
    cfg = load_freshness_config({"conventions": {"freshness": {"retrieval_defer_days": 15}}})
    assert cfg["retrieval_defer_days"] == 15
    cfg = load_freshness_config(None)
    assert cfg["retrieval_defer_days"] == 60  # hardcoded default


# --------------------------------------------------------------------------- #
# 2. evaluate_note_freshness judgment cascade
# --------------------------------------------------------------------------- #
def test_judge_stale_after_future_is_fresh():
    v = evaluate_note_freshness({"stale_after": FUTURE, "type": "decision"})
    assert v["state"] == "fresh"


def test_judge_stale_after_past_is_due():
    v = evaluate_note_freshness({"stale_after": PAST, "type": "decision"})
    assert v["state"] == "due"
    assert v["due_date"] == PAST


def test_judge_retrieval_defer():
    recent = (TODAY - timedelta(days=5)).strftime("%Y-%m-%d")
    v = evaluate_note_freshness({"stale_after": PAST}, None, last_hit=recent)
    assert v["state"] == "fresh" and v["deferred"] is True
    old_hit = (TODAY - timedelta(days=200)).strftime("%Y-%m-%d")
    v2 = evaluate_note_freshness({"stale_after": PAST}, None, last_hit=old_hit)
    assert v2["state"] == "due"


def test_judge_date_fallback_uses_type_window():
    # No stale_after -> fall back to metadata.date + type window
    old = (TODAY - timedelta(days=100)).strftime("%Y-%m-%d")
    schema_cfg = load_freshness_config({"conventions": {"freshness": {
        "default_window_days": 180, "by_type": {"workaround": 45}}}})
    # workaround, 100 days old, 45d window -> due
    assert evaluate_note_freshness({"date": old, "type": "workaround"}, schema_cfg)["state"] == "due"
    # decision, 100 days old, 365d default -> fresh
    assert evaluate_note_freshness({"date": old, "type": "decision"}, schema_cfg)["state"] == "fresh"


def test_judge_no_signal_is_fresh():
    v = evaluate_note_freshness({"type": "decision"})
    assert v["state"] == "fresh" and v["due_date"] is None


# --------------------------------------------------------------------------- #
# 3. Write side: ingest/confirm use type-aware windows (F2)
# --------------------------------------------------------------------------- #
def _read_fm(od: Path, name: str) -> dict:
    text = (od / "notes" / name).read_text(encoding="utf-8")
    end = text.find("---", 3)
    return yaml.safe_load(text[3:end])


def test_ingest_writes_type_window(tmp_path):
    od = _mk_wiki(tmp_path, freshness={
        "default_window_days": 180,
        "by_type": {"workaround": 45, "decision": 365},
    })
    store = SessionStore()
    for ntype in ("workaround", "decision"):
        r = json.loads(handle_ingest_note({
            "output_dir": str(od), "title": f"n-{ntype}",
            "note_type": ntype, "content": "body", "status": "draft",
        }, store))
        assert r["status"] == "ingested", r
        name = Path(r["note_path"]).name
        fm = _read_fm(od, name)
        stale = datetime.strptime(str(fm["stale_after"])[:10], "%Y-%m-%d")
        expect = {"workaround": 45, "decision": 365}[ntype]
        assert expect - 1 <= (stale - TODAY).days <= expect, (ntype, fm["stale_after"])


def test_confirm_renews_by_type_window(tmp_path):
    od = _mk_wiki(tmp_path, freshness={
        "default_window_days": 180, "by_type": {"workaround": 45}})
    # Old workaround note whose stale_after has lapsed
    _write_note(od, "w.md", ntype="workaround", status="draft",
                stale_after=PAST)
    store = SessionStore()
    r = json.loads(handle_confirm_note(
        {"output_dir": str(od), "note_file": "w.md"}, store))
    assert "error" not in r, r
    fm = _read_fm(od, "w.md")
    assert fm["status"] == "stable"
    stale = datetime.strptime(str(fm["stale_after"])[:10], "%Y-%m-%d")
    # Renewed to ~45 days out (workaround window), not the lapsed date
    assert 44 <= (stale - TODAY).days <= 45
    # Confirmed old note is no longer stale (regression: bug 1 "确认不生效")
    assert _stats_due(_check_stale_notes(od)) == []


# --------------------------------------------------------------------------- #
# 4. lint stale_notes reads stale_after + schema config (F1)
# --------------------------------------------------------------------------- #
def test_lint_flags_lapsed_stale_after(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"default_window_days": 180})
    _write_note(od, "lapsed.md", stale_after=PAST)
    _write_note(od, "fresh.md", stale_after=FUTURE)
    due = _stats_due(_check_stale_notes(od))
    assert [i["file"] for i in due] == ["notes/lapsed.md"]
    assert "confirm_note" in due[0]["suggestion"]


def test_lint_retrieval_defer(tmp_path):
    od = _mk_wiki(tmp_path, freshness={
        "default_window_days": 180, "retrieval_defer_days": 60})
    _write_note(od, "lapsed.md", stale_after=PAST)
    _touch(od, "notes/lapsed.md", (TODAY - timedelta(days=2)).strftime("%Y-%m-%d"))
    assert _stats_due(_check_stale_notes(od)) == []


def test_lint_skips_draft_and_deprecated(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"default_window_days": 180})
    _write_note(od, "d.md", status="draft", stale_after=PAST)
    _write_note(od, "dep.md", status="deprecated", stale_after=PAST)
    assert _stats_due(_check_stale_notes(od)) == []


def test_lint_dispatch_reads_schema_config(tmp_path):
    # Tight window configured -> dispatch (no hardcoded args) must honor it.
    od = _mk_wiki(tmp_path, freshness={
        "default_window_days": 180, "by_type": {"workaround": 5}})
    # workaround confirmed 10 days ago (window 5) with a fresh date field:
    # old logic (date-age 90d) would NOT flag; new type-aware logic MUST.
    _write_note(od, "wa.md", ntype="workaround", status="stable",
                date=(TODAY - timedelta(days=10)).strftime("%Y-%m-%d"),
                stale_after=(TODAY - timedelta(days=5)).strftime("%Y-%m-%d"))
    store = SessionStore()
    resp = json.loads(handle_lint_wiki(
        {"output_dir": str(od), "checks": ["stale_notes"]}, store))
    files = [i["file"] for i in resp.get("issues", []) if i["check"] == "stale_notes"]
    assert files == ["notes/wa.md"]


def test_lint_no_double_report_with_okf(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"default_window_days": 180})
    _write_note(od, "lapsed.md", stale_after=PAST)
    store = SessionStore()
    resp = json.loads(handle_lint_wiki(
        {"output_dir": str(od), "checks": ["stale_notes", "okf_conformance"]}, store))
    lapsed_issues = [i for i in resp.get("issues", []) if i["file"] == "notes/lapsed.md"]
    checks = {i["check"] for i in lapsed_issues}
    assert checks == {"stale_notes"}  # not double-reported by okf_conformance


def test_okf_still_audits_notes_when_stale_check_absent(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"default_window_days": 180})
    _write_note(od, "lapsed.md", stale_after=PAST)
    issues = _check_stale_notes(od)
    assert len(issues) == 1
    # Without stale_notes in checks, okf_conformance still flags the note.
    from codewiki.mcp.tools.wiki_lint import _check_okf_conformance
    okf = [i for i in _check_okf_conformance(od, skip_notes_staleness=False)
           if i["file"] == "notes/lapsed.md"]
    assert any("stale_after" in i["message"] for i in okf)


# --------------------------------------------------------------------------- #
# 5. Backfill script (F3)
# --------------------------------------------------------------------------- #
def _run_migrate(od: Path, dry_run=False):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "migrate_freshness",
        Path(__file__).resolve().parents[1] / "scripts" / "migrate_freshness.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.migrate(od, dry_run=dry_run)


def test_backfill_renews_from_verified_and_is_idempotent(tmp_path):
    od = _mk_wiki(tmp_path, freshness={
        "default_window_days": 180, "by_type": {"decision": 365}})
    verified_at = TODAY - timedelta(days=10)
    _write_note(od, "v.md", ntype="decision", status="stable",
                stale_after=PAST,
                verified=[{"by": "human:alice",
                           "at": verified_at.strftime("%Y-%m-%dT00:00:00Z")}])
    _write_note(od, "nv.md", ntype="decision", status="stable", stale_after=PAST)

    stats = _run_migrate(od)
    assert stats["updated"] == 1 and stats["no_verified"] == 1
    fm = _read_fm(od, "v.md")
    expect = verified_at + timedelta(days=365)
    assert str(fm["stale_after"])[:10] == expect.strftime("%Y-%m-%d")
    # Renewed note is fresh now; nv.md stays lapsed (no verified to backfill)
    assert _freshness_distribution(od)["due"] == 1

    # Idempotent: second run changes nothing
    stats2 = _run_migrate(od)
    assert stats2["updated"] == 0 and stats2["unchanged"] == 1


def test_backfill_dry_run_writes_nothing(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"by_type": {"decision": 365}})
    verified_at = TODAY - timedelta(days=10)
    _write_note(od, "v.md", ntype="decision", status="stable", stale_after=PAST,
                verified=[{"by": "x", "at": verified_at.strftime("%Y-%m-%dT00:00:00Z")}])
    before = (od / "notes" / "v.md").read_text(encoding="utf-8")
    stats = _run_migrate(od, dry_run=True)
    assert stats["updated"] == 1
    assert (od / "notes" / "v.md").read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------- #
# 6. wiki_stats freshness distribution (F3)
# --------------------------------------------------------------------------- #
def test_wiki_stats_freshness_distribution(tmp_path):
    od = _mk_wiki(tmp_path, freshness={"default_window_days": 180})
    _write_note(od, "fresh.md", stale_after=FUTURE)
    _write_note(od, "lapsed.md", stale_after=PAST)
    _write_note(od, "draft.md", status="draft", stale_after=PAST)  # excluded
    dist = _freshness_distribution(od)
    assert dist["due"] == 1 and dist["fresh"] == 1
    assert dist["due_notes"] == ["notes/lapsed.md"]

    store = SessionStore()
    resp = json.loads(handle_wiki_stats({"output_dir": str(od)}, store))
    # No retrieval stats db yet -> error path still carries freshness
    assert resp.get("freshness", {}).get("due") == 1
