"""B4：change_plan 计划写入门禁的纯函数与 MCP 写入回归。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import change_plan as cp
from codewiki.mcp.tools.doc_writer import (
    _save_history,
    handle_edit_doc_file,
    handle_write_doc_file,
)


def _plan() -> dict:
    plan = {
        "schema_version": 1,
        "surface": "mcp",
        "job_id": "job-b4",
        "base_commit": None,
        "basis": {},
        "summary": {},
        "ops": [
            {
                "op_id": "add_subtree:Core",
                "op": "add_subtree",
                "page": "Core",
                "path": ["Core"],
                "status": "pending",
            },
            {
                "op_id": "update_page:wiki/overview.md",
                "op": "update_page",
                "page": "overview",
                "page_key": "wiki/overview.md",
                "status": "pending",
            },
            {
                "op_id": "replan_subtree:Done",
                "op": "replan_subtree",
                "page": "Done",
                "path": ["Done"],
                "status": "done",
            },
            {
                "op_id": "delete_subtree:Gone",
                "op": "delete_subtree",
                "page": "Gone",
                "path": ["Gone"],
                "page_key": "wiki/modules/Gone.md",
                "status": "pending",
            },
        ],
    }
    plan["plan_hash"] = cp.compute_plan_hash(plan)
    return plan


def _repo(tmp_path: Path, *, with_plan: bool = True) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    output = repo / "repowiki"
    output.mkdir(parents=True)
    if with_plan:
        cp.write_plan(repo, output, _plan())
    return repo, output


def _write(repo: Path, filename: str, **extra) -> dict:
    args = {
        "repo_path": str(repo),
        "filename": filename,
        "page_type": "module",
        "content": f"# {filename}\n\nbody\n",
        **extra,
    }
    result: dict = json.loads(asyncio.run(handle_write_doc_file(args, SessionStore())))
    return result


def _events(output: Path) -> list[dict]:
    plan = cp.load_plan(output, output)
    return ((plan or {}).get("write_guard") or {}).get("unplanned_writes") or []


def test_observe_allows_and_records_unplanned_write(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    decision = evaluate_page_write(
        cp.load_plan(repo, output),
        output,
        doc_path=output / "wiki/modules/Rogue.md",
        filename="Rogue.md",
        page_type="module",
        mode="observe",
        tool="write_doc_file",
    )

    assert decision["classification"] == "unplanned"
    assert decision["outcome"] == "allowed"
    assert decision["allowed_by"] == "observe"
    assert decision["unplanned_write"] is True
    assert decision["warning"]

    result = _write(repo, "Rogue.md")
    assert result["status"] == "created"
    assert result["write_guard"]["classification"] == "unplanned"
    assert result["warning"] == result["write_guard"]["warning"]
    assert (output / "wiki/modules/Rogue.md").is_file()
    assert _events(output)[0]["outcome"] == "allowed"


def test_enforce_allows_pending_module_and_marks_operator_done(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(repo, "Core.md", write_guard_mode="enforce")

    assert result["status"] == "created"
    assert result["write_guard"]["classification"] == "pending"
    assert result["write_guard"]["allowed_by"] == "pending_pages"
    assert _events(output) == []
    stored = cp.load_plan(repo, output)
    core = next(op for op in stored["ops"] if op["page"] == "Core")
    assert core["status"] == "done"


def test_enforce_allows_pending_overview_update(tmp_path):
    repo, output = _repo(tmp_path)
    page = output / "wiki/overview.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# overview\n\nold\n", encoding="utf-8")

    result = json.loads(
        asyncio.run(
            handle_edit_doc_file(
                {
                    "repo_path": str(repo),
                    "filename": "overview.md",
                    "page_type": "module",
                    "command": "str_replace",
                    "old_string": "old",
                    "new_string": "new",
                    "write_guard_mode": "enforce",
                },
                None,
            )
        )
    )

    assert result["status"] == "edited"
    assert result["write_guard"]["classification"] == "pending"
    assert "new" in page.read_text(encoding="utf-8")


def test_enforce_blocks_unplanned_write_without_touching_disk(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(repo, "Rogue.md", write_guard_mode="enforce")

    assert "error" in result
    assert result["write_guard"]["classification"] == "unplanned"
    assert result["write_guard"]["outcome"] == "blocked"
    assert result["write_guard"]["unplanned_write"] is True
    assert not (output / "wiki/modules/Rogue.md").exists()
    assert _events(output)[0]["outcome"] == "blocked"
    summary = cp.plan_summary(cp.load_plan(repo, output))
    assert summary["unplanned_write_count"] == 1
    assert summary["blocked_write_count"] == 1


def test_enforce_current_target_allows_one_unplanned_page_and_records_it(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(
        repo,
        "Rogue.md",
        write_guard_mode="enforce",
        target="Rogue.md",
    )

    assert result["status"] == "created"
    assert result["write_guard"]["allowed_by"] == "current_target"
    assert result["write_guard"]["unplanned_write"] is True
    assert result["warning"]
    assert _events(output)[0]["outcome"] == "allowed"


def test_target_must_match_the_actual_page(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(
        repo,
        "Rogue.md",
        write_guard_mode="enforce",
        target="Core.md",
    )

    assert "error" in result
    assert result["write_guard"]["reason"] == "target_mismatch"
    assert not (output / "wiki/modules/Rogue.md").exists()


def test_target_cannot_borrow_a_nested_same_stem_page(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    kwargs = {
        "doc_path": output / "wiki/modules/nested/Rogue.md",
        "filename": "Rogue.md",
        "page_type": "module",
        "tool": "write_doc_file",
    }

    bare = evaluate_page_write(
        cp.load_plan(repo, output), output, mode="enforce", target="Rogue.md", **kwargs
    )
    routed = evaluate_page_write(
        cp.load_plan(repo, output),
        output,
        mode="enforce",
        target="wiki/modules/nested/Rogue.md",
        **kwargs,
    )

    assert bare["outcome"] == "blocked"
    assert bare["reason"] == "target_mismatch"
    assert routed["outcome"] == "allowed"
    assert routed["allowed_by"] == "current_target"


def test_centralized_target_and_operator_stay_in_the_writing_partition(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    kwargs = {
        "doc_path": output / "wiki/modules/a/Core.md",
        "filename": "Core.md",
        "page_type": "module",
        "module_repo": "a",
        "tool": "write_doc_file",
    }

    pending = evaluate_page_write(plan, output, mode="enforce", **kwargs)
    wrong_target = evaluate_page_write(
        plan,
        output,
        mode="enforce",
        target="wiki/modules/b/Rogue.md",
        **{**kwargs, "doc_path": output / "wiki/modules/a/Rogue.md", "filename": "Rogue.md"},
    )
    other_partition = evaluate_page_write(
        plan,
        output,
        mode="enforce",
        **{**kwargs, "doc_path": output / "wiki/modules/b/Core.md"},
    )

    assert pending["classification"] == "pending"
    assert wrong_target["reason"] == "target_mismatch"
    assert other_partition["classification"] == "unplanned"
    assert other_partition["outcome"] == "blocked"


def test_done_operator_is_planned_but_not_pending(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    kwargs = {
        "doc_path": output / "wiki/modules/Done.md",
        "filename": "Done.md",
        "page_type": "module",
        "tool": "edit_doc_file",
    }

    blocked = evaluate_page_write(plan, output, mode="enforce", **kwargs)
    assert blocked["classification"] == "planned_not_pending"
    assert blocked["outcome"] == "blocked"
    assert blocked["unplanned_write"] is False

    targeted = evaluate_page_write(plan, output, mode="enforce", target="Done.md", **kwargs)
    assert targeted["outcome"] == "allowed"
    assert targeted["allowed_by"] == "current_target"


def test_current_target_does_not_override_delete_operator(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    decision = evaluate_page_write(
        cp.load_plan(repo, output),
        output,
        doc_path=output / "wiki/modules/Gone.md",
        filename="Gone.md",
        page_type="module",
        mode="enforce",
        target="Gone.md",
        tool="write_doc_file",
    )

    assert decision["classification"] == "delete_only"
    assert decision["outcome"] == "blocked"
    assert decision["allowed_by"] is None


def test_failed_and_skipped_operators_are_pending_for_write_guard(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    for op in plan["ops"]:
        if op["page"] == "Core":
            op["status"] = "failed"
        elif op["page"] == "overview":
            op["status"] = "skipped"

    for filename, page_type in (("Core.md", "module"), ("overview.md", "module")):
        decision = evaluate_page_write(
            plan,
            output,
            doc_path=output
            / ("wiki/overview.md" if filename == "overview.md" else f"wiki/modules/{filename}"),
            filename=filename,
            page_type=page_type,
            mode="enforce",
            tool="write_doc_file",
        )
        assert decision["classification"] == "pending"
        assert decision["outcome"] == "allowed"


def test_centralized_module_partition_matches_by_module_stem(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    decision = evaluate_page_write(
        cp.load_plan(repo, output),
        output,
        doc_path=output / "wiki/modules/member/Core.md",
        filename="Core.md",
        page_type="module",
        module_repo="member",
        mode="enforce",
        tool="write_doc_file",
    )

    assert decision["classification"] == "pending"
    assert decision["outcome"] == "allowed"


def test_update_page_key_disambiguates_same_stem_in_shared_pool(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"] = [
        {
            "op_id": "update_page:wiki/queries/Core.md",
            "op": "update_page",
            "page": "Core",
            "page_key": "wiki/queries/Core.md",
            "status": "pending",
        }
    ]
    plan["plan_hash"] = cp.compute_plan_hash(plan)

    module = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/Core.md",
        filename="Core.md",
        page_type="module",
        mode="enforce",
        tool="write_doc_file",
    )
    query = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/queries/Core.md",
        filename="Core.md",
        page_type="query",
        mode="enforce",
        tool="write_doc_file",
    )

    assert module["classification"] == "unplanned"
    assert query["classification"] == "pending"


def test_legacy_update_requires_unique_shared_page_match(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    legacy_op = {
        "op_id": "update_page:Core",
        "op": "update_page",
        "page": "Core",
        "status": "pending",
    }
    plan["ops"] = [legacy_op]
    plan["plan_hash"] = cp.compute_plan_hash(plan)

    def decision():
        return evaluate_page_write(
            plan,
            output,
            doc_path=output / "wiki/queries/Core.md",
            filename="Core.md",
            page_type="query",
            mode="enforce",
            tool="write_doc_file",
        )

    assert decision()["classification"] == "pending"
    plan["ops"].append({**legacy_op, "op_id": "update_page:Core:2"})
    plan["plan_hash"] = cp.compute_plan_hash(plan)
    ambiguous = decision()
    assert ambiguous["classification"] == "unplanned"
    assert ambiguous["outcome"] == "blocked"


def test_unplanned_same_stem_write_does_not_settle_another_page(tmp_path):
    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"] = [
        {
            "op_id": "update_page:wiki/queries/Core.md",
            "op": "update_page",
            "page": "Core",
            "page_key": "wiki/queries/Core.md",
            "status": "pending",
        }
    ]
    plan["plan_hash"] = cp.compute_plan_hash(plan)
    cp.write_plan(repo, output, plan)

    result = _write(repo, "Core.md")

    assert result["write_guard"]["classification"] == "unplanned"
    stored = cp.load_plan(repo, output)
    assert stored["ops"][0]["status"] == "pending"


def test_recreating_delete_only_page_does_not_settle_delete(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(repo, "Gone.md")

    assert result["status"] == "created"
    stored = cp.load_plan(repo, output)
    gone = next(op for op in stored["ops"] if op["page"] == "Gone")
    assert gone["status"] == "pending"


def test_explicit_query_path_cannot_borrow_pending_module_operator(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(
        repo,
        "wiki/queries/Core.md",
        page_type="module",
        write_guard_mode="enforce",
    )

    assert "error" in result
    assert result["write_guard"]["classification"] == "unplanned"
    stored = cp.load_plan(repo, output)
    core = next(op for op in stored["ops"] if op["page"] == "Core")
    assert core["status"] == "pending"


def test_query_write_without_page_key_does_not_settle_structural_operator(tmp_path):
    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"] = [
        {
            "op_id": "add_subtree:Core",
            "op": "add_subtree",
            "page": "Core",
            "path": ["Core"],
            "status": "pending",
        }
    ]
    plan["plan_hash"] = cp.compute_plan_hash(plan)
    cp.write_plan(repo, output, plan)

    result = _write(repo, "Core.md", page_type="query")

    assert result["write_guard"]["classification"] == "unplanned"
    assert cp.load_plan(repo, output)["ops"][0]["status"] == "pending"


@pytest.mark.parametrize(
    ("field", "value"),
    [("op", "bogus"), ("status", "running")],
)
def test_malformed_operator_fails_closed(tmp_path, field, value):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"][0][field] = value
    decision = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/Core.md",
        filename="Core.md",
        page_type="module",
        mode="enforce",
        tool="write_doc_file",
    )

    assert decision["plan_status"] == "missing"
    assert decision["classification"] == "unavailable"
    assert decision["outcome"] == "blocked"


def test_centralized_edit_does_not_fall_back_to_another_repo_partition(tmp_path):
    from codewiki.mcp.tools import workspace_bootstrap as wb
    from codewiki.mcp.tools import workspace_layout as wl

    wl.clear_cache()
    try:
        ws = tmp_path / "ws"
        ws.mkdir()
        json.loads(wb.handle_init_workspace({"workspace_path": str(ws), "layout": "centralized"}))
        for name in ("a", "b"):
            (ws / name).mkdir()
            json.loads(
                wb.handle_add_workspace_repo(
                    {
                        "workspace_path": str(ws),
                        "url": f"https://example.com/{name}.git",
                        "clone": False,
                    }
                )
            )
        output = ws / "repowiki"
        cp.write_plan(ws / "a", output, _plan())
        other_page = output / "wiki/modules/b/Core.md"
        other_page.parent.mkdir(parents=True, exist_ok=True)
        other_page.write_text("# Core\n\nother repo\n", encoding="utf-8")

        result = json.loads(
            asyncio.run(
                handle_edit_doc_file(
                    {
                        "repo_path": str(ws / "a"),
                        "filename": "Core.md",
                        "command": "str_replace",
                        "old_string": "other repo",
                        "new_string": "changed",
                        "write_guard_mode": "enforce",
                    },
                    None,
                )
            )
        )

        assert "error" in result
        assert other_page.read_text(encoding="utf-8") == "# Core\n\nother repo\n"
        core = next(op for op in cp.load_plan(ws / "a", output)["ops"] if op["page"] == "Core")
        assert core["status"] == "pending"
    finally:
        wl.clear_cache()


def test_basename_fallback_rejects_symlink_escape(tmp_path):
    repo, output = _repo(tmp_path)
    outside = output.parent / "outside.md"
    outside.write_text("keep\n", encoding="utf-8")
    query = output / "wiki/queries/Link.md"
    query.parent.mkdir(parents=True)
    try:
        query.symlink_to(outside)
    except OSError:
        pytest.skip("symlink unavailable")

    result = json.loads(
        asyncio.run(
            handle_edit_doc_file(
                {
                    "repo_path": str(repo),
                    "filename": "Link.md",
                    "command": "str_replace",
                    "old_string": "keep",
                    "new_string": "changed",
                    "write_guard_mode": "enforce",
                },
                None,
            )
        )
    )

    assert result["error"] == "Filename escapes output directory."
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_missing_plan_observe_is_compatible_but_enforce_fails_closed(tmp_path):
    repo, output = _repo(tmp_path, with_plan=False)

    observed = _write(repo, "Core.md")
    assert observed["status"] == "created"
    assert observed["write_guard"]["plan_status"] == "missing"
    assert observed["write_guard"]["outcome"] == "allowed"
    assert "warning" not in observed

    blocked = _write(repo, "Other.md", write_guard_mode="enforce")
    assert "error" in blocked
    assert blocked["write_guard"]["reason"] == "change_plan_unavailable"
    assert not (output / "wiki/modules/Other.md").exists()


def test_corrupt_plan_observe_is_compatible_but_enforce_fails_closed(tmp_path):
    repo, output = _repo(tmp_path)
    cp.plan_path(repo, output).write_text("{not json", encoding="utf-8")

    observed = _write(repo, "Core.md")
    assert observed["status"] == "created"
    assert observed["write_guard"]["plan_status"] == "missing"

    blocked = _write(repo, "Other.md", write_guard_mode="enforce")
    assert "error" in blocked
    assert blocked["write_guard"]["outcome"] == "blocked"


def test_edit_undo_is_guarded_before_history_is_mutated(tmp_path):
    repo, output = _repo(tmp_path)
    page = output / "wiki/modules/Rogue.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# Rogue\n\ncurrent\n", encoding="utf-8")
    _save_history(str(output), page, "# Rogue\n\nold\n")
    history_path = output / ".meta/edit_history.json"
    before = history_path.read_text(encoding="utf-8")

    result = json.loads(
        asyncio.run(
            handle_edit_doc_file(
                {
                    "repo_path": str(repo),
                    "filename": "Rogue.md",
                    "command": "undo",
                    "write_guard_mode": "enforce",
                },
                None,
            )
        )
    )

    assert "error" in result
    assert page.read_text(encoding="utf-8") == "# Rogue\n\ncurrent\n"
    assert history_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("mode", ["observe", "enforce"])
def test_parent_traversal_is_rejected_before_plan_guard(tmp_path, mode):
    repo, output = _repo(tmp_path)
    outside = output.parent / "outside.md"

    result = _write(repo, "../../../../outside.md", write_guard_mode=mode)

    assert result["error"] == "Filename escapes output directory."
    assert not outside.exists()
    assert _events(output) == []


@pytest.mark.parametrize("mode", ["observe", "enforce"])
def test_symlink_escape_is_rejected_before_plan_guard(tmp_path, mode):
    repo, output = _repo(tmp_path)
    modules = output / "wiki/modules"
    modules.mkdir(parents=True)
    outside = output.parent / "outside.md"
    outside.write_text("keep\n", encoding="utf-8")
    link = modules / "Link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink unavailable")

    result = _write(repo, "wiki/modules/Link.md", write_guard_mode=mode)

    assert result["error"] == "Filename escapes output directory."
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert _events(output) == []


def test_unplanned_audit_does_not_change_plan_hash_and_survives_settle(tmp_path):
    repo, output = _repo(tmp_path)
    before = cp.load_plan(repo, output)["plan_hash"]

    _write(repo, "Rogue.md")
    cp.mark_op_done(repo, output, "Core.md")

    stored = cp.load_plan(repo, output)
    assert stored["plan_hash"] == before
    assert len(stored["write_guard"]["unplanned_writes"]) == 1


def test_structural_operator_page_key_cannot_authorize_another_page_type(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"][0]["page_key"] = "wiki/queries/Core.md"
    plan["plan_hash"] = cp.compute_plan_hash(plan)

    decision = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/Core.md",
        filename="Core.md",
        page_type="module",
        mode="enforce",
        tool="write_doc_file",
    )

    assert decision["classification"] == "unplanned"
    assert decision["outcome"] == "blocked"


def test_centralized_exact_target_cannot_authorize_another_partition(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"][0]["status"] = "done"
    plan["plan_hash"] = cp.compute_plan_hash(plan)

    decision = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/a/Core.md",
        filename="Core.md",
        page_type="module",
        module_repo="a",
        mode="enforce",
        target="wiki/modules/b/Core.md",
        tool="write_doc_file",
    )

    assert decision["outcome"] == "blocked"
    assert decision["reason"] == "target_mismatch"


def test_null_page_key_is_valid_and_keeps_legacy_module_operator_pending(tmp_path):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"][0]["page_key"] = None
    plan["plan_hash"] = cp.compute_plan_hash(plan)

    decision = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/Core.md",
        filename="Core.md",
        page_type="module",
        mode="enforce",
        tool="write_doc_file",
    )

    assert decision["plan_status"] == "loaded"
    assert decision["classification"] == "pending"
    assert decision["outcome"] == "allowed"


@pytest.mark.parametrize("mutation", ["missing_hash", "wrong_hash", "wrong_schema"])
def test_invalid_plan_identity_fails_closed_in_enforce(tmp_path, mutation):
    from codewiki.mcp.tools.write_guard import evaluate_page_write

    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    if mutation == "missing_hash":
        del plan["plan_hash"]
    elif mutation == "wrong_hash":
        plan["plan_hash"] = "sha256:tampered"
    else:
        plan["schema_version"] = 2

    decision = evaluate_page_write(
        plan,
        output,
        doc_path=output / "wiki/modules/Core.md",
        filename="Core.md",
        page_type="module",
        mode="enforce",
        tool="write_doc_file",
    )

    assert decision["plan_status"] == "missing"
    assert decision["classification"] == "unavailable"
    assert decision["outcome"] == "blocked"


def test_audit_failure_does_not_replace_enforce_decision(tmp_path, monkeypatch):
    repo, output = _repo(tmp_path)

    def fail_save(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(cp, "_save", fail_save)
    result = _write(repo, "Rogue.md", write_guard_mode="enforce")

    assert "error" in result
    assert result["write_guard"]["outcome"] == "blocked"
    assert not (output / "wiki/modules/Rogue.md").exists()


def test_mark_op_done_does_not_settle_case_mismatch_or_nested_same_stem(tmp_path):
    repo, output = _repo(tmp_path)

    assert cp.mark_op_done(repo, output, "core.md", page_key="wiki/modules/core.md") is None
    assert cp.mark_op_done(repo, output, "Core.md", page_key="wiki/modules/nested/Core.md") is None
    assert (
        next(op for op in cp.load_plan(repo, output)["ops"] if op["page"] == "Core")["status"]
        == "pending"
    )


def test_mark_op_done_requires_current_centralized_partition_for_legacy_operator(tmp_path):
    repo, output = _repo(tmp_path)

    assert (
        cp.mark_op_done(
            repo,
            output,
            "Core.md",
            page_key="wiki/modules/b/Core.md",
            module_repo="a",
        )
        is None
    )
    summary = cp.mark_op_done(
        repo,
        output,
        "Core.md",
        page_key="wiki/modules/a/Core.md",
        module_repo="a",
    )
    assert summary is not None
    assert "Core" not in summary["pending_pages"]


def test_mark_op_done_rejects_other_partition_even_with_matching_page_key(tmp_path):
    repo, output = _repo(tmp_path)
    plan = cp.load_plan(repo, output)
    plan["ops"][0]["op"] = "replan_subtree"
    plan["ops"][0]["page_key"] = "wiki/modules/b/Core.md"
    plan["plan_hash"] = cp.compute_plan_hash(plan)
    cp.write_plan(repo, output, plan)

    assert (
        cp.mark_op_done(
            repo,
            output,
            "Core.md",
            page_key="wiki/modules/b/Core.md",
            module_repo="a",
        )
        is None
    )
    core = next(op for op in cp.load_plan(repo, output)["ops"] if op["page"] == "Core")
    assert core["status"] == "pending"


def test_unplanned_query_does_not_close_same_stem_module_job(tmp_path):
    from codewiki.mcp.tools import job_state

    repo, output = _repo(tmp_path, with_plan=False)
    job_state.start_job(repo, output)
    job_state.record_planned(repo, output, ["Core"])

    result = _write(repo, "Core.md", page_type="query")

    assert result["status"] == "created"
    job = job_state.load_job(repo, output)
    assert job["pages"]["written"] == 0
    assert job["pages"]["other_written"] == 1
    assert job_state.missing_pages(job) == ["Core"]


def test_execute_deletions_rejects_legacy_cross_partition_target(tmp_path):
    from codewiki.mcp.tools import workspace_bootstrap as wb
    from codewiki.mcp.tools import workspace_layout as wl

    wl.clear_cache()
    try:
        ws = tmp_path / "ws"
        ws.mkdir()
        json.loads(wb.handle_init_workspace({"workspace_path": str(ws), "layout": "centralized"}))
        for name in ("a", "b"):
            (ws / name).mkdir()
            json.loads(
                wb.handle_add_workspace_repo(
                    {
                        "workspace_path": str(ws),
                        "url": f"https://example.com/{name}.git",
                        "clone": False,
                    }
                )
            )
        output = ws / "repowiki"
        other = output / "wiki/modules/b/Core.md"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("# Core\n\nkeep\n", encoding="utf-8")
        plan = _plan()
        plan["ops"] = [
            {
                "op_id": "delete_subtree:Core",
                "op": "delete_subtree",
                "page": "Core",
                "path": ["Core"],
                "page_key": "wiki/modules/b/Core.md",
                "status": "pending",
            }
        ]
        plan["plan_hash"] = cp.compute_plan_hash(plan)
        cp.write_plan(ws / "a", output, plan)

        assert cp.execute_deletions(ws / "a", output) == []
        assert other.read_text(encoding="utf-8") == "# Core\n\nkeep\n"
        deleted = cp.load_plan(ws / "a", output)["ops"][0]
        assert deleted["status"] == "failed"
    finally:
        wl.clear_cache()


def test_invalid_guard_mode_is_rejected(tmp_path):
    repo, output = _repo(tmp_path)

    result = _write(repo, "Core.md", write_guard_mode="allow-all")

    assert "error" in result
    assert "write_guard_mode" in result["error"]
    assert not (output / "wiki/modules/Core.md").exists()
