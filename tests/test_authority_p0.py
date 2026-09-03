"""Tests for P0 authority-weighted ranking (borrowed from ai-memory PageAuthority).

Covers the ai-memory调研报告 P0 item 3: BM25 score × deterministic authority
factor (note_type boost + OKF status gate + L2/L3 page boost + raw/sources
penalty), computed at index time, clamped 0.7-1.3, applied AFTER BM25 and
BEFORE the note title floor. Similarity-oriented consumers (distill dedup
recall) are exempt via apply_authority=False.
"""

from pathlib import Path

from codewiki.mcp.cache import AnalysisCache
from codewiki.src.retrieval import doc_authority as _doc_authority
from codewiki.mcp.tools import wiki_search


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_note(notes_dir: Path, name: str, title: str, ntype: str, status: str, body: str) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    p = notes_dir / name
    p.write_text(
        f"---\ntype: {ntype}\ntitle: {title}\nstatus: {status}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# 1. _doc_authority rule table
# --------------------------------------------------------------------------- #
def test_authority_note_type_and_status():
    decision_stable = "---\ntype: decision\ntitle: T\nstatus: stable\n---\nbody"
    lesson_draft = "---\ntype: lesson\ntitle: T\nstatus: draft\n---\nbody"
    assert _doc_authority("notes/a.md", "note", decision_stable) == 1.2  # +0.15 +0.05
    assert _doc_authority("notes/b.md", "note", lesson_draft) == 0.85  # +0.10 -0.25


def test_authority_deprecated_clamped_low():
    dep = "---\ntype: pitfall\ntitle: T\nstatus: deprecated\n---\nbody"  # +0.12 -0.35
    assert abs(_doc_authority("notes/c.md", "note", dep) - 0.77) < 1e-9
    bare_dep = "---\ntitle: T\nstatus: deprecated\n---\nbody"  # -0.35 -> clamp 0.7
    assert _doc_authority("notes/d.md", "note", bare_dep) == 0.7


def test_authority_l2_l3_boost_and_sources_penalty():
    assert _doc_authority("wiki/scenarios/x.md", "doc", "# X") == 1.15
    assert _doc_authority("wiki/doctrine.md", "doc", "# D") == 1.2
    assert _doc_authority("wiki/modules/order.md", "doc", "# O") == 1.0
    assert _doc_authority("raw/sources/vendor.md", "source", "text") == 0.8


def test_authority_metadata_folded_fields():
    # OKF folding: type/status may live under metadata:
    folded = "---\nmetadata:\n  type: decision\n  status: stable\n---\nbody"
    assert _doc_authority("notes/e.md", "note", folded) == 1.2


# --------------------------------------------------------------------------- #
# 2. SQLite path: ranking + exemption semantics
# --------------------------------------------------------------------------- #
def test_sqlite_search_orders_by_authority(tmp_path):
    od = tmp_path / "repowiki"
    notes = od / "notes"
    shared = "gateway timeout retry budget configuration"
    _mk_note(notes, "n-decision.md", "gateway timeout choice", "decision", "stable", shared)
    _mk_note(notes, "n-lesson.md", "gateway timeout retro", "lesson", "draft", shared)

    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        res = cache.search("gateway timeout retry", output_dir=od)
        assert len(res) == 2
        assert res[0]["file"] == "notes/n-decision.md"
        assert res[0]["authority"] == 1.2
        assert res[1]["authority"] == 0.85
        # Exemption: identical bodies -> identical raw BM25 scores, authority 1.0
        raw = cache.search("gateway timeout retry", output_dir=od, apply_authority=False)
        by_file = {r["file"]: r for r in raw}
        assert (
            by_file["notes/n-decision.md"]["relevance_score"]
            == by_file["notes/n-lesson.md"]["relevance_score"]
        )
        assert all(r["authority"] == 1.0 for r in raw)
    finally:
        cache.close()


# --------------------------------------------------------------------------- #
# 3. Legacy JSON path: ranking + incremental authority refresh
# --------------------------------------------------------------------------- #
def test_legacy_search_orders_by_authority(tmp_path):
    od = tmp_path / "repowiki"
    notes = od / "notes"
    shared = "gateway timeout retry budget configuration"
    _mk_note(notes, "n-decision.md", "gateway timeout choice", "decision", "stable", shared)
    _mk_note(notes, "n-lesson.md", "gateway timeout retro", "lesson", "draft", shared)

    wiki_search.build_full_index(od)  # no session / no DB -> legacy JSON index
    res = wiki_search.search(od, "gateway timeout retry")
    assert len(res) == 2
    assert res[0]["file"] == "notes/n-decision.md"
    assert res[0]["authority"] == 1.2
    assert res[1]["authority"] == 0.85


def test_update_file_refreshes_authority_after_status_change(tmp_path):
    od = tmp_path / "repowiki"
    p = _mk_note(
        od / "notes",
        "n.md",
        "cache invalidation strategy",
        "lesson",
        "draft",
        "cache invalidation strategy body text",
    )
    wiki_search.build_full_index(od)
    res = wiki_search.search(od, "cache invalidation strategy")
    assert res and res[0]["file"] == "notes/n.md"
    assert res[0]["authority"] == 0.85

    # Promote draft -> stable (mirrors _apply_status_to_file rewriting status)
    p.write_text(
        p.read_text(encoding="utf-8").replace("status: draft", "status: stable"), encoding="utf-8"
    )
    wiki_search.update_file(od, p)
    res2 = wiki_search.search(od, "cache invalidation strategy")
    assert res2 and res2[0]["authority"] == 1.15  # lesson +0.10, stable +0.05


# --------------------------------------------------------------------------- #
# 4. Distill dedup exemption contract
# --------------------------------------------------------------------------- #
def test_distill_dedup_recall_disables_authority(tmp_path, monkeypatch):
    from codewiki.mcp.tools import distill_conversation as distill
    from codewiki.mcp.tools import wiki_search as ws

    seen = {}

    def fake_search(output_dir, query, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(ws, "search", fake_search)
    distill._bm25_recall_candidates("some title", "some body text", tmp_path)
    assert seen.get("apply_authority") is False
