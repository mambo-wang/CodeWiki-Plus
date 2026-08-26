"""Tests for the adoption-signal pipeline (P1 A-line).

Covers docs/知识飞轮增强设计方案-P1三项.md §2 acceptance criteria:
  - extract_adopted_docs: parse matrix (valid/invalid JSON, path
    normalisation, existence filter, multiple declarations, no declaration)
  - record_adoption_events: idempotency (same capture_key re-capture does
    not double-count; a newly declared doc under the same key counts once)
  - compute_usage_heat: adoption weight (2x recall), boost_cap still caps,
    adopted_weight=0 degrades to the pre-A-line behaviour
  - capture integration: declared docs persisted + adoption_nudge only when
    search traces exist without any declaration
"""
from __future__ import annotations

import json


from codewiki.mcp.cache import USAGE_RANKING_DEFAULTS, compute_usage_heat
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.adoption import (
    extract_adopted_docs,
    load_adoption_counts,
    record_adoption_events,
)
from codewiki.mcp.tools.capture_conversation import handle_capture_conversation


# --------------------------------------------------------------------------- #
# extract_adopted_docs (pure function)
# --------------------------------------------------------------------------- #
DECL = '<!-- codewiki:referenced-docs: ["notes/pitfall-a.md"] -->'


def _turns(*contents, role="assistant"):
    return [{"role": role, "content": c} for c in contents]


class TestExtractAdoptedDocs:
    def test_basic_declaration(self):
        turns = _turns(
            f"answer text\n{DECL}\nmore text",
        )
        assert extract_adopted_docs(turns) == ["notes/pitfall-a.md"]

    def test_multiple_docs_and_dedup_sorted(self):
        turns = _turns(
            '<!-- codewiki:referenced-docs: ["notes/b.md", "wiki/a.md"] -->',
            '<!-- codewiki:referenced-docs: ["notes/b.md"] -->',
        )
        assert extract_adopted_docs(turns) == ["notes/b.md", "wiki/a.md"]

    def test_path_normalisation(self):
        turns = _turns(
            '<!-- codewiki:referenced-docs: [".\\\\notes\\\\win.md", "/notes/abs.md", "./notes/rel.md"] -->',
        )
        assert extract_adopted_docs(turns) == [
            "notes/abs.md", "notes/rel.md", "notes/win.md",
        ]

    def test_rejects_traversal_and_empty(self):
        turns = _turns(
            '<!-- codewiki:referenced-docs: ["../../etc/passwd", "", "ok.md"] -->',
        )
        assert extract_adopted_docs(turns) == ["ok.md"]

    def test_invalid_json_skipped(self):
        turns = _turns(
            '<!-- codewiki:referenced-docs: ["broken.md" -->',
            '<!-- codewiki:referenced-docs: not-json -->',
            '<!-- codewiki:referenced-docs: {"a": 1} -->',
        )
        assert extract_adopted_docs(turns) == []

    def test_non_list_payload_skipped(self):
        turns = _turns('<!-- codewiki:referenced-docs: "notes/x.md" -->')
        assert extract_adopted_docs(turns) == []

    def test_only_assistant_turns_scanned(self):
        turns = [
            {"role": "user", "content": DECL},
            {"role": "assistant", "content": "clean answer"},
        ]
        assert extract_adopted_docs(turns) == []

    def test_existence_filter(self):
        turns = _turns(
            '<!-- codewiki:referenced-docs: ["exists.md", "missing.md"] -->',
        )
        def _exists(p):
            return p == "exists.md"
        assert extract_adopted_docs(turns, existing=_exists) == ["exists.md"]

    def test_prose_mention_does_not_match(self):
        turns = _turns(
            "The field codewiki:referenced-docs is documented elsewhere.",
        )
        assert extract_adopted_docs(turns) == []

    def test_empty_turns(self):
        assert extract_adopted_docs([]) == []


# --------------------------------------------------------------------------- #
# record_adoption_events / load_adoption_counts (persistence)
# --------------------------------------------------------------------------- #
class TestAdoptionEvents:
    """T2: persistence moved from adoption_events table to telemetry jsonl."""

    def test_insert_and_count(self, tmp_path):
        n = record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md", "notes/b.md"])
        assert n == 2
        assert load_adoption_counts(tmp_path) == {
            "notes/a.md": 1, "notes/b.md": 1,
        }

    def test_idempotent_same_key(self, tmp_path):
        record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md"])
        assert record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md"]) == 0
        assert load_adoption_counts(tmp_path) == {"notes/a.md": 1}

    def test_new_doc_same_key_counts(self, tmp_path):
        # supersede re-capture that declares one more doc
        record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md"])
        n = record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md", "notes/b.md"])
        assert n == 1
        assert load_adoption_counts(tmp_path) == {
            "notes/a.md": 1, "notes/b.md": 1,
        }

    def test_different_sessions_accumulate(self, tmp_path):
        record_adoption_events(tmp_path, "tester/sess-1", ["notes/a.md"])
        record_adoption_events(tmp_path, "tester/sess-2", ["notes/a.md"])
        assert load_adoption_counts(tmp_path) == {"notes/a.md": 2}

    def test_empty_paths_noop(self, tmp_path):
        assert record_adoption_events(tmp_path, "tester/sess-1", []) == 0

    def test_missing_db_returns_empty(self, tmp_path):
        assert load_adoption_counts(tmp_path) == {}

    def test_no_telemetry_data_tolerated(self, tmp_path):
        # empty output dir (no telemetry files at all)
        assert load_adoption_counts(tmp_path) == {}


