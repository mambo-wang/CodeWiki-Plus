"""Tests for the promote/晋升 mechanism (P1 C-line).

Covers docs/知识飞轮增强设计方案-P1三项.md §4 acceptance criteria:
  - _promotion_candidates: candidate judgment (stable + adopted >=
    min_adopted + age >= min_age_days, metadata.promoted_to exclusion,
    verified[-1].at age fallback)
  - wiki_stats mounts the promotion_candidates section
  - schema.yaml conventions.promotion threshold overrides
  - suggested page_type routing (pitfall → query, lesson → concept)
  - promote-note workflow prompt: handler content + registration
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from codewiki.mcp.prompts import _prompt_promote_note, register
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.adoption import record_adoption_events
from codewiki.mcp.tools.knowledge_loop import (
    _promotion_candidates,
    handle_wiki_stats,
)


# --------------------------------------------------------------------------- #
# Helpers (fixture style follows tests/test_query_transparency.py)
# --------------------------------------------------------------------------- #
def _mk_wiki(tmp_path) -> Path:
    od = tmp_path / "repowiki"
    (od / "notes").mkdir(parents=True, exist_ok=True)
    (od / ".meta").mkdir(parents=True, exist_ok=True)
    return od


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _write_note(
    od: Path,
    name: str,
    *,
    note_type: str = "pitfall",
    status: str = "stable",
    date: str | None = None,
    verified_at: str | None = None,
    promoted_to: str | None = None,
) -> None:
    """Write one note with OKF-style frontmatter (metadata: nested block)."""
    fm = [
        "---",
        f"type: {note_type}",
        f"title: {name.removesuffix('.md')}",
        'tags: ["test"]',
        "metadata:",
    ]
    if date:
        fm.append(f"  date: {date}")
    if promoted_to:
        fm.append(f"  promoted_to: {promoted_to}")
    fm.append(f"status: {status}")
    if verified_at:
        fm.append("verified:")
        fm.append("  - by: codewiki/1.0")
        fm.append(f"    at: {verified_at}")
    fm.append("---")
    (od / "notes" / name).write_text("\n".join(fm) + "\n\nbody content\n", encoding="utf-8")


def _seed_adoption(od: Path, doc_path: str, count: int) -> None:
    """Record *count* adoption events (distinct capture keys; T2 jsonl)."""
    for i in range(count):
        record_adoption_events(od, f"tester/sess-{i}", [doc_path])


def _seed_stats_table(od: Path, doc_path: str) -> None:
    """Seed hit events so wiki_stats has usage rows to report (T2 jsonl)."""
    from tests.telemetry_seed import seed_hits

    seed_hits(od, {doc_path: (5, _days_ago(1))})


# --------------------------------------------------------------------------- #
# C1: candidate judgment
# --------------------------------------------------------------------------- #
class TestPromotionCandidates:
    def test_full_candidate(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", note_type="pitfall", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 3)
        cands = _promotion_candidates(od)
        assert cands and len(cands) == 1
        c = cands[0]
        assert c["file"] == "notes/note-a.md"
        assert c["title"] == "note-a"
        assert c["type"] == "pitfall"
        assert c["adopted_count"] == 3
        assert c["age_days"] >= 15
        assert c["suggested_page_type"] == "query"

    def test_adopted_below_threshold_not_candidate(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 2)
        assert _promotion_candidates(od) == []

    def test_draft_status_not_candidate(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", status="draft", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 5)
        assert _promotion_candidates(od) == []

    def test_promoted_to_marker_excludes(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(
            od,
            "note-a.md",
            date=_days_ago(15),
            promoted_to="wiki/queries/note-a.md",
        )
        _seed_adoption(od, "notes/note-a.md", 5)
        assert _promotion_candidates(od) == []

    def test_too_young_not_candidate(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", date=_days_ago(10))
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od) == []

    def test_legacy_confirmed_status_counts_as_stable(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", status="confirmed", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 3)
        cands = _promotion_candidates(od)
        assert cands and cands[0]["file"] == "notes/note-a.md"

    def test_no_notes_dir_returns_none(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        assert _promotion_candidates(od) is None

    def test_no_adoption_data_returns_empty(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", date=_days_ago(15))
        assert _promotion_candidates(od) == []


# --------------------------------------------------------------------------- #
# age fallback: verified[-1].at when metadata.date is absent
# --------------------------------------------------------------------------- #
class TestAgeFallback:
    def test_verified_at_used_when_no_date(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(
            od,
            "note-a.md",
            verified_at=(datetime.now() - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        _seed_adoption(od, "notes/note-a.md", 3)
        cands = _promotion_candidates(od)
        assert cands and cands[0]["age_days"] >= 20

    def test_date_preferred_over_verified(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(
            od,
            "note-a.md",
            date=_days_ago(30),
            verified_at=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        _seed_adoption(od, "notes/note-a.md", 3)
        cands = _promotion_candidates(od)
        assert cands and cands[0]["age_days"] >= 30

    def test_unparseable_dates_yield_zero_age(self, tmp_path):
        od = _mk_wiki(tmp_path)
        # no date, no verified → age 0 → cannot pass the gate
        _write_note(od, "note-a.md")
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od) == []


# --------------------------------------------------------------------------- #
# suggested page_type routing
# --------------------------------------------------------------------------- #
class TestTypeRouting:
    def test_pitfall_maps_to_query(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", note_type="pitfall", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od)[0]["suggested_page_type"] == "query"

    def test_lesson_maps_to_concept(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", note_type="lesson", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od)[0]["suggested_page_type"] == "concept"

    def test_general_leaves_blank(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", note_type="general", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od)[0]["suggested_page_type"] == ""


# --------------------------------------------------------------------------- #
# schema.yaml threshold overrides
# --------------------------------------------------------------------------- #
class TestSchemaOverride:
    def test_min_adopted_override(self, tmp_path):
        import yaml

        od = _mk_wiki(tmp_path)
        (od / "schema.yaml").write_text(
            yaml.safe_dump({"conventions": {"promotion": {"min_adopted": 1, "min_age_days": 14}}}),
            encoding="utf-8",
        )
        _write_note(od, "note-a.md", date=_days_ago(15))
        _seed_adoption(od, "notes/note-a.md", 1)
        cands = _promotion_candidates(od)
        assert cands and cands[0]["adopted_count"] == 1

    def test_min_age_days_override(self, tmp_path):
        import yaml

        od = _mk_wiki(tmp_path)
        (od / "schema.yaml").write_text(
            yaml.safe_dump({"conventions": {"promotion": {"min_adopted": 3, "min_age_days": 30}}}),
            encoding="utf-8",
        )
        _write_note(od, "note-a.md", date=_days_ago(20))
        _seed_adoption(od, "notes/note-a.md", 3)
        assert _promotion_candidates(od) == []

    def test_config_from_repo_schema_files(self):
        # The shipped schema templates must carry the promotion thresholds.
        import yaml

        root = Path(__file__).resolve().parent.parent
        for rel in ("schema.yaml", "codewiki/templates/schema.yaml"):
            data = yaml.safe_load((root / rel).read_text(encoding="utf-8"))
            promo = data["conventions"]["promotion"]
            assert promo["min_adopted"] == 3
            assert promo["min_age_days"] == 14


# --------------------------------------------------------------------------- #
# wiki_stats mounting
# --------------------------------------------------------------------------- #
class TestWikiStatsMounting:
    def test_wiki_stats_surfaces_promotion_candidates(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", date=_days_ago(15))
        _seed_stats_table(od, "notes/note-a.md")
        _seed_adoption(od, "notes/note-a.md", 3)
        out = json.loads(handle_wiki_stats({"output_dir": str(od)}, SessionStore()))
        assert "promotion_candidates" in out
        cands = out["promotion_candidates"]
        assert len(cands) == 1
        assert cands[0]["file"] == "notes/note-a.md"
        assert cands[0]["adopted_count"] == 3
        assert cands[0]["suggested_page_type"] == "query"

    def test_wiki_stats_omits_when_no_candidates(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-a.md", date=_days_ago(15))
        _seed_stats_table(od, "notes/note-a.md")
        _seed_adoption(od, "notes/note-a.md", 1)
        out = json.loads(handle_wiki_stats({"output_dir": str(od)}, SessionStore()))
        assert "promotion_candidates" not in out

    def test_ranked_by_adopted_count(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _write_note(od, "note-low.md", date=_days_ago(15))
        _write_note(od, "note-high.md", date=_days_ago(15))
        _seed_adoption(od, "notes/note-low.md", 3)
        _seed_adoption(od, "notes/note-high.md", 7)
        cands = _promotion_candidates(od)
        assert [c["file"] for c in cands] == [
            "notes/note-high.md",
            "notes/note-low.md",
        ]


# --------------------------------------------------------------------------- #
# C2: promote-note workflow prompt
# --------------------------------------------------------------------------- #
class _FakeServer:
    """Minimal stand-in capturing the decorators used by prompts.register."""

    def list_prompts(self):
        def deco(fn):
            self._list = fn
            return fn

        return deco

    def get_prompt(self):
        def deco(fn):
            self._get = fn
            return fn

        return deco


class TestPromoteNotePrompt:
    def test_handler_contains_key_sections(self):
        text = _prompt_promote_note({})
        # 前置说明：候选来源
        assert "promotion_candidates" in text
        assert "wiki_stats" in text
        # 类型路由映射表
        assert "pitfall" in text and "query" in text
        assert "lesson" in text and "concept" in text
        assert "general" in text
        # 重写规则（去个人化）
        assert "症状" in text and "根因" in text
        assert "aliases" in text
        # draft 评审闸门
        assert "draft" in text
        assert "confirm" in text.lower() or "confirm_note" in text
        # 回标规则：metadata 嵌套段下的 promoted_to
        assert "metadata:" in text
        assert "promoted_to" in text
        assert "顶层" in text  # 不能写顶层的警告
        # 执行步骤工具
        assert "write_doc_file" in text
        assert "edit_doc_file" in text
        # 原笔记保留
        assert "不删除" in text

    def test_handler_interpolates_arguments(self):
        text = _prompt_promote_note(
            {
                "note_file": "notes/2026-08-01-port-conflict.md",
                "output_dir": "D:/repo/repowiki",
            }
        )
        assert "notes/2026-08-01-port-conflict.md" in text
        assert "D:/repo/repowiki" in text

    def test_registered_in_prompt_list(self):
        srv = _FakeServer()
        register(srv)
        prompts = asyncio.run(srv._list())
        names = [p.name for p in prompts]
        assert "promote-note" in names
        entry = next(p for p in prompts if p.name == "promote-note")
        arg_names = {a.name for a in entry.arguments}
        assert {"note_file", "output_dir", "repo_path"} <= arg_names

    def test_get_prompt_dispatches_to_handler(self):
        srv = _FakeServer()
        register(srv)
        result = asyncio.run(srv._get("promote-note", {"note_file": "notes/x.md"}))
        text = result.messages[0].content.text
        assert "notes/x.md" in text
        assert "promoted_to" in text
