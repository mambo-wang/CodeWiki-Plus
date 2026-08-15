#!/usr/bin/env python3
"""CodeBuddy SessionStart hook: inject active-task guidance into a new session.

The task-memory layer lets long-running work span sessions. This hook makes the
"pick (or create) a task" prompt *deterministic* at session start: it reads
``repowiki/tasks/.index.json`` and emits a ``hookSpecificOutput.additionalContext``
instructing the agent to ask the user which task to bind (or to create a new
one) before work begins.

This is the **source** copy of the hook, shipped inside the ``codewiki``
package. When a user enables task management, the ``team-memory-hook`` MCP
prompt copies this file into the project's ``.codebuddy/hooks/task_session_start.py``
and registers it for the ``SessionStart`` event. CodeBuddy runs the *copied*
file, not this one.

Why a SessionStart hook (not just AGENTS.md guidance):
    AGENTS.md guidance is a *soft* constraint — an agent may or may not honor
    "at session start, list tasks and ask the user". A SessionStart hook is a
    *hard* trigger: the IDE waits for this script's stdout and injects the
    returned ``additionalContext`` into the agent's context, so the task prompt is
    guaranteed to surface every time.

Unlike the SessionEnd capture hook (which fires-and-forgets via a detached
subprocess), this hook MUST return its ``systemMessage`` synchronously — the IDE
is waiting on stdout. It is therefore deliberately lightweight: it reads one
JSON file and prints one JSON line, and never imports the ``codewiki`` package
(no import-path dance, fast startup, no risk of a slow import blocking the IDE).

CodeBuddy invokes it with the event as JSON on stdin, e.g.:

    {
      "session_id": "abc123",
      "transcript_path": "/path/to/transcript.txt",
      "cwd": "/project/path",
      "hook_event_name": "SessionStart",
      "source": "startup"
    }

Stdout is emitted in the CodeBuddy-expected ``{continue, systemMessage}`` shape.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # <repo>/.codebuddy/hooks/ -> <repo>


def _read_event() -> dict:
    """Read the hook event JSON from stdin ({} when absent/unparseable)."""
    if sys.stdin.isatty():
        return {}
    try:
        # Read raw bytes and decode leniently: PowerShell pipes may prepend one
        # or more UTF-8 BOMs, which would break json.loads.
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        raw = raw.lstrip("\ufeff").strip()
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_repo_path(event: dict) -> str:
    """Resolve the repo root, preferring authoritative sources.

    Priority: CODEBUDDY_PROJECT_DIR env var (CodeBuddy-specific) >
    CLAUDE_PROJECT_DIR (compat) > event's cwd > this script's repo location.
    Candidates that don't exist on disk are skipped.
    """
    candidates = [
        os.environ.get("CODEBUDDY_PROJECT_DIR"),
        os.environ.get("CLAUDE_PROJECT_DIR"),
        event.get("cwd"),
        str(REPO),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return str(REPO)


def _load_active_tasks(repo_path: str) -> list:
    """Read repowiki/tasks/.index.json and return active (non-completed) tasks.

    Returns [] when the index is absent/corrupt (the task layer has never been
    initialized) — the caller then prompts the user to create a task instead.
    """
    idx = Path(repo_path) / "repowiki" / "tasks" / ".index.json"
    if not idx.is_file():
        return []
    try:
        data = json.loads(idx.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    return [t for t in tasks if isinstance(t, dict) and t.get("status") == "active"]


def _build_message(event: dict, repo_path: str) -> str:
    """Build the systemMessage injected into the fresh session."""
    session_id = str(event.get("session_id") or "").strip()
    active = _load_active_tasks(repo_path)

    lines = ["[task-memory] 本会话开始前，请先处理「任务关联」（跨会话任务记忆）。"]
    if active:
        lines.append("")
        lines.append("当前仓库有以下进行中的任务：")
        for t in active:
            lines.append(f"- {t.get('title')}（task_id={t.get('id')}）")
    else:
        lines.append("")
        lines.append("当前仓库暂无进行中的任务。")

    lines.append("")
    lines.append("请向用户询问，二选一：")
    lines.append(
        "1. 关联已有任务：用户从列表中选择一个，调用 "
        f"set_session_task(source_session_id={session_id or '<当前会话id>'}, task_id=<选中任务>) 建立绑定"
    )
    lines.append(
        "2. 新建任务：用户直接输入任务名（可补一句描述），调用 "
        "create_task(title=<任务名>, description=<可选>) 创建后即关联该新任务"
    )
    lines.append("")
    lines.append(
        "关联完成后调用 get_task_context(task_id=<选中任务>) 拉取该任务上下文继续工作。"
        "若用户明确表示本次会话与任何任务无关，可跳过本提示。"
    )

    return "\n".join(lines)


def main() -> int:
    event = _read_event()
    repo_path = _resolve_repo_path(event)
    message = _build_message(event, repo_path)

    # Ensure CJK task titles survive the Windows console encoding (cp936) when
    # the IDE reads our stdout.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

    # SessionStart injects extra context to the *agent* via
    # hookSpecificOutput.additionalContext. (systemMessage only surfaces to the
    # user and never reaches the agent — see the CodeBuddy hooks reference.)
    output = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        },
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
