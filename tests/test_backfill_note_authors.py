"""Tests for the backfill-note-authors CLI (Phase 3, D16 follow-up).

Covers git-provenance resolution, idempotency (already-stamped notes are
skipped), the --author override, and the --default fallback for notes
without git provenance.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


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


def _note(path: Path, title: str, author_stamped: bool = False) -> None:
    fm = f"title: {title}\ntype: lesson\nstatus: stable\n"
    if author_stamped:
        fm += "author: someone\n"
    fm += "generated:\n  by: codewiki/5.5.1\n  at: '2026-09-02T00:00:00Z'\n"
    path.write_text(f"---\n{fm}---\n\nbody\n", encoding="utf-8")


def _read_author(note: Path) -> str | None:
    text = note.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    fm = yaml.safe_load(text[3:end])
    return fm.get("author")


def _run_cli(repo: Path, *args: str):
    import os
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "codewiki.cli.main", "backfill-note-authors", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


def _mk_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "alice")
    _git(repo, "config", "user.email", "a@e.com")
    notes = repo / "repowiki" / "notes"
    notes.mkdir(parents=True)
    _note(notes / "a.md", "A")  # committed by alice
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a")
    # second author commits another note
    _git(repo, "config", "user.name", "bob")
    _git(repo, "config", "user.email", "b@e.com")
    _note(notes / "b.md", "B")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "b")
    # uncommitted local note (no git provenance)
    _note(notes / "c.md", "C")
    # already stamped
    _note(notes / "d.md", "D", author_stamped=True)
    return repo


def test_backfill_git_provenance_and_skip(tmp_path):
    repo = _mk_repo(tmp_path)
    proc = _run_cli(repo)
    assert proc.returncode == 0, proc.stderr
    notes = repo / "repowiki" / "notes"
    assert _read_author(notes / "a.md") == "alice"
    assert _read_author(notes / "b.md") == "bob"
    # c has no provenance and no --default → untouched, reported
    assert _read_author(notes / "c.md") is None
    assert "skipped:             1" in proc.stdout
    # d already stamped → untouched
    assert _read_author(notes / "d.md") == "someone"
    assert "already have author: 1" in proc.stdout


def test_backfill_default_fallback(tmp_path):
    repo = _mk_repo(tmp_path)
    proc = _run_cli(repo, "--default", "local-user")
    assert proc.returncode == 0, proc.stderr
    assert _read_author(repo / "repowiki" / "notes" / "c.md") == "local-user"


def test_backfill_author_override(tmp_path):
    repo = _mk_repo(tmp_path)
    proc = _run_cli(repo, "--author", "bulk-owner")
    assert proc.returncode == 0, proc.stderr
    notes = repo / "repowiki" / "notes"
    # override stamps everything not already stamped (c included)
    assert _read_author(notes / "a.md") == "bulk-owner"
    assert _read_author(notes / "c.md") == "bulk-owner"
    # already-stamped d is never touched
    assert _read_author(notes / "d.md") == "someone"


def test_backfill_idempotent(tmp_path):
    repo = _mk_repo(tmp_path)
    assert _run_cli(repo).returncode == 0
    proc = _run_cli(repo)  # second run: everything already stamped
    assert "to stamp:            0" in proc.stdout


def test_backfill_dry_run_touches_nothing(tmp_path):
    repo = _mk_repo(tmp_path)
    proc = _run_cli(repo, "--dry-run")
    assert proc.returncode == 0
    assert "dry-run" in proc.stdout
    assert _read_author(repo / "repowiki" / "notes" / "a.md") is None
