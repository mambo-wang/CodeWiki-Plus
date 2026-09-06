"""Tests for team-layout Phase 4 SECOND slice: session_ff_only + auto_push.

All against throwaway file:// "remotes" (bare repos) — the fake-remote
matrix agreed in the design review (2026-09-02):

* D17 gate: single repo (no workspace.json) NEVER auto-syncs; a workspace
  root (centralized AND colocated) does when enabled.
* session_ff_only: clean tree pulls ff; dirty tree skips with a report;
  divergence refuses to merge.
* auto_push: stages only repowiki/, commits with repo identity
  (``codewiki:`` prefix), pushes; push races resolve via fetch+rebase
  retry; retry exhaustion keeps the local commit (D12).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from codewiki.src import git_sync
from codewiki.src.git_sync import auto_push, session_ff_only


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
        timeout=60,
    )
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"
    return proc.stdout


def _make_remote(tmp_path: Path, name: str) -> Path:
    remote = tmp_path / f"{name}.git"
    remote.mkdir()
    _git(remote, "init", "-q", "--bare", "-b", "main")
    return remote


def _clone(tmp_path: Path, remote: Path, name: str) -> Path:
    clone = tmp_path / name
    _git(tmp_path, "clone", "-q", str(remote), str(clone))
    _git(clone, "config", "user.email", "t@e.com")
    _git(clone, "config", "user.name", "t")
    return clone


def _make_workspace_repo(tmp_path: Path, name: str, layout: str) -> Path:
    """A git repo whose root IS a workspace root (repowiki/.meta/workspace.json)."""
    remote = _make_remote(tmp_path, f"{name}-origin")
    seed = _clone(tmp_path, remote, f"{name}-seed")
    (seed / "repowiki" / ".meta").mkdir(parents=True)
    (seed / "repowiki" / ".meta" / "workspace.json").write_text(
        f'{{"wiki_layout": "{layout}"}}', encoding="utf-8"
    )
    (seed / "repowiki" / "notes").mkdir()
    (seed / "repowiki" / "notes" / "seed.md").write_text("seed\n", encoding="utf-8")
    # schema.yaml is a COMMITTED file in real repos — enable both features
    # (decision C: explicit opt-in) in the SEED so the clone stays clean.
    _enable(seed, mode="session_ff_only", auto_push=True)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "-u", "origin", "main")
    return _clone(tmp_path, remote, name)


def _enable(repo: Path, mode: str = "advisory", auto_push: bool = False) -> None:
    """Write conventions.git_sync into the workspace repowiki's schema.yaml."""
    od = repo / "repowiki"
    od.mkdir(exist_ok=True)
    (od / "schema.yaml").write_text(
        "conventions:\n"
        "  telemetry:\n"
        "    enabled: false\n"
        f"  git_sync:\n    mode: {mode}\n    auto_push: {str(auto_push).lower()}\n",
        encoding="utf-8",
    )


def _reset_state():
    git_sync._checked_repos.clear()
    git_sync._ff_pulled_repos.clear()


# --------------------------------------------------------------------------- #
# D17 gate
# --------------------------------------------------------------------------- #


def test_gate_single_repo_never_auto_syncs(tmp_path):
    """Single repo (no workspace.json): auto_push and session_ff_only are
    no-ops even when enabled in schema.yaml."""
    _reset_state()
    remote = _make_remote(tmp_path, "single-origin")
    repo = _clone(tmp_path, remote, "single")
    (repo / "repowiki" / "notes").mkdir(parents=True)
    (repo / "repowiki" / "notes" / "n.md").write_text("x\n", encoding="utf-8")
    _enable(repo, mode="session_ff_only", auto_push=True)

    assert session_ff_only(repo / "repowiki") is None
    assert auto_push(repo / "repowiki", "test") is None
    # nothing was committed/pushed by the tool
    assert _git(repo, "status", "--porcelain").strip() != ""


def test_gate_colocated_and_centralized_roots_qualify(tmp_path):
    from codewiki.src.git_sync import _is_workspace_root_repo, _find_repo_root

    for layout in ("colocated", "centralized"):
        repo = _make_workspace_repo(tmp_path, f"gate-{layout}", layout)
        od = repo / "repowiki"
        root = _find_repo_root(od)
        assert root == repo.resolve()
        assert _is_workspace_root_repo(od, root) is True
    # and a nested business-style repo does not qualify
    nested = tmp_path / "gate-colocated" / "sub" / "repowiki"
    assert _is_workspace_root_repo(nested, tmp_path / "gate-colocated") is False


