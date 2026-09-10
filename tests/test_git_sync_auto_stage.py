"""auto_stage — stage-only companion to auto_push (git_sync, 2026-09-09).

Covers the contract of :func:`codewiki.src.git_sync.auto_stage` against real
git repositories: durable knowledge is staged, ignored / transient files are
not, deletions keep the index ghost-free, and the config gates
(``auto_stage: false`` / ``auto_push: true``) suppress staging.

``_force=True`` is passed throughout because auto_stage is a silent no-op
under pytest by design (keeps the suite's tmp wikis out of the developer's
index); the guard itself is pinned by ``test_pytest_guard``.
"""

import subprocess
from pathlib import Path

import pytest

from codewiki.src import git_sync
from codewiki.src.git_sync import auto_stage


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def _staged(repo: Path) -> list:
    out = _git(repo, "diff", "--cached", "--name-only").stdout
    return [line for line in out.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _clear_decision_caches():
    git_sync._wiki_root_cache.clear()
    git_sync._stage_decisions.clear()
    yield
    git_sync._wiki_root_cache.clear()
    git_sync._stage_decisions.clear()


@pytest.fixture
def wiki_repo(tmp_path: Path) -> Path:
    """A git repo containing a repowiki/ (with .meta/, so the wiki root is
    discoverable) and git identity configured for direct git assertions."""
    repo = tmp_path / "repo"
    wiki = repo / "repowiki"
    (wiki / ".meta").mkdir(parents=True)
    (wiki / "notes").mkdir()
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    return repo


def _write_schema(wiki: Path, git_sync_block: str) -> None:
    (wiki / "schema.yaml").write_text(
        f"conventions:\n  git_sync:\n{git_sync_block}", encoding="utf-8"
    )


def test_stages_written_file(wiki_repo: Path):
    note = wiki_repo / "repowiki" / "notes" / "pitfall-foo.md"
    note.write_text("body", encoding="utf-8")

    auto_stage(note, _force=True)

    assert _staged(wiki_repo) == ["repowiki/notes/pitfall-foo.md"]


def test_stages_modification_of_tracked_file(wiki_repo: Path):
    note = wiki_repo / "repowiki" / "notes" / "pitfall-foo.md"
    note.write_text("v1", encoding="utf-8")
    _git(wiki_repo, "add", "--", "repowiki/notes/pitfall-foo.md")
    _git(wiki_repo, "commit", "-q", "-m", "init")
    note.write_text("v2", encoding="utf-8")

    auto_stage(note, _force=True)

    assert _staged(wiki_repo) == ["repowiki/notes/pitfall-foo.md"]


def test_ignored_file_not_staged(wiki_repo: Path):
    (wiki_repo / ".gitignore").write_text("repowiki/raw/\n", encoding="utf-8")
    raw = wiki_repo / "repowiki" / "raw" / "conv-1.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("captured", encoding="utf-8")

    auto_stage(raw, _force=True)

    assert _staged(wiki_repo) == []


def test_lock_and_tmp_residue_never_staged(wiki_repo: Path):
    # no .gitignore entry at all — the hard-skip must hold regardless
    for name in ("sidecar.lck", "page.md.tmp.123.45"):
        p = wiki_repo / "repowiki" / "notes" / name
        p.write_text("x", encoding="utf-8")
        auto_stage(p, _force=True)

    assert _staged(wiki_repo) == []


def test_no_wiki_root_noop(tmp_path: Path):
    """Files outside a repowiki (no .meta ancestor) are not codewiki
    knowledge — staging must not fire even inside a git repo."""
    repo = tmp_path / "bare"
    repo.mkdir()
    _git(tmp_path, "init", "-q", str(repo))
    stray = repo / "notes.md"
    stray.write_text("x", encoding="utf-8")

    auto_stage(stray, _force=True)

    assert _staged(repo) == []


def test_no_git_repo_noop(tmp_path: Path):
    wiki = tmp_path / "repowiki"
    (wiki / ".meta").mkdir(parents=True)
    note = wiki / "notes" / "n.md"
    note.parent.mkdir()
    note.write_text("x", encoding="utf-8")

    auto_stage(note, _force=True)  # must not raise, must not stage

    assert not (tmp_path / ".git").exists()


def test_config_auto_stage_false(wiki_repo: Path):
    _write_schema(wiki_repo / "repowiki", "    auto_stage: false\n")
    note = wiki_repo / "repowiki" / "notes" / "n.md"
    note.write_text("x", encoding="utf-8")

    auto_stage(note, _force=True)

    assert _staged(wiki_repo) == []


def test_auto_push_supersedes_staging(wiki_repo: Path):
    # auto_push stages+commits+pushes on its own anchors; auto_stage must
    # stand down or auto_push's pre-staged-content guard would false-positive.
    _write_schema(wiki_repo / "repowiki", "    auto_push: true\n")
    note = wiki_repo / "repowiki" / "notes" / "n.md"
    note.write_text("x", encoding="utf-8")

    auto_stage(note, _force=True)

    assert _staged(wiki_repo) == []


def test_removal_stages_deletion(wiki_repo: Path):
    note = wiki_repo / "repowiki" / "notes" / "n.md"
    note.write_text("x", encoding="utf-8")
    auto_stage(note, _force=True)
    assert _staged(wiki_repo) == ["repowiki/notes/n.md"]

    note.unlink()
    auto_stage(note, removed=True, _force=True)

    assert _staged(wiki_repo) == []  # no ghost "added then deleted" pair


def test_removal_of_never_staged_file_is_silent(wiki_repo: Path):
    note = wiki_repo / "repowiki" / "notes" / "never.md"
    note.write_text("x", encoding="utf-8")
    note.unlink()

    auto_stage(note, removed=True, _force=True)  # must not raise

    assert _staged(wiki_repo) == []


def test_pytest_guard(wiki_repo: Path):
    """Without _force the call is a no-op under pytest — the production hook
    in store.atomic_write relies on this to keep test wikis out of the
    developer's index."""
    note = wiki_repo / "repowiki" / "notes" / "n.md"
    note.write_text("x", encoding="utf-8")

    auto_stage(note)  # no _force

    assert _staged(wiki_repo) == []
