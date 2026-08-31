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
