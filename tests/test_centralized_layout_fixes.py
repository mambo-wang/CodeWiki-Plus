"""Regression tests for the centralized-layout defects found in a full MCP sweep.

Covers four fixes:

1. ``init_wiki`` routes business repos of a centralized workspace into the
   workspace corpus (design doc §6: modules → ``wiki/modules/<repo>/``,
   shared-pool dirs → workspace ``repowiki/``) instead of recreating
   ``<repo>/repowiki/`` and re-injecting the AGENTS.md wiki block that
   ``add_workspace_repo`` had just removed.
2. ``get_module_tree`` resolves the namespaced tree
   ``<ws>/.codewiki/<repo>/module_tree.json`` instead of only
   ``<corpus>/.meta/module_tree.json``.
3. ``ingest_note`` warns when provenance cannot be stamped because no writing
   repo is resolvable (silent global degradation).
5. ``run_git_bounded`` enforces a hard wall-clock bound (the nominal 15s
   advisory once held the MCP event loop for 204s).
7. Shared-pool provenance is stamped under ``metadata:`` (OKF v0.2 §4/§5),
   matching ``ingest_note`` — a top-level ``repo:`` trips okf_conformance.

Style follows ``tests/test_workspace_layout.py``.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl
from codewiki.mcp.tools.doc_writer import handle_write_doc_file
from codewiki.mcp.tools.evidence import evidence_roots, handle_stamp_evidence
from codewiki.mcp.tools.init_wiki import handle_init_wiki
from codewiki.mcp.tools.knowledge_loop import handle_ingest_note
from codewiki.mcp.tools.legacy_tools import handle_get_module_tree
from codewiki.mcp.tools.wiki_lint import _check_stale_evidence
from codewiki.src import git_sync as gs
from codewiki.src.evidence import hash_resource

URL_A = "https://example.com/a.git"  # derived name: a


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _init(tmp_path, layout="centralized"):
    return json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": layout}))


def _register(tmp_path, url=URL_A):
    return json.loads(
        wb.handle_add_workspace_repo({"workspace_path": str(tmp_path), "url": url, "clone": False})
    )


# ---------------------------------------------------------------------------
# Fix 1 — init_wiki centralized routing (design doc §6)
# ---------------------------------------------------------------------------
class TestInitWikiCentralizedRouting:
    def test_routes_centralized_business_repo_into_corpus(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        # A customized workspace schema.yaml must survive the business-repo init.
        marker = "# user-customized schema"
        schema = tmp_path / "repowiki" / "schema.yaml"
        schema.write_text(schema.read_text(encoding="utf-8") + marker + "\n", encoding="utf-8")

        res = json.loads(handle_init_wiki({"repo_path": str(repo)}))

        assert res["status"] == "ok"
        assert res["layout"] == "centralized"
        assert Path(res["output_dir"]) == (tmp_path / "repowiki").resolve()
        # §6: modules partition ensured inside the corpus
        assert (tmp_path / "repowiki" / "wiki" / "modules" / "a").is_dir()
        # business repo stays pure code — no in-repo repowiki/, no AGENTS.md block
        assert not (repo / "repowiki").exists()
        assert not (repo / "AGENTS.md").exists()
        # workspace schema.yaml not clobbered, shared dirs exist
        assert marker in schema.read_text(encoding="utf-8")
        assert (tmp_path / "repowiki" / "notes").is_dir()

    def test_explicit_output_dir_not_hijacked(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        custom = tmp_path / "a" / "custom-wiki"

        res = json.loads(handle_init_wiki({"repo_path": str(repo), "output_dir": str(custom)}))

        # Explicit output_dir is the caller's directory-level choice (§7):
        # never hijacked, but centralized safety defaults still apply.
        assert res["status"] == "ok"
        assert Path(res["output_dir"]) == custom.resolve()
        assert (custom / "schema.yaml").is_file()
        assert not (repo / "AGENTS.md").exists()

    def test_still_allows_workspace_root(self, tmp_path):
        _init(tmp_path)
        res = json.loads(handle_init_wiki({"repo_path": str(tmp_path)}))
        assert res.get("status") == "ok"

    def test_still_allows_standalone_repo(self, tmp_path):
        standalone = tmp_path / "standalone"
        standalone.mkdir()
        res = json.loads(handle_init_wiki({"repo_path": str(standalone)}))
        assert res.get("status") == "ok"
        assert res.get("layout") is None


# ---------------------------------------------------------------------------
# Fix 2 — get_module_tree namespaced lookup
# ---------------------------------------------------------------------------
class TestGetModuleTreeLookup:
    def test_reads_namespaced_tree(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        ns = tmp_path / ".codewiki" / "a"
        ns.mkdir(parents=True)
        tree = {"svc": {"components": ["x.py::y"], "children": {}}}
        (ns / "module_tree.json").write_text(json.dumps(tree), encoding="utf-8")

        res = json.loads(
            asyncio.run(
                handle_get_module_tree(
                    {"repo_path": str(repo), "output_dir": str(tmp_path / "repowiki")}, None
                )
            )
        )

        assert res["status"] == "success"
        assert res["module_tree_path"] == str(ns / "module_tree.json")
        assert res["total_modules"] == 1

    def test_falls_back_to_corpus_meta(self, tmp_path):
        """Pre-namespacing layout: <corpus>/.meta/module_tree.json still loads."""
        corpus = tmp_path / "repowiki"
        (corpus / ".meta").mkdir(parents=True)
        tree = {"legacy": {"components": [], "children": {}}}
        (corpus / ".meta" / "module_tree.json").write_text(json.dumps(tree), encoding="utf-8")
        repo = tmp_path / "a"
        repo.mkdir()

        res = json.loads(
            asyncio.run(
                handle_get_module_tree({"repo_path": str(repo), "output_dir": str(corpus)}, None)
            )
        )

        assert res["status"] == "success"
        assert res["total_modules"] == 1


# ---------------------------------------------------------------------------
# Fix 3 — ingest_note provenance visibility
# ---------------------------------------------------------------------------
class TestIngestNoteProvenance:
    def test_warns_when_writing_repo_unknown(self, tmp_path):
        _init(tmp_path)
        res = json.loads(
            handle_ingest_note(
                {"output_dir": str(tmp_path / "repowiki"), "title": "T1", "content": "body"}, None
            )
        )
        assert res["status"] == "ingested"
        assert "provenance_warning" in res

    def test_stamps_provenance_with_repo_path(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)

        res = json.loads(
            handle_ingest_note(
                {
                    "output_dir": str(tmp_path / "repowiki"),
                    "repo_path": str(repo),
                    "title": "T2",
                    "content": "body",
                },
                None,
            )
        )

        assert res["status"] == "ingested"
        assert "provenance_warning" not in res
        # Filename slug is tooling-internal (short titles fall back to a hash),
        # so assert on content: the note must carry the writing repo's tag.
        notes = sorted((tmp_path / "repowiki" / "notes").glob("*.md"))
        assert notes, "no note file was written"
        assert any('repo: "a"' in p.read_text(encoding="utf-8") for p in notes)


# ---------------------------------------------------------------------------
# Fix 6 — repo:// evidence roots under a shared corpus
# ---------------------------------------------------------------------------
CODE_FILE = "code/x.py"
SOURCE = "def a():\n    return 1\n"
RESOURCE = "repo://code/x.py#L1-L2"


def _write_page(path, sources_block=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntype: Module\ntitle: P\nstatus: stable\n{sources_block}---\n\n# P\n",
        encoding="utf-8",
    )


def _legacy_sources_block(resource, content_hash):
    return f'sources:\n- id: {resource}\n  resource: {resource}\n  content_hash: "{content_hash}"\n'


class TestEvidenceRoots:
    def test_centralized_roots_include_member_repos(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        (tmp_path / "a").mkdir(exist_ok=True)
        roots = evidence_roots(tmp_path / "repowiki")
        assert (tmp_path / "a").resolve() in roots
        assert roots[-1] == tmp_path.resolve()  # status-quo fallback last

    def test_stamp_records_repo_and_lint_resolves(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        (repo / "code").mkdir(parents=True)
        (repo / CODE_FILE).write_text(SOURCE, encoding="utf-8")
        od = tmp_path / "repowiki"
        page = od / "wiki" / "modules" / "a" / "p.md"
        _write_page(page)

        res = json.loads(
            handle_stamp_evidence(
                {
                    "page": "wiki/modules/a/p.md",
                    "evidence": [{"resource": RESOURCE}],
                    "output_dir": str(od),
                    "repo_path": str(repo),
                },
                None,
            )
        )

        assert res["stamped"]["new"] == 1
        # YAML emits plain scalars unquoted, so match the line, not a literal.
        assert re.search(r"^\s+repo:\s*a\s*$", page.read_text(encoding="utf-8"), re.M)
        assert [i for i in _check_stale_evidence(od) if i["check"] == "stale_evidence"] == []

    def test_legacy_entry_without_repo_field_resolves(self, tmp_path):
        """Entries stamped before the `repo` field existed must still verify."""
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        (repo / "code").mkdir(parents=True)
        (repo / CODE_FILE).write_text(SOURCE, encoding="utf-8")
        od = tmp_path / "repowiki"
        _write_page(
            od / "wiki" / "legacy.md",
            _legacy_sources_block(RESOURCE, hash_resource(RESOURCE, repo)),
        )

        assert [i for i in _check_stale_evidence(od) if i["check"] == "stale_evidence"] == []

    def test_still_flags_truly_missing_evidence(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        (tmp_path / "a").mkdir(exist_ok=True)
        od = tmp_path / "repowiki"
        _write_page(
            od / "wiki" / "gone.md", _legacy_sources_block("repo://nope.py", "sha256:deadbeef")
        )

        issues = _check_stale_evidence(od)
        assert any(i["check"] == "stale_evidence" and "disappeared" in i["message"] for i in issues)

    def test_colocated_uses_repo_root(self, tmp_path):
        """No workspace above: status-quo resolution (output_dir.parent)."""
        repo = tmp_path / "r"
        od = repo / "repowiki"
        od.mkdir(parents=True)
        (repo / "code").mkdir()
        (repo / CODE_FILE).write_text(SOURCE, encoding="utf-8")
        _write_page(
            od / "wiki" / "p.md", _legacy_sources_block(RESOURCE, hash_resource(RESOURCE, repo))
        )

        assert evidence_roots(od) == [repo.resolve()]
        assert _check_stale_evidence(od) == []


# ---------------------------------------------------------------------------
# Fix 7 — shared-pool provenance belongs under metadata:
# ---------------------------------------------------------------------------
def _frontmatter_dict(path: Path) -> dict:
    import yaml

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} has no frontmatter"
    end = text.find("\n---", 3)
    data = yaml.safe_load(text[4:end]) or {}
    assert isinstance(data, dict)
    return data


class TestProvenancePlacement:
    def test_shared_pool_write_stamps_under_metadata(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)

        res = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "output_dir": str(tmp_path / "repowiki"),
                        "repo_path": str(repo),
                        "filename": "probe-concept.md",
                        "page_type": "concept",
                        "title": "ProbeConcept",
                        "content": "# ProbeConcept\n\nbody\n",
                    },
                    None,
                )
            )
        )

        assert res["status"] == "created"
        fm = _frontmatter_dict(Path(res["path"]))
        assert "repo" not in fm and "repos" not in fm, f"provenance leaked: {fm}"
        assert fm["metadata"]["repo"] == "a"

    def test_existing_top_level_repo_is_migrated(self, tmp_path):
        """Pages written before the fix carry a top-level repo: — re-fold it."""
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)

        res = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "output_dir": str(tmp_path / "repowiki"),
                        "repo_path": str(repo),
                        "filename": "legacy-concept.md",
                        "page_type": "concept",
                        "content": '---\ntype: Concept\ntitle: "Legacy"\nrepo: "legacy"\n---\n\n# Legacy\n',
                    },
                    None,
                )
            )
        )

        fm = _frontmatter_dict(Path(res["path"]))
        assert "repo" not in fm and "repos" not in fm
        assert set(fm["metadata"]["repos"]) == {"a", "legacy"}

    def test_global_scope_strips_provenance(self, tmp_path):
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)

        res = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "output_dir": str(tmp_path / "repowiki"),
                        "repo_path": str(repo),
                        "filename": "global-concept.md",
                        "page_type": "concept",
                        "scope": "global",
                        "content": '---\ntype: Concept\ntitle: "G"\nrepo: "legacy"\n---\n\n# G\n',
                    },
                    None,
                )
            )
        )

        text = Path(res["path"]).read_text(encoding="utf-8")
        assert wl.read_provenance(text) == set()
        assert "repo:" not in text

    def test_merge_creates_metadata_node(self):
        merged = wl.merge_provenance("---\ntype: Entity\n---\nbody", None, "a")
        assert "metadata:" in merged
        assert '\n  repo: "a"' in merged
        assert wl.read_provenance(merged) == {"a"}

    def test_merge_reuses_existing_metadata_node(self):
        merged = wl.merge_provenance(
            "---\ntype: Entity\nmetadata:\n  origin: x\n---\nbody", None, "a"
        )
        import yaml

        fm = yaml.safe_load(merged.split("\n---")[0].split("---\n")[1])
        assert fm["metadata"] == {"origin": "x", "repo": "a"}

    def test_merge_drops_emptied_metadata_node(self):
        merged = wl.merge_provenance(
            '---\ntype: Entity\nmetadata:\n  repo: "x"\n---\nbody',
            None,
            None,
            explicit_scope="global",
        )
        assert "metadata:" not in merged
        assert wl.read_provenance(merged) == set()

    def test_module_pages_are_not_stamped(self, tmp_path):
        """Module pages are partitioned by directory — no provenance needed."""
        _init(tmp_path)
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)

        res = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "output_dir": str(tmp_path / "repowiki"),
                        "repo_path": str(repo),
                        "filename": "mod.md",
                        "page_type": "module",
                        "content": "# Mod\n\nbody\n",
                    },
                    None,
                )
            )
        )

        assert "CodeWiki-Plus" not in res["path"]  # tmp repo is named "a"
        assert "a" in Path(res["path"]).parts
        assert wl.read_provenance(Path(res["path"]).read_text(encoding="utf-8")) == set()


# ---------------------------------------------------------------------------
# Fix 5 — hard-bounded git calls
# ---------------------------------------------------------------------------
class TestRunGitBounded:
    def test_success_returns_stdout(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        res = gs.run_git_bounded(tmp_path, ["rev-parse", "--is-inside-work-tree"], timeout=10)
        assert res is not None
        assert res.stdout.strip() == "true"

    def test_timeout_returns_none_and_kills_child(self, tmp_path, monkeypatch):
        import subprocess as sp

        import psutil

        class FakeProc:
            def __init__(self, *a, **k):
                self.pid = 999999  # never a real process
                self._calls = 0
                self.killed = False

            def communicate(self, timeout=None):
                self._calls += 1
                if self._calls == 1:
                    raise sp.TimeoutExpired(cmd="git", timeout=timeout)
                return ("", "")

            def kill(self):
                self.killed = True

        procs: list[FakeProc] = []

        def fake_popen(*a, **k):
            procs.append(FakeProc())
            return procs[-1]

        # psutil.Process must never touch a real process in a unit test.
        monkeypatch.setattr(psutil, "Process", lambda pid: (_ for _ in ()).throw(RuntimeError()))
        monkeypatch.setattr(gs.subprocess, "Popen", fake_popen)

        assert gs.run_git_bounded(tmp_path, ["fetch"], timeout=0.01) is None
        assert procs and procs[0].killed

    def test_ok_only_false_keeps_rc_visible(self, tmp_path):
        """D12 callers (session_ff_only/auto_push) must distinguish "git
        refused" (CompletedProcess, rc != 0 → report) from "network" (None →
        silent).  rev-parse HEAD on an empty repo exits non-zero."""
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)

        res = gs.run_git_bounded(tmp_path, ["rev-parse", "HEAD"], timeout=10, ok_only=False)
        assert res is not None
        assert res.returncode != 0

        # default (ok_only=True) swallows the failure — advisory behaviour
        assert gs.run_git_bounded(tmp_path, ["rev-parse", "HEAD"], timeout=10) is None
