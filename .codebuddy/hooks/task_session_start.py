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
    """Build the guidance injected into the fresh session.

    IMPORTANT: the user expects an interactive chooser, NOT a text paragraph.
    The message below must instruct the agent to surface the choice through the
    ``ask_followup_question`` tool (the IDE's structured-question UI), so the
    user can click an option or type a task name, exactly like a native dialog.
    """
    session_id = str(event.get("session_id") or "").strip()
    active = _load_active_tasks(repo_path)

    lines = ["[task-memory] 本会话开始前，请先处理「任务关联」（跨会话任务记忆）。"]
    lines.append("")
    lines.append(
        "【硬性执行顺序】无论用户第一条消息问什么（哪怕是关于代码、文件、bug 的具体问题），"
        "本会话的第一个动作都必须是下面这个任务关联弹框流程；弹框、绑定、拉取上下文全部完成后，"
        "才允许开始读文件/搜索代码/回答用户提问。严禁先探索代码或直接回答，事后再补弹任务关联框。"
    )
    lines.append("")
    lines.append(
        "【必须弹框】请立即调用 ask_followup_question 工具弹出结构化选择框"
        "（这是 IDE 的原生弹框 UI，用户可以直接点击选项），不要用纯文本输出一段话让用户自行回复。"
        "弹框标题用「任务关联」，提供以下选项："
    )
    if active:
        lines.append("- 关联已有任务：把下面每个进行中任务的标题作为弹框选项，用户选中后调用 "
                     f"set_session_task(source_session_id={session_id or '<当前会话id>'}, task_id=<选中任务>) 建立绑定")
        lines.append("  当前进行中的任务：")
        for t in active:
            lines.append(f"    - {t.get('title') or t.get('id')}（task_id={t.get('id')}）")
    else:
        lines.append("- 新建任务：选择后会再弹一个输入框让用户输入任务名（可补一句描述），调用 "
                     "create_task(title=<任务名>, description=<可选>) 创建后即关联该新任务")
    lines.append("- 跳过：本次会话不做任务关联，直接开始干活")
    lines.append("")
    lines.append(
        "【新建任务两步弹框】当用户选择「新建任务」后，必须再次调用 ask_followup_question "
        "弹出第二个输入框：标题用「新建任务」，问题写「请输入新任务名称」，提供 2 个占位示例选项"
        "（如「临时任务」「在输入框直接输入名称后回车」）。该弹框自带输入框，用户可自由输入任务名后回车；"
        "以用户输入的文字为准，立即调用 create_task(title=<任务名>, description=<可选>) 创建并关联该新任务。"
        "若用户只点击了占位选项，则用文字追问确认真实任务名。"
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
