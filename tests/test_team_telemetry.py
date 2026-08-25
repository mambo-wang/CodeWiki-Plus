"""Tests for T2: identity + per-user telemetry streams.

Covers docs/团队知识库支持优化设计方案.md §4 acceptance criteria:
  - user_id priority: CODEWIKI_USER > git user.name > getlogin
  - record_hit same-day aggregation; record_adopted appends
  - aggregate_usage: multi-user fold, key-dedup for adoptions, bad-line skip
  - mtime snapshot cache invalidation
  - teammate pull simulation: events copied to another output_dir aggregate
  - telemetry.enabled=false switches writes to the gitignored local dir
  - capture integration: adoption declarations land in the user's stream
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import telemetry
from codewiki.mcp.tools.capture_conversation import handle_capture_conversation
from codewiki.mcp.tools.telemetry import (
    aggregate_usage,
    record_adopted,
    record_hit,
    telemetry_enabled,
)


def _all_events(od: Path) -> list:
    """All events across every user stream in the shared telemetry dir."""
    d = od / ".meta" / "telemetry"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.jsonl")):
        out.extend(
            json.loads(l)
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()
        )
    return out


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestUserId:
    def test_env_override_first(self, monkeypatch):
        from codewiki.src.config import user_id
        monkeypatch.setenv("CODEWIKI_USER", "pseudonym-x")
        assert user_id() == "pseudonym-x"

    def test_git_config_fallback(self, monkeypatch):
        from codewiki.src.config import user_id
        monkeypatch.delenv("CODEWIKI_USER", raising=False)
        uid = user_id()
        assert uid and uid != "local"
        # filename-safe: only [A-Za-z0-9_-]
        assert all(c.isalnum() or c in "-_" for c in uid)


class TestRecordHit:
    def test_same_day_same_doc_merges(self, tmp_path):
        record_hit(tmp_path, "notes/a.md", 2)
        record_hit(tmp_path, "notes/a.md", 3)
        events = _all_events(tmp_path)
        assert len(events) == 1
        assert events[0]["n"] == 5
        assert events[0]["t"] == "hit"

    def test_same_day_diff_doc_appends(self, tmp_path):
        record_hit(tmp_path, "notes/a.md")
        record_hit(tmp_path, "notes/b.md")
        assert len(_all_events(tmp_path)) == 2

    def test_hits_aggregate(self, tmp_path):
        record_hit(tmp_path, "notes/a.md", 7)
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["hits"] == 7


class TestAggregate:
    def test_multi_user_fold(self, tmp_path):
        for user, n in (("alice", 3), ("bob", 5)):
            p = tmp_path / ".meta" / "telemetry"
            p.mkdir(parents=True, exist_ok=True)
            (p / f"{user}.jsonl").write_text(
                json.dumps({"t": "hit", "doc": "notes/a.md",
                            "at": _days_ago(1), "n": n}) + "\n",
                encoding="utf-8",
            )
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["hits"] == 8

    def test_adoption_key_dedup(self, tmp_path):
        p = tmp_path / ".meta" / "telemetry"
        p.mkdir(parents=True)
        lines = [
            {"t": "adopted", "doc": "notes/a.md", "at": "x", "key": "u/s1"},
            {"t": "adopted", "doc": "notes/a.md", "at": "y", "key": "u/s1"},  # dup
            {"t": "adopted", "doc": "notes/a.md", "at": "z", "key": "u/s2"},
        ]
        (p / "u.jsonl").write_text(
            "\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["adopted"] == 2  # distinct keys only

    def test_bad_line_skipped(self, tmp_path):
        p = tmp_path / ".meta" / "telemetry"
        p.mkdir(parents=True)
        (p / "u.jsonl").write_text(
            "not json at all\n"
            + json.dumps({"t": "hit", "doc": "notes/a.md",
                          "at": _days_ago(0), "n": 4}) + "\n",
            encoding="utf-8")
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["hits"] == 4

    def test_mtime_cache_invalidates(self, tmp_path):
        record_hit(tmp_path, "notes/a.md", 1)
        assert aggregate_usage(tmp_path)["notes/a.md"]["hits"] == 1
        record_hit(tmp_path, "notes/a.md", 2)   # mtime changes
        assert aggregate_usage(tmp_path)["notes/a.md"]["hits"] == 3

    def test_missing_dirs_empty(self, tmp_path):
        assert aggregate_usage(tmp_path) == {}


class TestTeammatePull:
    def test_events_flow_to_other_checkout(self, tmp_path):
        # user A's checkout — alice's events written under her own name
        # (write_telemetry pins the user file; record_* uses the machine user)
        from tests.telemetry_seed import write_telemetry
        a = tmp_path / "a" / "repowiki"
        (a / "notes").mkdir(parents=True)
        (a / "notes" / "x.md").write_text("---\ntitle: x\n---\nbody", encoding="utf-8")
        write_telemetry(a, "alice", [
            {"t": "hit", "doc": "notes/x.md", "at": _days_ago(1), "n": 6},
            {"t": "adopted", "doc": "notes/x.md", "at": "2026-08-22T10:00:00",
             "key": "alice/sess-1"},
        ])

        # simulate pull: md + telemetry land in user B's checkout
        b = tmp_path / "b" / "repowiki"
        b.mkdir(parents=True)
        (b / "notes").mkdir()
        (b / "notes" / "x.md").write_text("---\ntitle: x\n---\nbody", encoding="utf-8")
        import shutil
        shutil.copytree(
            a / ".meta" / "telemetry", b / ".meta" / "telemetry", dirs_exist_ok=True)

        agg = aggregate_usage(b)
        assert agg["notes/x.md"]["hits"] == 6
        assert agg["notes/x.md"]["adopted"] == 1


class TestLocalMode:
    def test_disabled_writes_to_local_dir(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        (od / "schema.yaml").write_text(
            "conventions:\n  telemetry:\n    enabled: false\n", encoding="utf-8")
        assert telemetry_enabled(od) is False
        record_hit(od, "notes/a.md", 2)
        assert not (od / ".meta" / "telemetry").exists()
        assert (od / ".meta" / "telemetry-local").exists()
        # aggregation still sees the events
        assert aggregate_usage(od)["notes/a.md"]["hits"] == 2


class TestCaptureIntegration:
    def test_adoption_declared_in_conversation_recorded(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        (od / "notes").mkdir()
        (od / "notes" / "pit.md").write_text(
            "---\ntitle: t\n---\nbody", encoding="utf-8")
        turns = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content":
                'a\n<!-- codewiki:referenced-docs: ["notes/pit.md"] -->'},
        ]
        res = json.loads(handle_capture_conversation({
            "output_dir": str(od), "repo_path": str(tmp_path),
            "conversation": turns, "source_session_id": "sess-42",
        }, SessionStore()))
        assert res.get("adopted_docs") == ["notes/pit.md"]
        # event landed in the CURRENT user's stream (user-dependent name)
        files = list((od / ".meta" / "telemetry").glob("*.jsonl"))
        assert len(files) == 1
        events = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines() if l.strip()]
        assert any(e["t"] == "adopted" and e["doc"] == "notes/pit.md" for e in events)
