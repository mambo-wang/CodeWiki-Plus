"""Tests for ticket 05: query_wiki one-hop retrieval + repo= scope filter.

The repo= filter must return exactly "knowledge applicable to that repo":
the repo's modules partition + shared-pool pages tagged with it + untagged
global pages — and nothing from other repos. Verified on whichever search
path is active (BM25 or legacy keyword fallback).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl

URL_A = "https://example.com/a.git"
URL_B = "https://example.com/b.git"


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


def _setup_workspace(tmp_path):
    json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": "centralized"}))
    for url in (URL_A, URL_B):
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        (tmp_path / name).mkdir(exist_ok=True)
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": url, "clone": False}
            )
        )
    wiki = tmp_path / "repowiki" / "wiki"
    notes = tmp_path / "repowiki" / "notes"
    # a's module partition
    (wiki / "modules" / "a").mkdir(parents=True, exist_ok=True)
    (wiki / "modules" / "a" / "autha.md").write_text(
        "# AuthA zebra\n\nmodule doc for repo a about zebra handling\n", encoding="utf-8"
    )
    # b's module partition
    (wiki / "modules" / "b").mkdir(parents=True, exist_ok=True)
    (wiki / "modules" / "b" / "authb.md").write_text(
        "# AuthB zebra\n\nmodule doc for repo b about zebra handling\n", encoding="utf-8"
    )
    # shared entity tagged with both repos
    (wiki / "entities").mkdir(parents=True, exist_ok=True)
    (wiki / "entities" / "SharedZebra.md").write_text(
        '---\ntype: Entity\ntitle: "SharedZebra"\nrepos: ["a", "b"]\n---\n\nshared zebra entity\n',
        encoding="utf-8",
    )
    # shared entity tagged only with b
    (wiki / "entities" / "OnlyBZebra.md").write_text(
        '---\ntype: Entity\ntitle: "OnlyBZebra"\nrepo: "b"\n---\n\nonly-b zebra entity\n',
        encoding="utf-8",
    )
    # untagged global convention page
    (wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki / "concepts" / "GlobalZebraConvention.md").write_text(
        '---\ntype: Concept\ntitle: "GlobalZebraConvention"\n---\n\nproduct-line zebra convention\n',
        encoding="utf-8",
    )
    # note stamped with repo a (metadata fold, as ingest_note writes it)
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "2026-01-01-zebra-note.md").write_text(
        '---\ntype: pitfall\ntitle: "zebra note"\nstatus: stable\nmetadata:\n  repo: "a"\n---\n\nzebra pitfall note\n',
        encoding="utf-8",
    )
    return tmp_path


def _query(tmp_path, query="zebra", repo=None, output_dir=None, repo_path=None):
    from codewiki.mcp.tools.knowledge_loop import handle_query_wiki

    args = {"query": query}
    if repo:
        args["repo"] = repo
    if output_dir:
        args["output_dir"] = str(output_dir)
    if repo_path:
        args["repo_path"] = str(repo_path)
    return json.loads(handle_query_wiki(args, _StubStore()))


def _titles(res):
    return {r.get("title", "") for r in res.get("results", [])}


def _files(res):
    return {Path(r.get("file", "")).as_posix() for r in res.get("results", [])}


class TestQueryRepoFilter:
    def test_one_hop_default_covers_all_repos(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        res = _query(ws, output_dir=ws / "repowiki")
        files = _files(res)
        assert "wiki/modules/a/autha.md" in files
        assert "wiki/modules/b/authb.md" in files
        assert "wiki/concepts/GlobalZebraConvention.md" in files

    def test_repo_filter_returns_applicable_knowledge_only(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        res = _query(ws, repo="a", output_dir=ws / "repowiki")
        assert res.get("repo_filter") == "a"
        files = _files(res)
        # a's partition + shared page tagged a + global page + a-tagged note
        assert "wiki/modules/a/autha.md" in files
        assert "wiki/entities/SharedZebra.md" in files
        assert "wiki/concepts/GlobalZebraConvention.md" in files
        assert "notes/2026-01-01-zebra-note.md" in files
        # b's partition and b-only pages excluded
        assert "wiki/modules/b/authb.md" not in files
        assert "wiki/entities/OnlyBZebra.md" not in files

    def test_repo_filter_other_repo(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        res = _query(ws, repo="b", output_dir=ws / "repowiki")
        files = _files(res)
        assert "wiki/modules/b/authb.md" in files
        assert "wiki/entities/OnlyBZebra.md" in files
        assert "wiki/entities/SharedZebra.md" in files
        assert "wiki/modules/a/autha.md" not in files
        # a-tagged note is not applicable to b
        assert "notes/2026-01-01-zebra-note.md" not in files

    def test_repo_path_fallback_is_one_hop(self, tmp_path):
        """query_wiki(repo_path=<member>) targets the workspace knowledge base."""
        ws = _setup_workspace(tmp_path)
        res = _query(ws, repo_path=ws / "a")
        files = _files(res)
        assert "wiki/modules/b/authb.md" in files  # other repo visible: one hop

    def test_repo_path_fallback_with_filter(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        res = _query(ws, repo="a", repo_path=ws / "a")
        files = _files(res)
        assert "wiki/modules/a/autha.md" in files
        assert "wiki/modules/b/authb.md" not in files

    def test_output_dir_corpus_with_repo_filter(self, tmp_path):
        """output_dir picks the corpus; repo= narrows within it."""
        ws = _setup_workspace(tmp_path)
        # Corpus limited to a's partition: b's pages are not in the corpus at all.
        res = _query(ws, repo="a", output_dir=ws / "repowiki" / "wiki" / "modules" / "a")
        files = _files(res)
        assert any("autha.md" in f for f in files)
        assert not any("authb.md" in f for f in files)

    def test_repo_filter_unknown_repo_returns_only_globals(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        res = _query(ws, repo="ghost", output_dir=ws / "repowiki")
        files = _files(res)
        # no partition and no tagged pages for "ghost" — only global pages match
        assert "wiki/concepts/GlobalZebraConvention.md" in files
        assert "wiki/modules/a/autha.md" not in files
        assert "wiki/entities/SharedZebra.md" not in files

    def test_repo_filter_inert_outside_centralized_corpus(self, tmp_path):
        """Registry contract: repo= is ignored outside centralized workspaces."""
        repo = tmp_path / "solo"
        repowiki = repo / "repowiki"
        (repowiki / "wiki" / "modules").mkdir(parents=True)
        (repowiki / "wiki" / "modules" / "solo.md").write_text(
            "# Solo zebra\n\nsolo zebra module\n", encoding="utf-8"
        )
        res = _query(tmp_path, repo="anything", output_dir=repowiki)
        # Filter inert: the page is found even though it is not under an
        # "anything/" partition, and no repo_filter is reported.
        assert any("solo.md" in f for f in _files(res))
        assert "repo_filter" not in res
