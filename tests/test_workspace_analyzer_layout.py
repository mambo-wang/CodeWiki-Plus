"""Tests for ticket 08: analyze_workspace under centralized layout.

Topology/overview must always run and read from layout-correct locations
(no hardcoded <repo>/repowiki); the heavy per-repo analysis is gated by
generate_repo_wikis (default false) under centralized, and colocated
behaviour is unchanged with the flag ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl

URL_A = "https://example.com/repo-a.git"
URL_B = "https://example.com/repo-b.git"

PY_MAIN = '''"""service entry"""\ndef handler():\n    return "ok"\n'''


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _mk_git_repo(path, name):
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.py").write_text(PY_MAIN, encoding="utf-8")
    repo = git.Repo.init(str(path))
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    repo.index.add([f"{name}.py"])
    repo.index.commit("init")


def _setup(tmp_path, layout):
    args = {"workspace_path": str(tmp_path)}
    if layout:
        args["layout"] = layout
    json.loads(wb.handle_init_workspace(args))
    for url in (URL_A, URL_B):
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": url, "clone": False}
            )
        )
        _mk_git_repo(tmp_path / name, name.replace("-", "_"))
    return tmp_path


def _analyze(ws, **extra):
    from codewiki.mcp.tools.workspace_analyzer import handle_analyze_workspace

    return json.loads(
        handle_analyze_workspace({"workspace_path": str(ws), **extra}, SessionStore())
    )


class TestAnalyzeWorkspaceCentralized:
    def test_topology_only_default(self, tmp_path):
        ws = _setup(tmp_path, "centralized")
        res = _analyze(ws)
        assert res["layout"] == "centralized"
        assert res["repos_analyzed"] == 2
        # Heavy per-repo analysis skipped by default
        for entry in res["repos"]:
            assert entry["analyzed"] is False
            assert entry["session_id"] is None
        # Overview still produced at the workspace knowledge base
        assert res["overview_path"].endswith("overview.md")
        assert Path(res["overview_path"]).is_file()
        assert Path(res["overview_path"]).parent == ws / "repowiki"
        # Business repos stay pure code
        assert not (ws / "repo-a" / "repowiki").exists()

    def test_generate_repo_wikis_populates_analysis(self, tmp_path):
        ws = _setup(tmp_path, "centralized")
        res = _analyze(ws, generate_repo_wikis=True)
        assert res["generate_repo_wikis"] is True
        for entry in res["repos"]:
            assert entry["analyzed"] is True
            assert entry["session_id"]
            assert entry["output_dir"] == str(ws / "repowiki")
        # Analysis state written into the workspace knowledge base
        assert (ws / "repowiki" / ".meta" / "project.json").is_file()
        # Per-repo analysis caches stay in the repos (layout-independent)
        assert (ws / "repo-a" / ".codewiki" / "analysis_cache.db").exists()

    def test_topology_rerun_after_generation(self, tmp_path):
        ws = _setup(tmp_path, "centralized")
        _analyze(ws, generate_repo_wikis=True)
        # Topology-only rerun reads existing caches; no heavy analysis
        res = _analyze(ws)
        assert res["repos_analyzed"] == 2
        assert all(e["analyzed"] is False for e in res["repos"])
        assert res["errors"] is None
        assert "cross_service" in res


class TestAnalyzeWorkspaceColocated:
    def test_colocated_ignores_flag_and_keeps_status_quo(self, tmp_path):
        ws = _setup(tmp_path, None)  # colocated default
        res = _analyze(ws, generate_repo_wikis=False)  # flag ignored
        assert res["layout"] == "colocated"
        assert res["generate_repo_wikis"] is None
        for entry in res["repos"]:
            assert entry["analyzed"] is True  # always analyzes
            assert entry["output_dir"].endswith("repowiki")
        # Per-repo repowikis created as before
        assert (ws / "repo-a" / "repowiki").is_dir()
        assert (ws / "repo-b" / "repowiki").is_dir()
