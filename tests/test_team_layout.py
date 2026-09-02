"""Tests for team-layout Phase 1 (D1/D5/D7): rebuildable files out of git.

Covers:
* append_log monthly sharding (log-YYYY-MM.md, ascending, pure append);
* WIKI_SYSTEM_FILES membership matching log shards (scanner exclusion);
* ensure_index self-heal (missing wiki/index.md rebuilt on read path);
* schema.yaml churn suppression (timestamp-only drift → no write-back);
* lint check team_layout_gitignore + init_wiki .gitignore hygiene;
* the migrate-team-layout core (list_tracked_rebuildables / untrack /
  ensure_gitignore_entries) on a real temp git repository.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from codewiki.mcp.tools import team_layout as tl
from codewiki.mcp.tools.init_wiki import handle_init_wiki
from codewiki.mcp.tools.schema_generator import generate_schema
from codewiki.mcp.tools.wiki_index import append_log, ensure_index
from codewiki.src.config import WIKI_SYSTEM_FILES


# ---------------------------------------------------------------------------
# D5: append_log monthly shards
# ---------------------------------------------------------------------------


def test_append_log_writes_monthly_shard_not_log_md(tmp_path):
    append_log(tmp_path, "write_doc_file", "Created foo.md")
    shard = tmp_path / "wiki" / f"log-{datetime.now().strftime('%Y-%m')}.md"
    assert shard.exists()
    text = shard.read_text(encoding="utf-8")
    assert text.startswith("# 操作日志 · ")
    assert "## " in text and "write_doc_file" in text
    # legacy log.md is never created again
    assert not (tmp_path / "wiki" / "log.md").exists()


def test_append_log_same_day_pure_append(tmp_path):
    append_log(tmp_path, "write_doc_file", "first")
    append_log(tmp_path, "ingest_note", "second")
    shard = tmp_path / "wiki" / f"log-{datetime.now().strftime('%Y-%m')}.md"
    text = shard.read_text(encoding="utf-8")
    # exactly one date heading, two entries, first stays above second
    assert text.count("\n## ") == 1
    assert text.index("first") < text.index("second")


def test_append_log_new_day_appends_section_at_end(tmp_path):
    shard_dir = tmp_path / "wiki"
    shard_dir.mkdir(parents=True)
    shard = shard_dir / f"log-{datetime.now().strftime('%Y-%m')}.md"
    # pre-seed an older day, simulating a file written yesterday
    shard.write_text(
        "# 操作日志 · 2026-01\n\n## 2026-01-01\n* **old_op**: old\n",
        encoding="utf-8",
    )
    append_log(tmp_path, "new_op", "today entry")
    text = shard.read_text(encoding="utf-8")
    # new section appended at END (ascending order), old content untouched
    assert text.index("2026-01-01") < text.index("new_op")
    assert text.startswith("# 操作日志 · 2026-01\n")


def test_wiki_system_files_matches_log_shards():
    assert "log-2026-09.md" in WIKI_SYSTEM_FILES
    assert "log-2099-12.md" in WIKI_SYSTEM_FILES
    assert "log.md" in WIKI_SYSTEM_FILES
    assert "log-2026-09.md" not in {"log.md"}  # plain set semantics unchanged
    assert "logging.md" not in WIKI_SYSTEM_FILES  # prefix must not overmatch


# ---------------------------------------------------------------------------
# D7: ensure_index self-heal
# ---------------------------------------------------------------------------


def test_ensure_index_rebuilds_missing_index(tmp_path):
    wiki = tmp_path / "wiki" / "modules"
    wiki.mkdir(parents=True)
    (wiki / "Auth.md").write_text("---\ntitle: Auth\n---\n# Auth\n", encoding="utf-8")
    assert not (tmp_path / "wiki" / "index.md").exists()
    assert ensure_index(tmp_path) is True
    index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "Auth" in index
    # idempotent: existing index is left alone
    assert ensure_index(tmp_path) is False


def test_ensure_index_noop_without_dir(tmp_path):
    assert ensure_index(tmp_path / "missing") is False


# ---------------------------------------------------------------------------
# §5.2: schema.yaml churn suppression
# ---------------------------------------------------------------------------


def _gen(tmp_path, **overrides):
    components = overrides.pop("components", {"a": {}, "b": {}})
    languages = overrides.pop("languages", ["python"])
    return generate_schema("demo", components, languages, tmp_path, module_names=["a_mod", "b_mod"])


def test_schema_no_write_on_timestamp_only_drift(tmp_path):
    _gen(tmp_path)
    path = tmp_path / "schema.yaml"
    before = path.read_text(encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns
    schema = _gen(tmp_path)  # identical inputs, only generated_at would drift
    assert path.read_text(encoding="utf-8") == before  # byte-identical, not rewritten
    assert path.stat().st_mtime_ns == mtime_before
    # returned dict keeps the OLD generated_at (no phantom timestamp bump)
    assert schema["generated_at"] in before


def test_schema_writes_on_substantive_change(tmp_path):
    _gen(tmp_path)
    before = (tmp_path / "schema.yaml").read_text(encoding="utf-8")
    schema = _gen(tmp_path, components={"a": {}, "b": {}, "c": {}})
    assert schema["project"]["total_components"] == 3
    after = (tmp_path / "schema.yaml").read_text(encoding="utf-8")
    assert after != before
    assert "total_components: 3" in after


# ---------------------------------------------------------------------------
# team_layout core + lint check + init_wiki hygiene (real git repo)
# ---------------------------------------------------------------------------


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    # committed rebuildable files (the pre-migration state)
    for rel in [
        "repowiki/wiki/index.md",
        "repowiki/.meta/metadata.json",
        "repowiki/.meta/module_tree.json",
        "repowiki/.meta/task_bindings/session-1.json",
        "repowiki/tasks/.index.json",
        "repowiki/notes/keep.md",
        "src/main.py",
    ]:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_list_tracked_rebuildables(git_repo):
    tracked = tl.list_tracked_rebuildables(git_repo, git_repo / "repowiki")
    assert "repowiki/wiki/index.md" in tracked
    assert "repowiki/.meta/metadata.json" in tracked
    assert "repowiki/.meta/task_bindings/session-1.json" in tracked
    assert "repowiki/tasks/.index.json" in tracked
    assert "repowiki/notes/keep.md" not in tracked  # content stays tracked
    assert "src/main.py" not in tracked


def test_lint_team_layout_gitignore_reports_tracked(git_repo):
    from codewiki.mcp.tools.wiki_lint import handle_lint_wiki

    res = json.loads(
        handle_lint_wiki(
            {"output_dir": str(git_repo / "repowiki"), "checks": ["team_layout_gitignore"]},
            _StubStore(),
        )
    )
    files = {i["file"] for i in res.get("issues", []) if i["check"] == "team_layout_gitignore"}
    assert "repowiki/wiki/index.md" in files
    assert all(i["severity"] == "warning" for i in res.get("issues", []))


def test_ensure_gitignore_entries_idempotent(git_repo):
    changed, added = tl.ensure_gitignore_entries(git_repo, git_repo / "repowiki")
    assert changed and "repowiki/wiki/index.md" in added
    changed2, added2 = tl.ensure_gitignore_entries(git_repo, git_repo / "repowiki")
    assert not changed2 and not added2
    text = (git_repo / ".gitignore").read_text(encoding="utf-8")
    assert "repowiki/tasks/.index.json" in text


def test_migrate_untracks_but_keeps_files(git_repo):
    tracked = tl.list_tracked_rebuildables(git_repo, git_repo / "repowiki")
    ok, staged = tl.untrack_files(git_repo, tracked)
    assert ok and len(staged) == len(tracked)
    # files still on disk
    assert (git_repo / "repowiki" / "wiki" / "index.md").exists()
    assert (git_repo / "repowiki" / ".meta" / "task_bindings" / "session-1.json").exists()
    # no longer tracked
    remaining = tl.list_tracked_rebuildables(git_repo, git_repo / "repowiki")
    assert remaining == []
    # content file untouched
    assert "repowiki/notes/keep.md" in _git(git_repo, "ls-files")


def test_init_wiki_appends_gitignore_block(git_repo):
    res = json.loads(handle_init_wiki({"repo_path": str(git_repo)}))
    assert res["status"] == "ok"
    gi = res["gitignore"]
    assert isinstance(gi, dict) and gi["status"] in {"updated", "already-present"}
    text = (git_repo / ".gitignore").read_text(encoding="utf-8")
    assert "repowiki/distill-jobs.json" in text


def test_find_repo_root_and_outside_repo(tmp_path):
    assert tl.find_repo_root(tmp_path) is None
    (tmp_path / ".git").mkdir()
    assert tl.find_repo_root(tmp_path / "a" / "b") == tmp_path