# --------------------------------------------------------------------------- #
# session_ff_only
# --------------------------------------------------------------------------- #


def test_session_ff_only_pulls_on_clean_tree(tmp_path):
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "ff-clean", "colocated")
    # remote moves ahead
    seed = tmp_path / "ff-clean-seed"
    (seed / "repowiki" / "notes" / "new.md").write_text("from remote\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "remote work")
    _git(seed, "push", "-q", "origin", "main")

    msg = session_ff_only(repo / "repowiki")
    assert msg and "ff-only" in msg
    assert (repo / "repowiki" / "notes" / "new.md").exists()  # pulled


def test_session_ff_only_reports_on_divergence(tmp_path):
    """D12: a ff-only pull refused by git (diverged remote) must be REPORTED,
    not silently swallowed as a network failure (run_git_bounded regression)."""
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "ff-diverge", "colocated")
    # local moves ahead
    (repo / "repowiki" / "notes" / "local.md").write_text("local\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "local work")
    # remote moves ahead on a different file (via the seed clone)
    seed = tmp_path / "ff-diverge-seed"
    (seed / "repowiki" / "notes" / "remote.md").write_text("remote\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "remote work")
    _git(seed, "push", "-q", "origin", "main")

    msg = session_ff_only(repo / "repowiki")
    assert msg and "ff-only 拉取失败" in msg
    assert "人工同步" in msg
    # the local commit is intact (D12: data intact, arrives later)
    assert (repo / "repowiki" / "notes" / "local.md").exists()


def test_session_ff_only_skips_on_dirty_tree(tmp_path):
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "ff-dirty", "colocated")
    (repo / "repowiki" / "notes" / "uncommitted.md").write_text("dirty\n", encoding="utf-8")

    msg = session_ff_only(repo / "repowiki")
    assert msg and "不干净" in msg
    # once-per-process: the failed attempt claims the slot
    assert session_ff_only(repo / "repowiki") is None


def test_session_ff_only_once_per_process(tmp_path):
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "ff-once", "centralized")
    assert session_ff_only(repo / "repowiki") is not None
    assert session_ff_only(repo / "repowiki") is None


def test_session_ff_only_mode_gate(tmp_path):
    """mode=advisory (the default) never pulls."""
    _reset_state()
    # workspace factory seeds session_ff_only; write an advisory variant by
    # hand into the CLONED schema (mode check happens before any pull, and
    # ff_only never mutates the tree — safe even though schema.yaml is dirty)
    repo = _make_workspace_repo(tmp_path, "ff-mode", "colocated")
    _enable(repo, mode="advisory", auto_push=False)
    assert session_ff_only(repo / "repowiki") is None


# --------------------------------------------------------------------------- #
# auto_push
# --------------------------------------------------------------------------- #


def test_auto_push_commits_and_pushes_knowledge_only(tmp_path):
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-ok", "colocated")
    # knowledge change + a stray business file that must NOT be committed
    (repo / "repowiki" / "notes" / "new.md").write_text("new knowledge\n", encoding="utf-8")
    (repo / "business.py").write_text("print('x')\n", encoding="utf-8")

    msg = auto_push(repo / "repowiki", "close_session")
    assert msg and "已推送" in msg
    log = _git(repo, "log", "-1", "--pretty=%B")
    assert log.startswith("codewiki: auto-sync knowledge (close_session")
    # business file stays untracked, never committed
    assert _git(repo, "status", "--porcelain").strip().startswith("??")
    # remote received the note
    seed = tmp_path / "push-ok-seed"
    _git(seed, "pull", "-q")
    assert (seed / "repowiki" / "notes" / "new.md").exists()


def test_auto_push_silent_when_nothing_staged(tmp_path):
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-empty", "centralized")
    assert auto_push(repo / "repowiki", "capture_conversation") is None
    assert _git(repo, "log", "--oneline").strip().count("\n") == 0  # only seed commit


