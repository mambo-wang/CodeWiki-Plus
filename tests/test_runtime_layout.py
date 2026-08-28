"""Tests for ticket 07: runtime data lands at the workspace root under
centralized layouts.

Tasks / raw captures / conversations are workspace-scale; they must live in
the shared area at the workspace repowiki root, never sharded per repo.
Format semantics (markdown memories, timestamped headings, atomic appends —
ADR-0001/0002) must stay byte-compatible; only the root moves.
"""

from __future__ import annotations

import json

import pytest

from codewiki.mcp.tools import task_manager as tm
from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl

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


# ---------------------------------------------------------------------------
# Resolution units
# ---------------------------------------------------------------------------
class TestRuntimeResolution:
    def test_capture_resolution_centralized_member(self, tmp_path):
        from codewiki.mcp.tools.capture_conversation import _resolve_output_dir

        ws = _init_centralized(tmp_path)
        od = _resolve_output_dir(None, {"repo_path": str(ws / "a")})
        assert od == ws / "repowiki"

    def test_capture_resolution_single_repo_status_quo(self, tmp_path):
        from codewiki.mcp.tools.capture_conversation import _resolve_output_dir

        repo = tmp_path / "solo"
        repo.mkdir()
        od = _resolve_output_dir(None, {"repo_path": str(repo)})
        assert od == repo / "repowiki"


# ---------------------------------------------------------------------------
# Conversation capture
# ---------------------------------------------------------------------------
_TURNS = [
    {"role": "user", "content": "为什么构建失败？"},
    {"role": "assistant", "content": "依赖版本冲突，已锁定版本。"},
]


class TestCaptureCentralized:
    def test_raw_lands_at_workspace_root(self, tmp_path):
        from codewiki.mcp.tools.capture_conversation import handle_capture_conversation

        ws = _init_centralized(tmp_path)
        res = json.loads(
            handle_capture_conversation(
                {
                    "repo_path": str(ws / "a"),
                    "conversation": _TURNS,
                    "source_session_id": "sess-1",
                },
                _StubStore(),
            )
        )
        assert res.get("status") in ("captured", "superseded")
        raw_files = list((ws / "repowiki" / "raw").glob("conv-*.md"))
        assert len(raw_files) == 1
        # Business repo stays pure code — no in-repo repowiki.
        assert not (ws / "a" / "repowiki").exists()

    def test_capture_colocated_status_quo(self, tmp_path):
        from codewiki.mcp.tools.capture_conversation import handle_capture_conversation

        repo = tmp_path / "solo"
        repo.mkdir()
        res = json.loads(
            handle_capture_conversation(
                {
                    "repo_path": str(repo),
                    "conversation": _TURNS,
                    "source_session_id": "sess-2",
                },
                _StubStore(),
            )
        )
        assert res.get("status") in ("captured", "superseded")
        assert list((repo / "repowiki" / "raw").glob("conv-*.md"))


# ---------------------------------------------------------------------------
# Task memory workflow
# ---------------------------------------------------------------------------
class TestTaskMemoryCentralized:
    def test_full_workflow_at_workspace_root(self, tmp_path):
        ws = _init_centralized(tmp_path)
        repo_arg = {"repo_path": str(ws / "a")}

        created = json.loads(
            tm.handle_create_task({**repo_arg, "title": "实现集中式路由"}, _StubStore())
        )
        assert created["ok"] is True
        task_id = created["task"]["id"]

        # tasks/ index lives at the workspace root, not in the business repo
        assert (ws / "repowiki" / "tasks" / ".index.json").is_file()
        assert not (ws / "a" / "repowiki").exists()

        m1 = json.loads(
            tm.handle_add_task_memory(
                {**repo_arg, "task_id": task_id, "content": "完成 workspace_layout 模块"},
                _StubStore(),
            )
        )
        assert m1["ok"] is True

        ctx = json.loads(tm.handle_get_task_context({**repo_arg, "task_id": task_id}, _StubStore()))
        memories_blob = json.dumps(ctx, ensure_ascii=False)
        assert "完成 workspace_layout 模块" in memories_blob

        # ADR-0001: memories stay markdown with timestamped headings in the
        # per-user file (format unchanged — only the root moved).
        task_dir = ws / "repowiki" / "tasks" / task_id
        mem_files = list((task_dir / "memories").glob("*.md"))
        assert mem_files, "per-user memories file expected"
        content = mem_files[0].read_text(encoding="utf-8")
        assert "### " in content  # timestamped heading is the parsing boundary
        assert "完成 workspace_layout 模块" in content

    def test_task_workflow_colocated_status_quo(self, tmp_path):
        repo = tmp_path / "solo"
        repo.mkdir()
        repo_arg = {"repo_path": str(repo)}
        created = json.loads(tm.handle_create_task({**repo_arg, "title": "普通任务"}, _StubStore()))
        assert created["ok"] is True
        assert (repo / "repowiki" / "tasks" / ".index.json").is_file()
