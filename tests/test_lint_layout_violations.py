"""Tests for ticket 09: lint_wiki layout-discipline checks.

Centralized-only: business repos must not grow a repowiki/ (knowledge leak),
and shared-pool pages are expected to carry repo:/repos: provenance (untagged
= a "confirm it's global" advisory). The checks are fully inert outside
centralized corpora.
"""

from __future__ import annotations

import json

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki

URL_A = "https://example.com/a.git"


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _init_centralized(tmp_path):
    json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": "centralized"}))
    (tmp_path / "a").mkdir(exist_ok=True)
    json.loads(
        wb.handle_add_workspace_repo(
            {"workspace_path": str(tmp_path), "url": URL_A, "clone": False}
        )
    )
    return tmp_path


def _lint(ws):
    res = json.loads(
        handle_lint_wiki(
            {"output_dir": str(ws / "repowiki"), "checks": ["layout_violations"]},
            _StubStore(),
        )
    )
    return [i for i in res.get("issues", []) if i.get("check") == "layout_violations"]


def _write_entity(ws, name, provenance_line):
    d = ws / "repowiki" / "wiki" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: Entity\ntitle: " + json.dumps(name) + "\n"
    if provenance_line:
        fm += provenance_line + "\n"
    fm += "---\n\nbody\n"
    (d / f"{name}.md").write_text(fm, encoding="utf-8")


class TestLayoutViolations:
    def test_compliant_workspace_zero_issues(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_entity(ws, "Tagged", 'repo: "a"')
        (ws / "repowiki" / "wiki" / "modules" / "a").mkdir(parents=True, exist_ok=True)
        (ws / "repowiki" / "wiki" / "modules" / "a" / "mod.md").write_text(
            "# mod\n\nno provenance needed — location is provenance\n", encoding="utf-8"
        )
        assert _lint(ws) == []

    def test_knowledge_leak_warns(self, tmp_path):
        ws = _init_centralized(tmp_path)
        (ws / "a" / "repowiki").mkdir(parents=True, exist_ok=True)
        issues = _lint(ws)
        leaks = [i for i in issues if i["severity"] == "warning"]
        assert len(leaks) == 1
        assert "repowiki" in leaks[0]["message"]
        assert "a" in leaks[0]["message"]

    def test_missing_provenance_info_advisory(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_entity(ws, "Global", None)  # untagged → global advisory
        issues = _lint(ws)
        infos = [i for i in issues if i["severity"] == "info"]
        assert len(infos) == 1
        assert "provenance" in infos[0]["message"]
        assert infos[0]["file"].endswith("Global.md")

    def test_tagged_and_multirepo_pages_pass(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_entity(ws, "Single", 'repo: "a"')
        _write_entity(ws, "Multi", 'repos: ["a", "b"]')
        assert _lint(ws) == []

    def test_inert_outside_centralized_corpus(self, tmp_path):
        # colocated repo: even with an in-repo repowiki, no layout issues fire
        repo = tmp_path / "solo"
        (repo / "repowiki" / "wiki" / "entities").mkdir(parents=True)
        (repo / "repowiki" / "wiki" / "entities" / "X.md").write_text(
            '---\ntype: Entity\ntitle: "X"\n---\n\nbody\n', encoding="utf-8"
        )
        res = json.loads(
            handle_lint_wiki(
                {"output_dir": str(repo / "repowiki"), "checks": ["layout_violations"]},
                _StubStore(),
            )
        )
        assert [i for i in res.get("issues", []) if i.get("check") == "layout_violations"] == []
