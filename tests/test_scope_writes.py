"""Tests for ticket 06: manual knowledge writes with explicit scope.

Three scope markings must all be writable and land correctly:
single-repo (auto or explicit), multi-repo (repos: [...]), and global
(no provenance). Verified at the provenance level and through the repo=
query filter end to end.
"""

from __future__ import annotations

import asyncio
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


def _init_centralized(tmp_path, repos=(URL_A, URL_B)):
    json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": "centralized"}))
    for url in repos:
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        (tmp_path / name).mkdir(exist_ok=True)
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": url, "clone": False}
            )
        )
    return tmp_path


# ---------------------------------------------------------------------------
# parse_scope_arg
# ---------------------------------------------------------------------------
class TestParseScopeArg:
    def test_none_and_empty(self):
        assert wl.parse_scope_arg(None) is None
        assert wl.parse_scope_arg("") is None
        assert wl.parse_scope_arg("   ") is None

    def test_global_aliases(self):
        for v in ("global", "Global", "product", "product-line", "全局"):
            assert wl.parse_scope_arg(v) == "global"

    def test_single_name(self):
        assert wl.parse_scope_arg("a") == ["a"]

    def test_comma_separated(self):
        assert wl.parse_scope_arg("a, b") == ["a", "b"]

    def test_list(self):
        assert wl.parse_scope_arg(["a", "b"]) == ["a", "b"]

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            wl.parse_scope_arg([])

    def test_blank_items_raise(self):
        with pytest.raises(ValueError):
            wl.parse_scope_arg(" , ")


# ---------------------------------------------------------------------------
# merge_provenance explicit scope
# ---------------------------------------------------------------------------
class TestMergeProvenanceExplicit:
    def test_global_strips_old_provenance(self):
        old = '---\ntype: Entity\nrepo: "a"\n---\nold'
        new = "---\ntype: Entity\n---\nnew"
        merged = wl.merge_provenance(new, old, "b", explicit_scope="global")
        assert wl.read_provenance(merged) == set()

    def test_list_sets_exactly(self):
        old = '---\ntype: Entity\nrepo: "a"\n---\nold'
        new = "---\ntype: Entity\n---\nnew"
        merged = wl.merge_provenance(new, old, "c", explicit_scope=["a", "b"])
        assert wl.read_provenance(merged) == {"a", "b"}

    def test_default_still_accumulates(self):
        old = '---\ntype: Entity\nrepo: "a"\n---\nold'
        new = "---\ntype: Entity\n---\nnew"
        merged = wl.merge_provenance(new, old, "b")
        assert wl.read_provenance(merged) == {"a", "b"}


# ---------------------------------------------------------------------------
# ingest_note scopes
# ---------------------------------------------------------------------------
def _ingest(tmp_path, repo_dir, title, scope=None):
    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

    args = {
        "repo_path": str(repo_dir),
        "title": title,
        "content": f"body of {title}",
        "note_type": "decision",
    }
    if scope is not None:
        args["scope"] = scope
    return json.loads(handle_ingest_note(args, _StubStore()))


def _note_text(res):
    note_path = res.get("note_path") or ""
    return Path(note_path).read_text(encoding="utf-8")


class TestIngestNoteScopes:
    def test_default_auto_stamp(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _ingest(ws, ws / "a", "auto scoped decision")
        assert wl.read_provenance(_note_text(res)) == {"a"}

    def test_global_scope_no_stamp(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _ingest(ws, ws / "a", "global convention", scope="global")
        assert wl.read_provenance(_note_text(res)) == set()

    def test_multi_repo_scope(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _ingest(ws, ws / "a", "joint interface decision", scope=["a", "b"])
        assert wl.read_provenance(_note_text(res)) == {"a", "b"}

    def test_invalid_scope_errors(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _ingest(ws, ws / "a", "bad scope", scope=[])
        assert "error" in res


# ---------------------------------------------------------------------------
# write_doc_file scopes
# ---------------------------------------------------------------------------
def _write_doc(tmp_path, repo_dir, filename, scope=None):
    from codewiki.mcp.tools.doc_writer import handle_write_doc_file

    args = {
        "repo_path": str(repo_dir),
        "filename": filename,
        "page_type": "entity",
        "content": f"# {filename}\n\nbody",
    }
    if scope is not None:
        args["scope"] = scope
    return json.loads(asyncio.run(handle_write_doc_file(args, _StubStore())))


class TestWriteDocFileScopes:
    def test_global_scope_no_stamp(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _write_doc(ws, ws / "a", "GlobalThing.md", scope="global")
        page = ws / "repowiki" / "wiki" / "entities" / "GlobalThing.md"
        assert res["status"] == "created"
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == set()

    def test_multi_repo_scope_comma_string(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_doc(ws, ws / "a", "JointThing.md", scope="a, b")
        page = ws / "repowiki" / "wiki" / "entities" / "JointThing.md"
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == {"a", "b"}

    def test_global_overwrite_strips_old_provenance(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_doc(ws, ws / "a", "Promoted.md")  # auto-stamped with a
        page = ws / "repowiki" / "wiki" / "entities" / "Promoted.md"
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == {"a"}
        # Re-scope to global: deliberate re-scoping clears provenance.
        _write_doc(ws, ws / "b", "Promoted.md", scope="global")
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == set()

    def test_default_overwrite_still_accumulates(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_doc(ws, ws / "a", "Accrued.md")
        _write_doc(ws, ws / "b", "Accrued.md")
        page = ws / "repowiki" / "wiki" / "entities" / "Accrued.md"
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == {"a", "b"}


# ---------------------------------------------------------------------------
# End to end: scoped knowledge hits the right repo= queries
# ---------------------------------------------------------------------------
class TestScopedKnowledgeQueryable:
    def test_global_and_multi_repo_filter_hits(self, tmp_path):
        from codewiki.mcp.tools.knowledge_loop import handle_query_wiki

        ws = _init_centralized(tmp_path)
        _ingest(ws, ws / "a", "quokka global convention", scope="global")
        _ingest(ws, ws / "a", "quokka joint decision", scope=["a", "b"])
        _ingest(ws, ws / "a", "quokka only-a pitfall")  # auto-stamp a

        def query(repo):
            return json.loads(
                handle_query_wiki(
                    {"query": "quokka", "repo": repo, "output_dir": str(ws / "repowiki")},
                    _StubStore(),
                )
            )

        files_a = {r["file"] for r in query("a").get("results", [])}
        files_b = {r["file"] for r in query("b").get("results", [])}

        def find(files, frag):
            return any(frag in f for f in files)

        # global + joint + a-tagged all applicable to a
        assert find(files_a, "quokka-global-convention")
        assert find(files_a, "quokka-joint-decision")
        assert find(files_a, "quokka-only-a-pitfall")
        # b sees global + joint, not the a-only note
        assert find(files_b, "quokka-global-convention")
        assert find(files_b, "quokka-joint-decision")
        assert not find(files_b, "quokka-only-a-pitfall")
