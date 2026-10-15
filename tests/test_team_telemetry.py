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
from datetime import datetime, timedelta
from pathlib import Path


from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.capture_conversation import handle_capture_conversation
from codewiki.mcp.tools.telemetry import (
    aggregate_usage,
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
            json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return out


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestUserId:
    def test_env_override_first(self, monkeypatch):
        from codewiki.src.config import user_id

        monkeypatch.setenv("CODEWIKI_USER", "pseudonym-x")
        assert user_id() == "pseudonym-x"

    def test_env_override_beats_repo_pin(self, monkeypatch, tmp_path):
        from codewiki.src.config import user_id

        _write_pin(tmp_path, "pinned-user")
        monkeypatch.setenv("CODEWIKI_USER", "pseudonym-x")
        assert user_id(tmp_path) == "pseudonym-x"

    def test_git_config_fallback(self, monkeypatch, tmp_path):
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        uid, source = resolve_user_id(tmp_path)
        assert uid == "ci-example-com"
        assert source == "git-email"
        # filename-safe: only [A-Za-z0-9_-]
        assert all(c.isalnum() or c in "-_" for c in uid)


class TestRepoIdentityPin:
    """B: the repo-local pin is what keeps one person in one shard across channels."""

    def test_pin_outranks_machine_cache_and_git(self, monkeypatch, tmp_path):
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _write_pin(tmp_path, "pinned-user")
        _degrade_to_git(monkeypatch, cfg_module, email="other@example.com", cache="cache-user")
        assert resolve_user_id(tmp_path) == ("pinned-user", "pin")

    def test_first_derivation_pins_the_clone(self, monkeypatch, tmp_path):
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        assert resolve_user_id(tmp_path) == ("ci-example-com", "git-email")
        assert _read_pin(tmp_path) == "ci-example-com"

    def test_degraded_channel_inherits_pinned_identity(self, monkeypatch, tmp_path):
        """The drift regression: a service-state MCP server has neither the
        machine cache nor a readable git config, and used to fall through to
        os.getlogin() — splitting one person over memories/<email>.md and
        memories/Administrator.md."""
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id, user_id

        # Channel 1: a normal login shell derives the identity and pins it.
        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        assert user_id(tmp_path) == "ci-example-com"

        # Channel 2: same clone, environment stripped of every input but the clone.
        _degrade_to_git(monkeypatch, cfg_module, email="", login="Administrator")
        uid, source = resolve_user_id(tmp_path)
        assert (uid, source) == ("ci-example-com", "pin")

    def test_pin_without_output_dir_still_resolves(self, monkeypatch):
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        uid, source = resolve_user_id(None)
        assert source == "git-email"
        assert uid == "ci-example-com"

    def test_hostile_pin_is_sanitized(self, monkeypatch, tmp_path):
        """The uid becomes a filename component; a foreign pin must not smuggle a path."""
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _write_pin(tmp_path, "../../escape")
        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        uid, source = resolve_user_id(tmp_path)
        assert source == "pin"
        assert "/" not in uid and "\\" not in uid and ".." not in uid

    def test_readable_git_beats_a_poisoned_cache(self, monkeypatch, tmp_path):
        """The cache only memoizes some past derivation — which may have been a
        degraded channel's login-name fallback. A readable git config outranks it,
        otherwise the wrong identity gets re-pinned onto the clone forever."""
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, cache="Administrator", email="ci@example.com")
        assert resolve_user_id(tmp_path) == ("ci-example-com", "git-email")
        assert _read_pin(tmp_path) == "ci-example-com"

    def test_cache_without_git_is_used_but_never_pinned(self, monkeypatch, tmp_path):
        """A channel that cannot run git has nothing to verify against: use the
        memoized id for this call, but do not promote it to the clone's identity."""
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, cache="cached-user")
        assert resolve_user_id(tmp_path) == ("cached-user", "cache")
        assert _read_pin(tmp_path) == ""

    def test_login_derived_identity_is_never_pinned(self, monkeypatch, tmp_path):
        """A stripped environment must not freeze its machine account for the clone."""
        from codewiki.src import config as cfg_module
        from codewiki.src.config import resolve_user_id

        _degrade_to_git(monkeypatch, cfg_module, login="Administrator")
        assert resolve_user_id(tmp_path) == ("Administrator", "login")
        assert _read_pin(tmp_path) == ""

        # The next healthy channel pins the person identity instead.
        _degrade_to_git(monkeypatch, cfg_module, email="ci@example.com")
        assert resolve_user_id(tmp_path) == ("ci-example-com", "git-email")
        assert _read_pin(tmp_path) == "ci-example-com"

    def test_pin_is_gitignored_and_rebuildable(self):
        from codewiki.src.config import TEAM_LAYOUT_REBUILDABLE_FILES

        assert ".meta/user_id" in TEAM_LAYOUT_REBUILDABLE_FILES


