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
is waiting on stdout. It is therefore deliberately lightweight: it reads at
most two small JSON files (task index + raw capture index) and prints one JSON
line, and never imports the ``codewiki`` package (no import-path dance, fast
startup, no risk of a slow import blocking the IDE).

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


def _count_pending_raws(repo_path: str) -> dict:
    """Count un-distilled raw captures grouped by task_id.

    Reads ``repowiki/raw/.index.json`` (maintained by capture_conversation,
    shape ``{"files": [{"relpath", "status", "task_id", ...}]}``): entries
    whose status is not "distilled" form the distillation backlog. If the index
    is missing, falls back to a lightweight frontmatter peek of conv-*.md.
    Any failure returns {} so the hook degrades silently to its previous
    behaviour (never breaks task binding). Stays stdlib-only and O(entries).
    """
    counts: dict = {}
    try:
        raw_dir = Path(repo_path) / "repowiki" / "raw"
        idx_path = raw_dir / ".index.json"
        if idx_path.is_file():
            data = json.loads(idx_path.read_text(encoding="utf-8-sig", errors="replace"))
            files = data.get("files", []) if isinstance(data, dict) else []
            for e in files:
                if not isinstance(e, dict):
                    continue
                if str(e.get("status") or "pending") == "distilled":
                    continue
                rel = str(e.get("relpath") or "")
                if not rel or not (raw_dir / rel).is_file():
                    continue  # stale index entry — the file is gone
                task_id = str(e.get("task_id") or "")
                counts[task_id] = counts.get(task_id, 0) + 1
            return counts
        # Fallback: no index — peek frontmatter of each raw capture.
        for p in sorted(raw_dir.glob("conv-*.md")):
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            status, task_id = "pending", ""
            for line in text.splitlines():
                if line.startswith("status:"):
                    status = line[len("status:"):].strip().strip("\"'")
                elif line.startswith("task_id:"):
                    task_id = line[len("task_id:"):].strip().strip("\"'")
            if status != "distilled":
                counts[task_id] = counts.get(task_id, 0) + 1
    except Exception:
        return {}
    return counts


def _latest_friction_hint(repo_path: str) -> str:
    """Scan the most recent pending raw capture for a high friction score.

    K-line (摩擦信号触发机制): a session that showed friction (corrections /
    interrupts / repeats) is the most likely to hold a worth-distilling lesson.
    When the newest pending ``conv-*.md`` carries ``friction_score: >= 20``,
    return a one-line Chinese hint recommending catch-up distillation first.
    Returns "" otherwise. stdlib-only line scanning (same convention as the
    ``status:``/``task_id:`` keys); every failure degrades silently.
    """
    try:
        raw_dir = Path(repo_path) / "repowiki" / "raw"
        if not raw_dir.is_dir():
            return ""
        # Most recent first (mtime): the last session is the relevant one.
        files = [p for p in raw_dir.glob("conv-*.md") if p.is_file()]
        if not files:
            return ""
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:5]:  # bounded scan: only the newest few captures
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            score = None
            status = "pending"
            correction = None
            for line in text.splitlines():
                if line.startswith("friction_score:"):
                    try:
                        score = int(line[len("friction_score:"):].strip())
                    except ValueError:
                        score = None
                elif line.startswith("status:"):
                    status = line[len("status:"):].strip().strip("\"'")
                elif line.startswith("friction_signals:"):
                    for part in line[len("friction_signals:"):].split(","):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "correction":
                            try:
                                correction = int(kv[1].strip())
                            except ValueError:
                                pass
            if score is None or status == "distilled":
                continue
            if score >= 20:
                corr = f"（纠正 {correction} 次）" if correction is not None else ""
                return (
                    f"[codewiki] 上次会话摩擦分 {score}{corr}，"
                    "建议优先委托蒸馏 worker subagent 补蒸馏（不阻塞本次工作）"
                )
            return ""  # newest pending capture is calm — don't disturb
    except Exception:
        return ""
    return ""


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
        "本会话的第一个动作都必须是下面这个任务关联弹框流程；弹框、绑定、拉取上下文完成后，"
        "才允许开始读文件/搜索代码/回答用户提问（有积压时补蒸馏委托 subagent 后台执行，"
        "见下方「补蒸馏」段落，不阻塞回答）。严禁先探索代码或直接回答，事后再补弹任务关联框。"
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
        "返回中的 pending_raw_count 是本任务尚未蒸馏的历史对话数：若大于 0，按下方"
        "「补蒸馏」委托蒸馏 subagent 后台执行（无需等待，直接开始回答用户提问）。"
        "若用户明确表示本次会话与任何任务无关，可跳过本提示。"
    )

    # Catch-up distillation backlog: deterministic trigger so agents that never
    # "think to" distill still clear the backlog at session start.
    pending_counts = _count_pending_raws(repo_path)
    if pending_counts:
        total = sum(pending_counts.values())
        lines.append("")
        lines.append(f"【补蒸馏】检测到 {total} 条未蒸馏的历史对话积压：")
        for tid, n in sorted(pending_counts.items()):
            label = f"任务 {tid}" if tid else "未关联任务"
            lines.append(f"  - {label}: {n} 条")
        lines.append(
            "绑定任务之后，立即用 Task 工具 spawn「蒸馏 worker」subagent "
            "（.codebuddy/agents/distill-worker.md，已授权 codewiki MCP）后台执行补蒸馏；"
            "主 Agent 不要亲自 read_file raw 原文、也不等蒸馏完成，直接开始回答用户提问。"
            "蒸馏 worker 走 Mode C（纯 MCP JSON）流程："
        )
        lines.append(
            "  1. distill_conversation(mode=\"prepare\", task_id=<绑定的任务id>) "
            "获取该任务的积压对话清单"
        )
        lines.append(
            "  2. 按清单逐条 read_file 阅读 raw 文件，提取 notes（通用经验）与 memories（任务进度）"
        )
        lines.append(
            "  3. distill_conversation(mode=\"submit\", distilled=<提取结果>) 提交；"
            "产出为草稿笔记与待确认记忆"
        )
        lines.append(
            "  4. 蒸馏完成后，主 Agent 在自然停顿点（任务告一段落/用户空闲时）重新 "
            "get_task_context 拉取最新上下文（新产出的待确认记忆/草稿笔记会一并注入）"
        )
        lines.append(
            "  5. 向用户展示待确认项，经 confirm_task_memories / confirm_note 确认后才正式落盘"
        )
        lines.append(
            "若用户明确表示紧急，可先回答提问，蒸馏结果在会话结束前展示确认即可。"
            "注意：pending 记忆与 draft 笔记在确认前只能作为只读参考，不得当作已定论的结论引用。"
        )

    # K-line: the newest pending capture showed friction (score >= 20) —
    # surface a one-line hint so the agent prioritises catch-up distillation.
    friction_hint = _latest_friction_hint(repo_path)
    if friction_hint:
        lines.append("")
        lines.append(friction_hint)

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
