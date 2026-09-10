"""Tests for the SessionStart task hook (codewiki/hooks/task_session_start.py).

The hook is exercised the same way CodeBuddy runs it: as a subprocess with the
event JSON on stdin, reading the ``{continue, hookSpecificOutput}`` JSON from
stdout. The repo root is forced via CODEBUDDY_PROJECT_DIR so the hook reads a
crafted tmp repo instead of the real one.

Covered:
  - backlog present  -> additionalContext carries the catch-up distillation
    instruction with per-task counts;
  - no backlog       -> no catch-up section (don't disturb);
  - corrupt index    -> silent degradation, still valid output;
  - missing index    -> frontmatter fallback still counts the backlog.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "codewiki" / "hooks" / "task_session_start.py"

EVENT = json.dumps(
    {
        "session_id": "test-session",
        "cwd": "/",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
)


def _run_hook(repo: Path, hook: Path = HOOK) -> dict:
    env = dict(os.environ)
    env["CODEBUDDY_PROJECT_DIR"] = str(repo)
    # Deterministic UTF-8 stdout regardless of the Windows console code page.
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=EVENT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, f"hook failed: {proc.stderr}"
    return json.loads(proc.stdout)


def _context(out: dict) -> str:
    assert out["continue"] is True
    return out["hookSpecificOutput"]["additionalContext"]


def _write_raw_index(repo: Path, entries: list) -> None:
    raw_dir = repo / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".index.json").write_text(
        json.dumps({"files": entries}, ensure_ascii=False), encoding="utf-8"
    )


def _write_raw_file(repo: Path, name: str, task_id: str, status: str = "pending") -> None:
    raw_dir = repo / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_text(
        f'---\nstatus: {status}\ntask_id: "{task_id}"\n---\n\nuser: hi', encoding="utf-8"
    )


def test_backlog_injects_catchup_instruction(tmp_path):
    # Two pending captures for task-one, one distilled (ignored), one unbound.
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    _write_raw_file(tmp_path, "conv-b.md", "task-one")
    _write_raw_file(tmp_path, "conv-c.md", "task-two", status="distilled")
    _write_raw_file(tmp_path, "conv-d.md", "")
    _write_raw_index(
        tmp_path,
        [
            {"relpath": "conv-a.md", "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-b.md", "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-c.md", "status": "distilled", "task_id": "task-two"},
            {"relpath": "conv-d.md", "status": "pending", "task_id": ""},
            # Stale entry: file no longer exists — must not be counted.
            {"relpath": "conv-gone.md", "status": "pending", "task_id": "task-one"},
        ],
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" in ctx
    assert "3 条" in ctx  # 2 x task-one + 1 unbound
    assert "任务 task-one: 2 条" in ctx
    assert "未关联任务: 1 条" in ctx
    # Distillation is delegated to a subagent, not run inline by the main agent.
    assert "蒸馏 worker" in ctx
    assert "distill-worker.md" in ctx
    assert "不阻塞回答" in ctx
    assert "自然停顿点" in ctx
    assert 'distill_conversation(mode="prepare", task_id=<绑定的任务id>)' in ctx
    # ADR-0002: task memories are direct-written by distillation — only the
    # note draft gate remains in the injected instructions.
    assert "confirm_note" in ctx
    assert "confirm_task_memories" not in ctx


def test_no_backlog_no_catchup_section(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one", status="distilled")
    _write_raw_index(
        tmp_path,
        [
            {"relpath": "conv-a.md", "status": "distilled", "task_id": "task-one"},
        ],
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" not in ctx
    # Base task-binding guidance is still present.
    assert "ask_followup_question" in ctx


def test_corrupt_index_degrades_silently(tmp_path):
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".index.json").write_text("{not valid json", encoding="utf-8")

    out = _run_hook(tmp_path)  # must not raise / must stay valid JSON
    ctx = _context(out)
    assert "【补蒸馏】" not in ctx
    assert "ask_followup_question" in ctx


def test_missing_index_falls_back_to_frontmatter(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    _write_raw_file(tmp_path, "conv-b.md", "task-one", status="distilled")
    # No .index.json at all.

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" in ctx
    assert "任务 task-one: 1 条" in ctx


def test_doctrine_injected_when_present(tmp_path):
    wiki = tmp_path / "repowiki" / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "doctrine.md").write_text(
        "---\ntype: Doctrine\nstatus: stable\n---\n\n## Operating Thesis\n\nWrite deep modules.\n",
        encoding="utf-8",
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【项目定向】" in ctx
    assert "Write deep modules." in ctx
    # Frontmatter noise is stripped, doctrine rides on the same hard channel.
    assert "type: Doctrine" not in ctx


def test_doctrine_absent_no_section(tmp_path):
    ctx = _context(_run_hook(tmp_path))
    assert "【项目定向】" not in ctx


# ---------------------------------------------------------------------------
# P2-2 (claude-mem borrowing, thin): knowledge-base overview — the KB's
# existence and the cheapest retrieval entries surface before work starts.
# ---------------------------------------------------------------------------


def test_knowledge_overview_injected_when_notes_present(tmp_path):
    notes = tmp_path / "repowiki" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    for name in ("2026-08-01-old.md", "2026-08-20-newer.md", "2026-09-01-newest.md"):
        (notes / name).write_text("---\ntype: lesson\n---\nbody", encoding="utf-8")

    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" in ctx
    assert "3 条笔记" in ctx
    # newest-first: the newest filename rides along
    assert "2026-09-01-newest" in ctx
    # retrieval strategy pointers (P0-3's call-time channel, mirrored here)
    assert "by_file" in ctx
    assert "mode='check'" in ctx


def test_knowledge_overview_absent_when_no_notes(tmp_path):
    # repowiki exists but notes/ empty → no section (don't disturb)
    (tmp_path / "repowiki").mkdir(parents=True, exist_ok=True)
    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" not in ctx


def test_knowledge_overview_absent_when_no_repowiki(tmp_path):
    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" not in ctx


# ---------------------------------------------------------------------------
# 补蒸馏委托按宿主家族分支：claude 家族自定义子代理拿不到 MCP 权限（实测），
# 改委托内置 general-purpose 子代理；CodeBuddy 保留自定义「蒸馏 worker」。
# ---------------------------------------------------------------------------


def test_qoder_copy_delegates_to_general_purpose(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    hook = tmp_path / ".qoder" / "hooks" / "task_session_start.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)

    ctx = _context(_run_hook(tmp_path, hook=hook))
    assert "【补蒸馏】" in ctx
    assert "general-purpose" in ctx
    assert ".qoder/agents/distill-worker.md" in ctx  # host-aware playbook path
    assert "拿不到 MCP 权限" in ctx
    assert "「蒸馏 worker」subagent" not in ctx  # custom-agent wording must not leak


def test_active_tasks_listed_in_one_chooser_box(tmp_path):
    """用户反馈「任务关联经常弹多个框」：注入文案必须钉死单框 + 一框列全。

    ask_followup_question 的 schema 建议「2-4 个 options」，Agent 会照做把任务
    拆进多个 question 或分多次调用 —— 这是多框的根因。注入的硬约束必须显式
    覆盖该建议，并要求把全部 active 任务放进同一个 question 的 options。
    """
    tasks_dir = tmp_path / "repowiki" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / ".index.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "t1", "title": "任务一", "status": "active"},
                    {"id": "t2", "title": "任务二", "status": "active"},
                    {"id": "t3", "title": "已完成任务", "status": "completed"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ctx = _context(_run_hook(tmp_path))
    assert "只弹一次，一框列全" in ctx
    assert "1 次 ask_followup_question" in ctx
    assert "只放 1 个 question" in ctx
    assert "新建任务两步弹框" not in ctx  # 两步弹框是第二个框的来源，已废止为兜底

    # 全部 active 任务出现在同一个 options 清单里（已完成任务不出现）。
    options_block = ctx.split("该 question 的 options（按顺序）：")[1].split("【结果判定】")[0]
    assert "    - 任务一（task_id=t1）" in options_block
    assert "    - 任务二（task_id=t2）" in options_block
    assert "已完成任务" not in options_block
    assert "新建任务…（在输入框直接输入名称）" in options_block
    assert "跳过" in options_block


def test_codebuddy_copy_keeps_worker_delegation(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    hook = tmp_path / ".codebuddy" / "hooks" / "task_session_start.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)

    ctx = _context(_run_hook(tmp_path, hook=hook))
    assert "【补蒸馏】" in ctx
    assert "「蒸馏 worker」subagent" in ctx
    assert ".codebuddy/agents/distill-worker.md" in ctx
    assert "general-purpose" not in ctx