def _write_pin(output_dir: Path, uid: str) -> None:
    (output_dir / ".meta").mkdir(parents=True, exist_ok=True)
    (output_dir / ".meta" / "user_id").write_text(uid, encoding="utf-8")


def _read_pin(output_dir: Path) -> str:
    path = output_dir / ".meta" / "user_id"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _degrade_to_git(monkeypatch, cfg_module, email="", name="", cache="", login="") -> None:
    """Strip every identity input except the ones the test supplies.

    The machine cache, the git lookups and the login name are all process-
    environment artifacts; tests must not depend on the real machine's values.
    """
    monkeypatch.delenv("CODEWIKI_USER", raising=False)
    monkeypatch.setattr(cfg_module, "_GIT_USER_EMAIL_CACHE", {})
    monkeypatch.setattr(cfg_module, "_GIT_USER_NAME_CACHE", {})
    monkeypatch.setattr(cfg_module, "_read_user_id_cache", lambda: cache)
    monkeypatch.setattr(cfg_module, "_write_user_id_cache", lambda uid: None)
    monkeypatch.setattr(cfg_module, "_git_user_email", lambda lookup_dir=None: email)
    monkeypatch.setattr(cfg_module, "_git_user_name", lambda lookup_dir=None: name)
    monkeypatch.setattr(cfg_module, "_login_name", lambda: login)


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
                json.dumps({"t": "hit", "doc": "notes/a.md", "at": _days_ago(1), "n": n}) + "\n",
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
        (p / "u.jsonl").write_text("\n".join(json.dumps(e) for e in lines) + "\n", encoding="utf-8")
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["adopted"] == 2  # distinct keys only

    def test_bad_line_skipped(self, tmp_path):
        p = tmp_path / ".meta" / "telemetry"
        p.mkdir(parents=True)
        (p / "u.jsonl").write_text(
            "not json at all\n"
            + json.dumps({"t": "hit", "doc": "notes/a.md", "at": _days_ago(0), "n": 4})
            + "\n",
            encoding="utf-8",
        )
        agg = aggregate_usage(tmp_path)
        assert agg["notes/a.md"]["hits"] == 4

    def test_mtime_cache_invalidates(self, tmp_path):
        record_hit(tmp_path, "notes/a.md", 1)
        assert aggregate_usage(tmp_path)["notes/a.md"]["hits"] == 1
        record_hit(tmp_path, "notes/a.md", 2)  # mtime changes
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
        write_telemetry(
            a,
            "alice",
            [
                {"t": "hit", "doc": "notes/x.md", "at": _days_ago(1), "n": 6},
                {
                    "t": "adopted",
                    "doc": "notes/x.md",
                    "at": "2026-08-22T10:00:00",
                    "key": "alice/sess-1",
                },
            ],
        )

        # simulate pull: md + telemetry land in user B's checkout
        b = tmp_path / "b" / "repowiki"
        b.mkdir(parents=True)
        (b / "notes").mkdir()
        (b / "notes" / "x.md").write_text("---\ntitle: x\n---\nbody", encoding="utf-8")
        import shutil

        shutil.copytree(a / ".meta" / "telemetry", b / ".meta" / "telemetry", dirs_exist_ok=True)

        agg = aggregate_usage(b)
        assert agg["notes/x.md"]["hits"] == 6
        assert agg["notes/x.md"]["adopted"] == 1


class TestLocalMode:
    def test_disabled_writes_to_local_dir(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        (od / "schema.yaml").write_text(
            "conventions:\n  telemetry:\n    enabled: false\n", encoding="utf-8"
        )
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
        (od / "notes" / "pit.md").write_text("---\ntitle: t\n---\nbody", encoding="utf-8")
        turns = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": 'a\n<!-- codewiki:referenced-docs: ["notes/pit.md"] -->',
            },
        ]
        res = json.loads(
            handle_capture_conversation(
                {
                    "output_dir": str(od),
                    "repo_path": str(tmp_path),
                    "conversation": turns,
                    "source_session_id": "sess-42",
                },
                SessionStore(),
            )
        )
        assert res.get("adopted_docs") == ["notes/pit.md"]
        # event landed in the CURRENT user's stream (user-dependent name)
        files = list((od / ".meta" / "telemetry").glob("*.jsonl"))
        assert len(files) == 1
        events = [
            json.loads(line)
            for line in files[0].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(e["t"] == "adopted" and e["doc"] == "notes/pit.md" for e in events)
