"""Tests for team-layout Phase 3 + Phase 4 first slice.

* D16 — author provenance: every ingested note carries ``author`` (write-only,
  no gating); OKF conformance tolerates the field.
* D15 — code fingerprint soft advisory: overwriting a page whose recorded
  fingerprint drifted surfaces an advisory in the result (never blocks); the
  new page is stamped with the current fingerprint.
* D14 — sync_check: read-only advisory, once per process per repo, silent
  degradation, respects mode=off.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from codewiki.mcp.tools.knowledge_loop import handle_ingest_note
from codewiki.mcp.tools.page_manifest import (
    compute_code_fingerprint,
    read_page_code_fingerprint,
)
from codewiki.mcp.tools.wiki_lint import _OKF_TOP_LEVEL_KEYS
from codewiki.src import git_sync
from codewiki.src.git_sync import sync_check


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


# --------------------------------------------------------------------------- #
# D16: author provenance
# --------------------------------------------------------------------------- #


def test_ingest_note_stamps_author(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    git_sync._checked_repos.clear()  # isolate sync_check once-per-process state
    res = json.loads(
        handle_ingest_note(
            {"output_dir": str(tmp_path), "title": "作者标注", "content": "正文"},
            _StubStore(),
        )
    )
    assert res["status"] == "ingested"
    note = Path(res["note_path"])
    text = note.read_text(encoding="utf-8")
    assert "author: alice" in text


def test_author_in_okf_top_level_keys():
    assert "author" in _OKF_TOP_LEVEL_KEYS


def test_author_field_okf_conformance_clean(tmp_path):
    """okf_conformance must not warn about the author field."""
    from codewiki.mcp.tools.wiki_lint import handle_lint_wiki

    (tmp_path / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "n.md").write_text(
        "---\ntype: lesson\ntitle: t\nstatus: stable\nauthor: bob\n"
        "generated:\n  by: codewiki/5.5.1\n  at: '2026-09-02T00:00:00Z'\n---\n\nbody\n",
        encoding="utf-8",
    )
    res = json.loads(
        handle_lint_wiki({"output_dir": str(tmp_path), "checks": ["okf_conformance"]}, _StubStore())
    )
    author_issues = [
        i
        for i in res.get("issues", [])
        if "author" in str(i.get("message", "")) or i.get("file", "").endswith("n.md")
    ]
    assert author_issues == []


# --------------------------------------------------------------------------- #
# D15: code fingerprint soft advisory
# --------------------------------------------------------------------------- #


def test_compute_code_fingerprint_requires_analysis(tmp_path):
    assert compute_code_fingerprint(tmp_path) is None
    (tmp_path / ".meta").mkdir()
    (tmp_path / ".meta" / "module_tree.json").write_text("{}", encoding="utf-8")
    assert compute_code_fingerprint(tmp_path) is None  # symbol_map still missing
    (tmp_path / ".meta" / "symbol_map.json").write_text("{}", encoding="utf-8")
    fp = compute_code_fingerprint(tmp_path)
    assert fp and fp.startswith("sha256:")
    # content change → fingerprint change
    (tmp_path / ".meta" / "symbol_map.json").write_text('{"x": 1}', encoding="utf-8")
    assert compute_code_fingerprint(tmp_path) != fp


def test_stamp_and_read_page_code_fingerprint_roundtrip(tmp_path):
    from codewiki.mcp.tools.doc_writer import _locked_transform, _stamp_metadata_field

    page = tmp_path / "page.md"
    page.write_text("---\ntitle: t\ntype: module\n---\n\nbody\n", encoding="utf-8")
    _locked_transform(page, lambda t: _stamp_metadata_field(t, "code_fingerprint", "sha256:aaa"))
    assert read_page_code_fingerprint(page) == "sha256:aaa"
    # re-stamp replaces, not duplicates
    _locked_transform(page, lambda t: _stamp_metadata_field(t, "code_fingerprint", "sha256:bbb"))
    text = page.read_text(encoding="utf-8")
    assert text.count("code_fingerprint:") == 1
    assert read_page_code_fingerprint(page) == "sha256:bbb"
    # existing metadata block is preserved
    assert "title: t" in text


def _init_centralized(tmp_path):
    """Minimal centralized workspace with one registered (non-cloned) repo."""
    from codewiki.mcp.tools import workspace_bootstrap as wb

    json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": "centralized"}))
    (tmp_path / "svc").mkdir(exist_ok=True)
    json.loads(
        wb.handle_add_workspace_repo(
            {"workspace_path": str(tmp_path), "url": "https://example.com/svc.git", "clone": False}
        )
    )
    return tmp_path


def test_write_doc_file_fingerprint_advisory_on_drift(tmp_path, monkeypatch):
    """Overwriting a SHARED-POOL page (the D9 last-write-wins path) after
    code drift surfaces an advisory, not a block."""
    import asyncio

    from codewiki.mcp.tools.doc_writer import handle_write_doc_file

    git_sync._checked_repos.clear()
    ws = _init_centralized(tmp_path)
    output_dir = ws / "repowiki"
    repo_path = ws / "svc"
    # seed analysis artifacts (fingerprint inputs)
    meta = output_dir / ".meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "module_tree.json").write_text("{}", encoding="utf-8")
    (meta / "symbol_map.json").write_text("{}", encoding="utf-8")

    args = {
        "output_dir": str(output_dir),
        "repo_path": str(repo_path),
        "filename": "Task.md",
        "page_type": "entity",  # non-module → shared-pool write → overwrite allowed
        "content": "---\ntitle: Task\ntype: entity\n---\n\n# Task\n\nv1 content\n",
    }
    r1 = json.loads(asyncio.run(handle_write_doc_file(args, _StubStore())))
    assert r1["status"] == "created", r1
    assert not [a for a in r1.get("advisories", []) if "code_fingerprint" in a]
    page = output_dir / "wiki" / "entities" / "Task.md"
    assert page.exists()
    assert read_page_code_fingerprint(page)  # stamped

    # code drifts
    (meta / "symbol_map.json").write_text('{"AuthService": "a.py"}', encoding="utf-8")
    args["content"] = "---\ntitle: Task\ntype: entity\n---\n\n# Task\n\nv2 content\n"
    r2 = json.loads(asyncio.run(handle_write_doc_file(args, _StubStore())))
    assert r2["status"] == "created"  # never blocked (D15 soft advisory)
    assert any("code_fingerprint" in a for a in r2.get("advisories", []))


def test_write_doc_file_no_advisory_without_drift(tmp_path, monkeypatch):
    import asyncio

    from codewiki.mcp.tools.doc_writer import handle_write_doc_file

    git_sync._checked_repos.clear()
    ws = _init_centralized(tmp_path)
    output_dir = ws / "repowiki"
    meta = output_dir / ".meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "module_tree.json").write_text("{}", encoding="utf-8")
    (meta / "symbol_map.json").write_text("{}", encoding="utf-8")
    args = {
        "output_dir": str(output_dir),
        "repo_path": str(ws / "svc"),
        "filename": "Queue.md",
        "page_type": "entity",
        "content": "---\ntitle: Queue\ntype: entity\n---\n\n# Queue\n\nv1\n",
    }
    json.loads(asyncio.run(handle_write_doc_file(args, _StubStore())))
    args["content"] = "---\ntitle: Queue\ntype: entity\n---\n\n# Queue\n\nv2\n"
    r2 = json.loads(asyncio.run(handle_write_doc_file(args, _StubStore())))
    assert not [a for a in r2.get("advisories", []) if "code_fingerprint" in a]


# --------------------------------------------------------------------------- #
# D14: sync_check advisory
# --------------------------------------------------------------------------- #


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


def _git_default_branch(repo: Path) -> str:
    """The branch name a fresh ``git init`` produced (master or main)."""
    out = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return out.stdout.strip() or "master"


def test_sync_check_behind_remote(tmp_path):
    """origin ahead of clone → advisory mentions the count; once per process."""
    git_sync._checked_repos.clear()
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    branch = _git_default_branch(seed)  # machine-dependent: master or main
    _git(seed, "config", "user.email", "t@e.com")
    _git(seed, "config", "user.name", "t")
    (seed / "repowiki").mkdir()
    (seed / "repowiki" / "notes").mkdir(parents=True)
    (seed / "repowiki" / "notes" / "a.md").write_text("x\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "init")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "-u", "origin", branch)

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    # remote moves ahead by 2
    _git(seed, "commit", "-q", "--allow-empty", "-m", "r1")
    _git(seed, "commit", "-q", "--allow-empty", "-m", "r2")
    _git(seed, "push", "-q", "origin", branch)

    advisory = sync_check(clone / "repowiki")
    assert advisory and "2" in advisory and "远端" in advisory
    # once-per-process: second call returns None (already claimed the slot)
    assert sync_check(clone / "repowiki") is None


def test_sync_check_up_to_date_silent(tmp_path):
    git_sync._checked_repos.clear()
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    branch = _git_default_branch(seed)  # machine-dependent: master or main
    _git(seed, "config", "user.email", "t@e.com")
    _git(seed, "config", "user.name", "t")
    (seed / "repowiki").mkdir()
    (seed / "repowiki" / "a.md").write_text("x\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "init")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "-u", "origin", branch)
    clone = tmp_path / "clone2"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    assert sync_check(clone / "repowiki") is None


def test_sync_check_mode_off(tmp_path, monkeypatch):
    """conventions.git_sync.mode=off silences the advisory."""
    git_sync._checked_repos.clear()
    od = tmp_path / "repowiki"
    od.mkdir()
    (od / "schema.yaml").write_text("conventions:\n  git_sync:\n    mode: off\n", encoding="utf-8")
    assert sync_check(od) is None


def test_sync_check_no_git_repo_silent(tmp_path):
    git_sync._checked_repos.clear()
    od = tmp_path / "plain"
    od.mkdir()
    assert sync_check(od) is None  # never raises
