"""ADR-0020 decision 3: the deterministic change plan (``.meta/change_plan.json``).

Pins the acceptance criteria of P1-3:

* a new top-level module on update produces ``add_subtree`` and its page is
  owed by the attempt (previously the cached ``first_module_tree.json`` blocked
  it entirely — see :func:`module_tree_coverage_gap` tests below);
* the same inputs produce a byte-identical plan;
* execution order is ``delete → add → replan → update`` and every operator
  settles to exactly one terminal status;
* a plan-driven update owes only the pages the plan asked for, so untouched
  modules do not read as "missing" and the job can still close ``done``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import git
import pytest

from codewiki.mcp.tools import change_plan as cp
from codewiki.mcp.tools import job_state as js
from codewiki.src.be.cluster_modules import module_tree_coverage_gap
from codewiki.src.config import Config


# --------------------------------------------------------------------------- #
# Fixtures local to this module
# --------------------------------------------------------------------------- #


def _leaf(*components: str, children: dict | None = None) -> dict:
    return {"components": list(components), "children": children or {}}


TREE_V1 = {
    "Core": {
        "components": ["core.py::Core"],
        "children": {"Leaf": _leaf("leaf.py::run")},
    },
    "Auth": _leaf("auth.py::login"),
}

TREE_V2 = {
    "Core": {
        "components": ["core.py::Core"],
        "children": {"Leaf": _leaf("leaf.py::run")},
    },
    "Billing": _leaf("billing.py::charge"),
}

MANIFEST = {
    "schema_version": 1,
    "pages": {
        "wiki/modules/Core.md": {"files": ["core.py"]},
        "wiki/modules/Leaf.md": {"files": ["leaf.py"]},
        "wiki/modules/Auth.md": {"files": ["auth.py"]},
        "wiki/overview.md": {"files": []},
    },
}


def _build(**overrides) -> dict:
    kwargs = {
        "previous_tree": TREE_V1,
        "module_tree": TREE_V2,
        "page_manifest": MANIFEST,
        "changed_files": [],
        "stale_pages": [],
        "base_commit": "abc123",
        "surface": "mcp",
        "job_id": "job-1",
    }
    kwargs.update(overrides)
    return cp.build_plan(**kwargs)


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    docs = repo / "repowiki"
    (docs / "wiki" / "modules").mkdir(parents=True)
    return repo, docs


def _write_plan(repo: Path, docs: Path, plan: dict) -> dict:
    _, stored = cp.write_plan(repo, docs, plan)
    return stored


def _manifest_on_disk(docs: Path, pages: dict) -> None:
    from codewiki.mcp.tools.page_manifest import save_manifest

    save_manifest(docs, {"schema_version": 1, "pages": dict(pages)})


def _page_ops(plan: dict) -> list[str]:
    return [str(op["page"]) for op in plan["ops"]]


# --------------------------------------------------------------------------- #
# Producer: determinism and operator selection
# --------------------------------------------------------------------------- #


def test_same_inputs_produce_a_byte_identical_plan():
    first = _build()
    second = _build()

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
    assert first["plan_hash"] == second["plan_hash"]


def test_plan_hash_ignores_execution_status():
    plan = _build()
    digested = plan["plan_hash"]

    plan["ops"][0]["status"] = "done"
    plan["job_id"] = "another-job"

    assert cp.compute_plan_hash(plan) == digested


def test_first_tree_has_no_operations():
    plan = cp.build_plan(previous_tree=None, module_tree=TREE_V1, page_manifest=MANIFEST)

    assert plan["ops"] == []
    assert plan["basis"]["tree"] == "no_previous_tree"
    assert plan["summary"]["total"] == 0


def test_new_top_level_module_becomes_add_subtree_plus_overview():
    plan = _build()

    ops = {(op["op"], op["page"]): op for op in plan["ops"]}
    assert ("delete_subtree", "Auth") in ops
    assert ("add_subtree", "Billing") in ops
    assert ("update_page", "overview") in ops
    # A brand-new module is covered by add_subtree; it must not also be replanned.
    assert ("replan_subtree", "Billing") not in ops

    add = ops[("add_subtree", "Billing")]
    assert add["reason"] == "new_module"
    assert add["path"] == ["Billing"]
    assert add["parent"] is None
    assert add["status"] == "pending"
    assert add["op_id"] == "add_subtree:Billing"
    assert plan["summary"] == {
        "total": 3,
        "delete_subtree": 1,
        "add_subtree": 1,
        "replan_subtree": 0,
        "update_page": 1,
    }


def test_changed_child_replans_leaf_then_parent():
    tree = {
        "Core": {
            "components": ["core.py::Core"],
            "children": {"Leaf": _leaf("leaf.py::run")},
        }
    }
    plan = _build(
        previous_tree=tree,
        module_tree=tree,
        changed_files=["leaf.py"],
    )

    replans = [op for op in plan["ops"] if op["op"] == "replan_subtree"]
    # Leaf first (deepest page), parent aggregate second.
    assert [op["page"] for op in replans] == ["Leaf", "Core"]
    assert replans[0]["reason"] == "changed_files"
    assert replans[0]["changed_files"] == ["leaf.py"]
    assert replans[1]["reason"] == "cascade"


def test_component_move_between_existing_modules_replans_both_pages():
    previous = {
        "A": _leaf("a.py::f"),
        "B": _leaf(),
    }
    current = {
        "A": _leaf(),
        "B": _leaf("a.py::f"),
    }
    manifest = {
        "pages": {
            "wiki/modules/A.md": {"files": ["a.py"]},
            "wiki/modules/B.md": {"files": []},
        }
    }

    plan = _build(
        previous_tree=previous,
        module_tree=current,
        page_manifest=manifest,
        changed_files=[],
    )

    replans = [op for op in plan["ops"] if op["op"] == "replan_subtree"]
    assert [(op["page"], op["reason"]) for op in replans] == [
        ("A", "components_changed"),
        ("B", "components_changed"),
    ]


def test_new_child_is_added_and_only_its_parent_is_cascaded():
    plan = _build(
        previous_tree={"Core": _leaf(children={})},
        module_tree={"Core": _leaf(children={"Fresh": _leaf("fresh.py::run")})},
        changed_files=["fresh.py"],
        page_manifest={"pages": {"wiki/modules/Core.md": {"files": ["core.py"]}}},
    )

    replanned = [op["page"] for op in plan["ops"] if op["op"] == "replan_subtree"]
    assert replanned == ["Core"]  # add_subtree covers Fresh; the parent aggregates it
    assert [op["page"] for op in plan["ops"] if op["op"] == "add_subtree"] == ["Fresh"]


def test_new_module_with_changed_sources_is_not_replanned():
    plan = _build(
        previous_tree={"Core": _leaf("core.py::Core")},
        module_tree={
            "Core": _leaf("core.py::Core"),
            "Billing": _leaf("billing.py::charge"),
        },
        changed_files=["billing.py"],
        page_manifest={"pages": {"wiki/modules/Core.md": {"files": ["core.py"]}}},
    )

    assert [op["op"] for op in plan["ops"]].count("replan_subtree") == 0
    assert _page_ops(plan) == ["Billing", "overview"]


def test_removed_child_deletes_page_and_replans_surviving_parent():
    prev = {
        "Core": {
            "components": ["core.py::Core"],
            "children": {"Leaf": _leaf("leaf.py::run"), "Util": _leaf("util.py::x")},
        }
    }
    new = {
        "Core": {
            "components": ["core.py::Core"],
            "children": {"Leaf": _leaf("leaf.py::run")},
        }
    }
    plan = _build(
        previous_tree=prev,
        module_tree=new,
        page_manifest={
            "pages": {
                "wiki/modules/Leaf.md": {"files": ["leaf.py"]},
                "wiki/modules/Util.md": {"files": ["util.py"]},
                "wiki/modules/Core.md": {"files": ["core.py"]},
            }
        },
    )

    delete = [op for op in plan["ops"] if op["op"] == "delete_subtree"]
    assert [(op["page"], op["page_key"], op["reason"]) for op in delete] == [
        ("Util", "wiki/modules/Util.md", "module_removed")
    ]
    cascades = [
        op for op in plan["ops"] if op["op"] == "replan_subtree" and op["reason"] == "cascade"
    ]
    assert [op["page"] for op in cascades] == ["Core"]


def test_removed_module_without_a_page_produces_no_delete():
    plan = _build(previous_tree={"Ghost": _leaf("ghost.py::x")}, module_tree={})

    assert plan["ops"] == []
    assert plan["summary"]["delete_subtree"] == 0


def test_operator_order_is_delete_add_replan_update():
    prev = {
        "Core": {
            "components": ["core.py::Core"],
            "children": {"Leaf": _leaf("leaf.py::run"), "Gone": _leaf("gone.py::x")},
        },
        "Keep": _leaf("keep.py::k"),
    }
    new = {
        "Core": {
            "components": ["core.py::Core"],
            "children": {"Leaf": _leaf("leaf.py::run")},
        },
        "Keep": _leaf("keep.py::k"),
        "Fresh": _leaf("fresh.py::new"),
    }
    manifest = {
        "pages": {
            "wiki/modules/Leaf.md": {"files": ["leaf.py"]},
            "wiki/modules/Gone.md": {"files": ["gone.py"]},
            "wiki/modules/Keep.md": {"files": ["keep.py"]},
            "notes/stale-note.md": {"files": ["doc.md"]},
            "wiki/overview.md": {"files": []},
        }
    }
    plan = _build(
        previous_tree=prev,
        module_tree=new,
        page_manifest=manifest,
        changed_files=["leaf.py", "doc.md"],
    )

    ranks = [cp._OP_RANK[op["op"]] for op in plan["ops"]]
    assert ranks == sorted(ranks)
    assert [op["op"] for op in plan["ops"]] == [
        "delete_subtree",
        "add_subtree",
        "replan_subtree",
        "replan_subtree",
        "update_page",
        "update_page",
    ]
    assert _page_ops(plan)[-2:] == ["stale-note", "overview"]


# --------------------------------------------------------------------------- #
# Executor: deletions are deterministic
# --------------------------------------------------------------------------- #


def test_execute_deletions_removes_page_and_manifest_entry(tmp_path):
    repo, docs = _repo(tmp_path)
    page = docs / "wiki" / "modules" / "Auth.md"
    page.write_text("# Auth\n", encoding="utf-8")
    _manifest_on_disk(
        docs,
        {"wiki/modules/Auth.md": {"files": ["auth.py"]}, "wiki/overview.md": {"files": []}},
    )
    _write_plan(repo, docs, _build())

    deleted = cp.execute_deletions(repo, docs)

    assert deleted == ["wiki/modules/Auth.md"]
    assert not page.exists()
    from codewiki.mcp.tools.page_manifest import load_manifest

    manifest = load_manifest(docs)
    assert "wiki/modules/Auth.md" not in manifest["pages"]
    assert "wiki/overview.md" in manifest["pages"]

    stored = cp.load_plan(repo, docs)
    statuses = {(op["op"], op["page"]): op["status"] for op in stored["ops"]}
    assert statuses[("delete_subtree", "Auth")] == "done"
    assert statuses[("add_subtree", "Billing")] == "pending"

    # Idempotent: a second pass has nothing pending to delete.
    assert cp.execute_deletions(repo, docs) == []


def test_execute_deletions_rejects_manifest_path_outside_wiki(tmp_path):
    repo, docs = _repo(tmp_path)
    outside = repo / "Auth.md"
    outside.write_text("# keep\n", encoding="utf-8")
    _manifest_on_disk(
        docs,
        {
            "../Auth.md": {"files": ["auth.py"]},
            "wiki/overview.md": {"files": []},
        },
    )
    plan = _build(
        page_manifest={
            "pages": {
                "../Auth.md": {"files": ["auth.py"]},
                "wiki/overview.md": {"files": []},
            }
        }
    )
    _write_plan(repo, docs, plan)

    deleted = cp.execute_deletions(repo, docs)

    assert deleted == []
    assert outside.read_text(encoding="utf-8") == "# keep\n"
    delete = next(
        op for op in cp.load_plan(repo, docs)["ops"] if op["op"] == "delete_subtree"
    )
    assert delete["status"] == "failed"


def test_plan_path_lives_next_to_the_job_ledger(tmp_path):
    repo, docs = _repo(tmp_path)

    assert cp.plan_path(repo, docs) == js.job_path(repo, docs).parent / "change_plan.json"


# --------------------------------------------------------------------------- #
# Executor: operator status machine
# --------------------------------------------------------------------------- #


def test_mark_op_done_settles_every_op_for_that_page(tmp_path):
    repo, docs = _repo(tmp_path)
    _write_plan(repo, docs, _build())

    summary = cp.mark_op_done(repo, docs, "Billing.md")

    assert summary is not None
    assert summary["done"] == 1
    assert "Billing" not in summary["pending_pages"]
    # Already done: no new write, so callers get None.
    assert cp.mark_op_done(repo, docs, "Billing.md") is None


def test_finalize_marks_owed_pages_failed_and_the_rest_skipped(tmp_path):
    repo, docs = _repo(tmp_path)
    _write_plan(repo, docs, _build())
    cp.mark_op_done(repo, docs, "Billing.md")

    summary = cp.finalize_plan(repo, docs, missing_pages=["overview"])

    assert summary is not None
    assert (summary["done"], summary["failed"], summary["skipped"], summary["pending"]) == (
        1,
        1,
        1,
        0,
    )
    stored = cp.load_plan(repo, docs)
    statuses = {(op["op"], op["page"]): op["status"] for op in stored["ops"]}
    # Deleting is the executor's job; this test never ran it, so the operator
    # is settled as skipped rather than reported as a missing page.
    assert statuses[("delete_subtree", "Auth")] == "skipped"
    assert statuses[("add_subtree", "Billing")] == "done"
    assert statuses[("update_page", "overview")] == "failed"


def test_finalize_skips_operators_the_run_never_touched(tmp_path):
    repo, docs = _repo(tmp_path)
    _write_plan(repo, docs, _build())

    summary = cp.finalize_plan(repo, docs)

    assert summary["skipped"] == 3
    assert summary["failed"] == 0
    stored = cp.load_plan(repo, docs)
    # ``Billing`` was owed but the run closed without it being missing from the
    # ledger's point of view — it is reported as skipped, not silently dropped.
    statuses = {(op["op"], op["page"]): op["status"] for op in stored["ops"]}
    assert statuses[("add_subtree", "Billing")] == "skipped"


def test_replay_owes_failed_and_skipped_operators(tmp_path):
    repo, docs = _repo(tmp_path)
    _write_plan(repo, docs, _build())
    cp.mark_op_done(repo, docs, "Billing.md")
    cp.finalize_plan(repo, docs, missing_pages=["overview"])

    owed = cp.plan_summary(cp.load_plan(repo, docs))
    # ``failed`` (page still missing) and ``skipped`` come back on the next
    # attempt — a resume is a replay of everything not done.
    assert owed["pending_pages"] == ["overview"]
    assert (owed["done"], owed["failed"], owed["skipped"]) == (1, 1, 1)

    # Writing the page settles an operator that failed on the previous attempt.
    cp.mark_op_done(repo, docs, "overview.md")
    settled = cp.plan_summary(cp.load_plan(repo, docs))
    assert settled["pending_pages"] == []
    assert (settled["done"], settled["failed"]) == (2, 0)


def test_failed_deletion_is_retried(tmp_path):
    repo, docs = _repo(tmp_path)
    page = docs / "wiki" / "modules" / "Auth.md"
    page.write_text("# Auth\n", encoding="utf-8")
    manifest = {"pages": {"wiki/modules/Auth.md": {"files": ["auth.py"]}}}
    _manifest_on_disk(docs, {"wiki/modules/Auth.md": {"files": ["auth.py"]}})
    plan = _build(page_manifest=manifest)
    plan["ops"][0]["status"] = "failed"  # sorted: delete_subtree comes first
    assert plan["ops"][0]["op"] == "delete_subtree"
    _write_plan(repo, docs, plan)

    assert cp.execute_deletions(repo, docs) == ["wiki/modules/Auth.md"]
    assert not page.exists()
    assert cp.load_plan(repo, docs)["ops"][0]["status"] == "done"


def test_write_plan_keeps_progress_for_the_same_job(tmp_path):
    repo, docs = _repo(tmp_path)
    _write_plan(repo, docs, _build())
    cp.mark_op_done(repo, docs, "Billing.md")

    _, stored = cp.write_plan(repo, docs, _build())
    assert [op["status"] for op in stored["ops"] if op["page"] == "Billing"] == ["done"]

    _, replaced = cp.write_plan(repo, docs, _build(job_id="job-2"))
    assert all(op["status"] == "pending" for op in replaced["ops"])


# --------------------------------------------------------------------------- #
# Clustering cache: a new component must force a re-cluster
# --------------------------------------------------------------------------- #


def test_module_tree_coverage_gap_reports_unassigned_components():
    tree = {
        "Core": {
            "components": ["a.py::f"],
            "children": {"Leaf": {"components": ["b.py::g"]}},
        }
    }

    assert module_tree_coverage_gap(tree, ["a.py::f", "b.py::g"]) == []
    assert module_tree_coverage_gap(tree, ["a.py::f", "b.py::g", "c.py::h"]) == ["c.py::h"]
    assert module_tree_coverage_gap({}, ["x.py::y"]) == ["x.py::y"]


def _config(tmp_path: Path, repo: Path, docs: Path) -> Config:
    return Config(
        repo_path=str(repo),
        output_dir=str(docs),
        dependency_graph_dir=str(tmp_path / "deps"),
        docs_dir=str(docs),
        max_depth=3,
        llm_base_url="http://localhost:1",
        llm_api_key="test",
        main_model="test-model",
        cluster_model="test-model",
    )


def test_cached_tree_missing_a_component_is_reclustered(tmp_path, monkeypatch):
    from codewiki.src.be import documentation_generator as dg

    repo = tmp_path / "repo"
    repo.mkdir()
    docs = tmp_path / "repowiki"
    (docs / ".meta").mkdir(parents=True)
    cached = {"Core": {"components": ["a.py::f"], "children": {}}}
    (docs / ".meta" / "first_module_tree.json").write_text(
        json.dumps(cached), encoding="utf-8"
    )

    calls: list[list[str]] = []

    def fake_cluster(leaf_nodes, components, config, completer=None):
        calls.append(list(leaf_nodes))
        return {"Core": {"components": ["a.py::f"], "children": {}},
                "New": {"components": ["b.py::g"], "children": {}}}

    monkeypatch.setattr(dg, "cluster_modules", fake_cluster)

    generator = dg.DocumentationGenerator(_config(tmp_path, repo, docs), backend=object())
    from types import SimpleNamespace

    components = {
        "a.py::f": SimpleNamespace(relative_path="a.py", source_code="def f(): pass\n"),
        "b.py::g": SimpleNamespace(relative_path="b.py", source_code="def g(): pass\n"),
    }
    monkeypatch.setattr(
        generator.graph_builder,
        "build_dependency_graph",
        lambda *a, **kw: (components, ["a.py::f", "b.py::g"], []),
    )

    async def no_pages(*a, **kw):
        return None

    monkeypatch.setattr(generator, "generate_module_documentation", no_pages)
    monkeypatch.setattr(generator, "create_documentation_metadata", lambda *a, **kw: None)

    asyncio.run(generator.run())
    assert calls == [["a.py::f", "b.py::g"]]
    saved = json.loads((docs / ".meta" / "first_module_tree.json").read_text(encoding="utf-8"))
    assert "New" in saved

    # The refreshed cache now covers every leaf node → no second re-cluster.
    asyncio.run(generator.run())
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# End-to-end: a new top-level module on update
# --------------------------------------------------------------------------- #


def test_update_with_a_new_top_level_module_plans_and_closes_done(analyzed_repo):
    from codewiki.mcp.tools.close_session import handle_close_session
    from codewiki.mcp.tools.doc_writer import handle_edit_doc_file, handle_write_doc_file
    from codewiki.mcp.tools.module_tree import handle_save_module_tree

    repo, store = analyzed_repo
    output = repo / "repowiki"
    tree_v1 = {"core": {"components": ["a.py::func_a"], "children": {}}}

    saved = json.loads(
        handle_save_module_tree({"repo_path": str(repo), "module_tree": tree_v1}, store)
    )
    assert saved["status"] == "saved", saved
    assert "change_plan" not in saved  # first tree: nothing to diff against

    for filename, page_type in (("core.md", "module"), ("overview.md", "overview")):
        written = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "repo_path": str(repo),
                        "filename": filename,
                        "page_type": page_type,
                        "content": f"# {filename[:-3]}\n\nbody\n",
                    },
                    store,
                )
            )
        )
        assert written.get("status") == "created", written
    closed = json.loads(handle_close_session({"repo_path": str(repo)}, store))
    assert closed["status"] == "closed", closed
    assert closed["job"]["phase"] == "done"

    # Second attempt: a new top-level module enters the repository.
    (repo / "billing.py").write_text(
        '"""billing"""\ndef charge():\n    return 1\n', encoding="utf-8"
    )
    git_repo = git.Repo(str(repo))
    git_repo.index.add(["billing.py"])
    git_repo.index.commit("add billing")
    js.start_job(repo, output, base_commit=git_repo.head.commit.hexsha)
    js.set_phase(repo, output, "analyzed")

    tree_v2 = {
        "core": {"components": ["a.py::func_a"], "children": {}},
        "billing": {"components": ["billing.py::charge"], "children": {}},
    }
    saved = json.loads(
        handle_save_module_tree({"repo_path": str(repo), "module_tree": tree_v2}, store)
    )
    plan = saved["change_plan"]
    assert plan["add_subtree"] == 1
    assert plan["delete_subtree"] == 0
    assert plan["pending_pages"] == ["billing", "overview"]

    # The plan-driven attempt owes exactly those pages, not every module again.
    job = js.load_job(repo, output)
    assert job["pages"]["planned_keys"] == ["billing", "overview"]

    for filename, page_type in (("billing.md", "module"), ("overview.md", "overview")):
        if filename == "overview.md":
            # Existing pages are regenerated through the edit path, not write.
            written = json.loads(
                asyncio.run(
                    handle_edit_doc_file(
                        {
                            "repo_path": str(repo),
                            "filename": filename,
                            "page_type": page_type,
                            "command": "str_replace",
                            "old_string": "# overview",
                            "new_string": "# overview\n\nrefreshed\n",
                        },
                        store,
                    )
                )
            )
            assert "error" not in written, written
            continue
        written = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "repo_path": str(repo),
                        "filename": filename,
                        "page_type": page_type,
                        "content": f"# {filename[:-3]}\n\nbody\n",
                    },
                    store,
                )
            )
        )
        assert written.get("status") in ("created", "updated"), written
    assert (output / "wiki" / "modules" / "billing.md").is_file()

    # Re-saving the same tree in this attempt replays the same plan (no reset).
    replanned = json.loads(
        handle_save_module_tree({"repo_path": str(repo), "module_tree": tree_v2}, store)
    )["change_plan"]
    assert replanned["plan_hash"] == plan["plan_hash"]
    assert replanned["pending_pages"] == []
    assert replanned["done"] == plan["total"]

    # force=True: the first close dropped the in-memory session and restoring
    # one depends on the SQLite cache; the close path under test starts after
    # that point either way.
    closed = json.loads(handle_close_session({"repo_path": str(repo), "force": True}, store))
    assert closed["status"] == "closed", closed
    assert closed["job"]["phase"] == "done"
    assert closed["job"]["missing_pages"] == []
    assert closed["change_plan"]["failed"] == 0
    assert closed["change_plan"]["skipped"] == 0


@pytest.mark.parametrize("content", ['{"ops": "not-a-list"}', "{not json"])
def test_corrupt_plan_is_fail_open(tmp_path, content):
    repo, docs = _repo(tmp_path)
    path = cp.plan_path(repo, docs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    assert cp.load_plan(repo, docs) is None
    assert cp.execute_deletions(repo, docs) == []
    assert cp.finalize_plan(repo, docs) is None