def test_auto_push_race_resolved_by_rebase(tmp_path):
    """Remote moves ahead AFTER our fetch → push race → fetch+rebase retry
    must land our commit on top of the remote's."""
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-race", "colocated")
    seed = tmp_path / "push-race-seed"

    # our knowledge change (not yet pushed)
    (repo / "repowiki" / "notes" / "ours.md").write_text("our knowledge\n", encoding="utf-8")

    # simulate the race: remote receives a commit before our push reaches it.
    # We do that by pre-pushing from seed and then monkeypatching the first
    # push attempt to behave as if the race happened — here simply: remote
    # advances BEFORE auto_push is called but after our clone is up to date,
    # so the direct push fails with non-FF and the rebase path must fix it.
    (seed / "repowiki" / "notes" / "theirs.md").write_text("their knowledge\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "their work")
    _git(seed, "push", "-q", "origin", "main")

    msg = auto_push(repo / "repowiki", "distill_submit")
    assert msg and "已推送" in msg, msg
    # both notes live on the remote now (rebase put ours on top of theirs)
    _git(seed, "pull", "-q")
    assert (seed / "repowiki" / "notes" / "theirs.md").exists()
    assert (seed / "repowiki" / "notes" / "ours.md").exists()
    # clean tree afterwards (no conflict leftovers)
    assert _git(repo, "status", "--porcelain").strip() == ""


def test_auto_push_divergence_keeps_local_commit(tmp_path):
    """True divergence (remote rewrites history) exhausts retries — the
    LOCAL CHANGE plus auto_push's own commit are KEPT (D12: data intact,
    arrives later).  The local change stays UNCOMMITTED before the call:
    auto_push's job is "commit new changes and push", and the push must
    race against a rewritten remote."""
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-diverge", "colocated")
    seed = tmp_path / "push-diverge-seed"

    # local knowledge change, UNCOMMITTED (auto_push will commit it)
    (repo / "repowiki" / "notes" / "local.md").write_text("local\n", encoding="utf-8")

    # remote DIVERGES: rewritten history makes every rebase attempt conflict
    # (the seed's note file differs from the clone's ancestor)
    (seed / "repowiki" / "notes" / "seed.md").write_text("rewritten seed\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "--amend", "-m", "rewritten remote history")
    _git(seed, "push", "-q", "-f", "origin", "main")

    msg = auto_push(repo / "repowiki", "close_session")
    assert msg and "保留" in msg, msg  # degradation report
    # local change + auto_push's commit survived — never reset (D12)
    assert (repo / "repowiki" / "notes" / "local.md").exists()
    log = _git(repo, "log", "--oneline")
    assert "codewiki: auto-sync knowledge" in log  # auto_push's own commit kept
    # and the tree carries no conflict leftovers from the aborted rebases
    assert _git(repo, "status", "--porcelain").strip() == ""


def test_auto_push_aborts_on_preexisting_staged_content(tmp_path):
    """Real-repo acceptance finding (2026-09-02): git commit commits the
    WHOLE index — user-staged changes must never be swept into the
    auto_push commit.  auto_push ABORTS with a report; the user's staged
    content is left untouched."""
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-guard", "colocated")
    # user stages their own change (NOT under repowiki/)
    (repo / "business.py").write_text("print('user work')\n", encoding="utf-8")
    _git(repo, "add", "business.py")
    # knowledge change exists too — the guard must still abort
    (repo / "repowiki" / "notes" / "new.md").write_text("knowledge\n", encoding="utf-8")

    msg = auto_push(repo / "repowiki", "close_session")
    assert msg and "跳过自动推送" in msg
    # user's staged content untouched, knowledge change unstaged (not lost)
    staged = _git(repo, "diff", "--cached", "--name-only")
    assert staged.strip() == "business.py"
    assert (repo / "repowiki" / "notes" / "new.md").exists()


def test_auto_push_never_commits_lock_files(tmp_path):
    """Real-repo finding: a repo whose .gitignore predates the team layout
    (no *.lck entry) had sidecar locks swept into the commit.  auto_push
    must unstage them before committing."""
    _reset_state()
    repo = _make_workspace_repo(tmp_path, "push-lck", "colocated")
    # knowledge change + a stray .lck next to it (unignored by this repo)
    (repo / "repowiki" / "notes" / "n.md").write_text("x\n", encoding="utf-8")
    (repo / "repowiki" / "notes" / "n.md.lck").write_text("", encoding="utf-8")

    msg = auto_push(repo / "repowiki", "close_session")
    assert msg and "已推送" in msg
    # the commit carries the note but not the lock
    files = _git(repo, "show", "--name-only", "--pretty=format:", "HEAD")
    assert "repowiki/notes/n.md".replace("/", "\\") in files or "repowiki/notes/n.md" in files
    assert ".lck" not in files
    # lock file still on disk
    assert (repo / "repowiki" / "notes" / "n.md.lck").exists()
