"""Tests for ticket 04: layout-aware page-type routing + provenance.

Covers the write-routing seam (workspace_layout), the page_router module
partition, write_doc_file / ingest_note integration under centralized
workspaces, provenance accumulation (sources only grow) and the locked
concurrent-write contract.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl
from codewiki.mcp.tools.page_router import resolve_doc_path

URL_A = "https://example.com/a.git"
URL_B = "https://example.com/b.git"


class _StubStore:
    """SessionStore stand-in: no sessions ever resolve."""

    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _init_centralized(tmp_path, repos=(URL_A,)):
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
# Write-routing seam (workspace_layout)
# ---------------------------------------------------------------------------
class TestWriteRoutingSeam:
    def test_default_output_dir_centralized_member(self, tmp_path):
        _init_centralized(tmp_path)
        od = wl.default_output_dir(tmp_path / "a")
        assert od == tmp_path / "repowiki"

    def test_default_output_dir_single_repo_status_quo(self, tmp_path):
        repo = tmp_path / "solo"
        repo.mkdir()
        assert wl.default_output_dir(repo) == repo / "repowiki"

    def test_routing_for_write_member(self, tmp_path):
        _init_centralized(tmp_path)
        assert wl.routing_for_write(tmp_path / "repowiki", tmp_path / "a") == "a"

    def test_routing_for_write_unregistered_is_none(self, tmp_path):
        _init_centralized(tmp_path)
        stray = tmp_path / "stray"
        stray.mkdir()
        assert wl.routing_for_write(tmp_path / "repowiki", stray) is None

    def test_routing_for_write_custom_target_is_none(self, tmp_path):
        _init_centralized(tmp_path)
        custom = tmp_path / "custom-wiki"
        custom.mkdir()
        assert wl.routing_for_write(custom, tmp_path / "a") is None

    def test_routing_for_write_colocated_is_none(self, tmp_path):
        json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path)}))
        repo = tmp_path / "a"
        repo.mkdir()
        assert wl.routing_for_write(repo / "repowiki", repo) is None


# ---------------------------------------------------------------------------
# Provenance merge (sources only grow)
# ---------------------------------------------------------------------------
class TestProvenance:
    def test_read_top_level_and_metadata(self):
        top = '---\ntype: Entity\nrepo: "a"\n---\nbody'
        meta = '---\ntype: Entity\nmetadata:\n  repo: "b"\n---\nbody'
        assert wl.read_provenance(top) == {"a"}
        assert wl.read_provenance(meta) == {"b"}
        assert wl.read_provenance(None) == set()

    def test_merge_accumulates(self):
        old = '---\ntype: Entity\nrepo: "a"\n---\nold body'
        new = "---\ntype: Entity\n---\nnew body"
        merged = wl.merge_provenance(new, old, "b")
        assert 'repos: ["a", "b"]' in merged
        assert "new body" in merged
        assert wl.read_provenance(merged) == {"a", "b"}

    def test_merge_single_source_canonical(self):
        new = "---\ntype: Entity\n---\nbody"
        merged = wl.merge_provenance(new, None, "a")
        assert 'repo: "a"' in merged
        assert "repos:" not in merged

    def test_merge_replaces_existing_repo_lines(self):
        new = '---\ntype: Entity\nmetadata:\n  repo: "stale"\n---\nbody'
        merged = wl.merge_provenance(new, None, "a")
        assert wl.read_provenance(merged) == {"a", "stale"}
        assert merged.count("repo") >= 1


# ---------------------------------------------------------------------------
# page_router module partition
# ---------------------------------------------------------------------------
class TestModulePartition:
    def test_module_partitioned_with_repo_name(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        path = resolve_doc_path("auth.md", "module", od, repo_name="a")
        assert path == od / "wiki" / "modules" / "a" / "auth.md"

    def test_no_partition_without_repo_name(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        path = resolve_doc_path("auth.md", "module", od)
        assert path == od / "wiki" / "modules" / "auth.md"

    def test_shared_pool_types_never_partitioned(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        for ptype, subdir in (("entity", "entities"), ("concept", "concepts")):
            path = resolve_doc_path("Task.md", ptype, od, repo_name="a")
            assert path == od / "wiki" / subdir / "Task.md"


# ---------------------------------------------------------------------------
# write_doc_file integration
# ---------------------------------------------------------------------------
def _write_doc(tmp_path, repo_dir, filename, page_type, content):
    from codewiki.mcp.tools.doc_writer import handle_write_doc_file

    return json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "repo_path": str(repo_dir),
                    "filename": filename,
                    "page_type": page_type,
                    "content": content,
                },
                _StubStore(),
            )
        )
    )


class TestWriteDocFileCentralized:
    def test_module_page_lands_in_partition(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _write_doc(ws, ws / "a", "auth.md", "module", "# Auth\n\nmodule body")
        assert res["status"] == "created"
        assert (ws / "repowiki" / "wiki" / "modules" / "a" / "auth.md").is_file()
        assert not (ws / "a" / "repowiki").exists()

    def test_entity_page_lands_in_shared_pool_with_provenance(self, tmp_path):
        ws = _init_centralized(tmp_path)
        res = _write_doc(ws, ws / "a", "Task.md", "entity", "# Task\n\nentity body")
        assert res["status"] == "created"
        page = ws / "repowiki" / "wiki" / "entities" / "Task.md"
        assert page.is_file()
        assert wl.read_provenance(page.read_text(encoding="utf-8")) == {"a"}

    def test_provenance_accumulates_across_repos(self, tmp_path):
        ws = _init_centralized(tmp_path, repos=(URL_A, URL_B))
        _write_doc(ws, ws / "a", "Task.md", "entity", "# Task\n\nbody from a")
        res = _write_doc(ws, ws / "b", "Task.md", "entity", "# Task\n\nbody from b")
        assert res["status"] == "created"  # last write wins, no "exists" error
        page = ws / "repowiki" / "wiki" / "entities" / "Task.md"
        text = page.read_text(encoding="utf-8")
        assert wl.read_provenance(text) == {"a", "b"}
        assert "body from b" in text

    def test_module_existing_file_still_errors(self, tmp_path):
        ws = _init_centralized(tmp_path)
        _write_doc(ws, ws / "a", "auth.md", "module", "# Auth")
        res = _write_doc(ws, ws / "a", "auth.md", "module", "# Auth v2")
        assert "error" in res

    def test_colocated_write_behaviour_unchanged(self, tmp_path):
        repo = tmp_path / "solo"
        repo.mkdir()
        res = _write_doc(repo, repo, "auth.md", "module", "# Auth")
        assert res["status"] == "created"
        assert (repo / "repowiki" / "wiki" / "modules" / "auth.md").is_file()
        # existing-file guard preserved outside the shared pool
        res2 = _write_doc(repo, repo, "auth.md", "module", "# Auth v2")
        assert "error" in res2


# ---------------------------------------------------------------------------
# Concurrent shared-pool writes keep provenance (ticket 04 acceptance)
# ---------------------------------------------------------------------------
class TestConcurrentSharedPool:
    def test_concurrent_writes_keep_all_sources(self, tmp_path):
        ws = _init_centralized(tmp_path, repos=(URL_A, URL_B))
        page = ws / "repowiki" / "wiki" / "entities" / "Task.md"
        page.parent.mkdir(parents=True, exist_ok=True)

        sources = ["a", "b", "a", "b"]
        errors = []

        def worker(src, i):
            try:
                from codewiki.src.locks import file_lock

                content = f'---\ntype: Entity\ntitle: "Task"\n---\nbody {src}-{i}'
                with file_lock(page) as f:
                    old = f.read()
                    merged = wl.merge_provenance(content, old or None, src)
                    f.seek(0)
                    f.write(merged)
                    f.truncate()
            except Exception as e:  # pragma: no cover - surfaced via errors
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(sources[i % 2], i)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        text = page.read_text(encoding="utf-8")
        assert wl.read_provenance(text) == {"a", "b"}
        # exactly one frontmatter fence pair, content intact
        assert text.count("---") == 2
        assert "body" in text


# ---------------------------------------------------------------------------
# ingest_note integration
# ---------------------------------------------------------------------------
class TestIngestNoteCentralized:
    def test_note_lands_in_workspace_pool_with_provenance(self, tmp_path):
        from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

        ws = _init_centralized(tmp_path)
        res = json.loads(
            handle_ingest_note(
                {
                    "repo_path": str(ws / "a"),
                    "title": "gateway MITM needs sslVerify off",
                    "content": "git config http.sslVerify false for github",
                    "note_type": "pitfall",
                },
                _StubStore(),
            )
        )
        note_path = res.get("note_path") or ""
        assert note_path.startswith(str(ws / "repowiki" / "notes"))
        text = (ws / "repowiki" / "notes" / Path(note_path).name).read_text(encoding="utf-8")
        assert wl.read_provenance(text) == {"a"}

    def test_note_single_repo_no_provenance(self, tmp_path):
        from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

        repo = tmp_path / "solo"
        repo.mkdir()
        res = json.loads(
            handle_ingest_note(
                {
                    "repo_path": str(repo),
                    "title": "a plain note",
                    "content": "nothing special",
                },
                _StubStore(),
            )
        )
        note_path = res.get("note_path") or ""
        assert note_path.startswith(str(repo / "repowiki" / "notes"))
        text = (repo / "repowiki" / "notes" / Path(note_path).name).read_text(encoding="utf-8")
        assert wl.read_provenance(text) == set()