# --------------------------------------------------------------------------- #
# compute_usage_heat adoption weighting
# --------------------------------------------------------------------------- #
class TestHeatAdoption:
    def test_adoption_boosts_more_than_recall(self):
        cfg = dict(USAGE_RANKING_DEFAULTS)
        h_recall_only = compute_usage_heat(10, "2026-08-20", cfg)
        h_with_adoption = compute_usage_heat(10, "2026-08-20", cfg, adopted_count=5)
        assert h_with_adoption > h_recall_only

    def test_adoption_weight_ratio(self):
        cfg = dict(USAGE_RANKING_DEFAULTS)
        # recall+10 vs recall+0/adopted+5 with 2x weight: ln(11) vs 2*ln(6)
        h1 = compute_usage_heat(10, "2026-08-20", cfg, adopted_count=0)
        h2 = compute_usage_heat(0 + 1, "2026-08-20", cfg, adopted_count=5)
        # adopted=5 on 1 hit: 0.03*ln2 + 0.06*ln6 ≈ 0.137
        # hits=10 alone:      0.03*ln11        ≈ 0.072
        assert h2 > h1

    def test_boost_cap_still_caps(self):
        cfg = dict(USAGE_RANKING_DEFAULTS)
        cap = float(cfg["boost_cap"])
        huge = compute_usage_heat(10000, "2026-08-20", cfg, adopted_count=10000)
        assert huge <= 1.0 + cap + 1e-9

    def test_adopted_weight_zero_degrades(self):
        cfg = dict(USAGE_RANKING_DEFAULTS)
        cfg["adopted_weight"] = 0.0
        base = compute_usage_heat(10, "2026-08-20", cfg)
        with_ad = compute_usage_heat(10, "2026-08-20", cfg, adopted_count=50)
        assert base == with_ad

    def test_no_hits_ignores_adoption(self):
        # hit_count <= 0 short-circuits: adoption alone cannot heat a doc
        assert compute_usage_heat(0, None, None, adopted_count=10) == 1.0


# --------------------------------------------------------------------------- #
# capture integration (end-to-end through handle_capture_conversation)
# --------------------------------------------------------------------------- #
def _capture_args(tmp_path, turns, session_id=""):
    return {
        "output_dir": str(tmp_path),
        "repo_path": str(tmp_path),
        "conversation": turns,
        "source_session_id": session_id,
    }


def _make_doc(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntype: pitfall\ntitle: t\nstatus: stable\n---\nbody", encoding="utf-8")


class TestCaptureIntegration:
    def test_declared_docs_persisted(self, tmp_path):
        _make_doc(tmp_path, "notes/pitfall-a.md")
        _make_doc(tmp_path, "wiki/modules/m.md")
        turns = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content":
                "answer\n<!-- codewiki:referenced-docs:"
                ' ["notes/pitfall-a.md", "wiki/modules/m.md"] -->'},
            {"role": "user", "content": "thanks"},
            {"role": "assistant", "content": "done"},
        ]
        result = json.loads(handle_capture_conversation(_capture_args(tmp_path, turns, "s1"), SessionStore()))
        assert result["adopted_docs"] == ["notes/pitfall-a.md", "wiki/modules/m.md"]
        assert result["adoption_inserted"] == 2
        counts = load_adoption_counts(tmp_path)
        assert counts == {"notes/pitfall-a.md": 1, "wiki/modules/m.md": 1}

    def test_supersede_no_double_count(self, tmp_path):
        _make_doc(tmp_path, "notes/pitfall-a.md")
        turns1 = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content":
                'a1\n<!-- codewiki:referenced-docs: ["notes/pitfall-a.md"] -->'},
        ]
        # re-capture same session with an extended transcript
        turns2 = turns1 + [
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        handle_capture_conversation(_capture_args(tmp_path, turns1, "s1"), SessionStore())
        handle_capture_conversation(_capture_args(tmp_path, turns2, "s1"), SessionStore())
        assert load_adoption_counts(tmp_path) == {"notes/pitfall-a.md": 1}

    def test_missing_path_dropped(self, tmp_path):
        _make_doc(tmp_path, "notes/exists.md")
        turns = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content":
                'a\n<!-- codewiki:referenced-docs: ["notes/exists.md", "notes/ghost.md"] -->'},
        ]
        result = json.loads(handle_capture_conversation(_capture_args(tmp_path, turns, "s1"), SessionStore()))
        assert result["adopted_docs"] == ["notes/exists.md"]
        assert load_adoption_counts(tmp_path) == {"notes/exists.md": 1}

    def test_nudge_when_search_traces_without_declaration(self, tmp_path):
        turns = [
            {"role": "user", "content": "search it"},
            {"role": "assistant", "content":
                "based on context_package from query_wiki ..."},
        ]
        result = json.loads(handle_capture_conversation(_capture_args(tmp_path, turns, "s1"), SessionStore()))
        assert result.get("adoption_nudge") is True
        assert "adopted_docs" not in result

    def test_no_nudge_when_declared(self, tmp_path):
        _make_doc(tmp_path, "notes/a.md")
        turns = [
            {"role": "user", "content": "search it"},
            {"role": "assistant", "content":
                "based on context_package...\n"
                '<!-- codewiki:referenced-docs: ["notes/a.md"] -->'},
        ]
        result = json.loads(handle_capture_conversation(_capture_args(tmp_path, turns, "s1"), SessionStore()))
        assert "adoption_nudge" not in result

    def test_no_nudge_when_no_search_traces(self, tmp_path):
        turns = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = json.loads(handle_capture_conversation(_capture_args(tmp_path, turns, "s1"), SessionStore()))
        assert "adoption_nudge" not in result
