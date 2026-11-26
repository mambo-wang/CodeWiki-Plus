#!/usr/bin/env python3
"""Cross-IDE SessionStart hook: inject active-task guidance into a new session.

The task-memory layer lets long-running work span sessions. This hook makes the
"pick (or create) a task" prompt *deterministic* at session start: it reads
``repowiki/tasks/.index.json``, existing session-task bindings, and (when the
host supplies one) the current transcript, then emits a
``hookSpecificOutput.additionalContext`` that either resumes the already-chosen
task, preserves an explicit skip, or instructs the agent to ask the user which
task to bind (or to create a new one) before work begins.

This is the **source** copy of the hook, shipped inside the ``codewiki``
package. When a user enables task management, the ``team-memory-hook`` MCP
prompt copies this file into each detected IDE's ``hooks/task_session_start.py``
and registers it for the ``SessionStart`` event. IDEs run the *copied* file,
not this one.

Why a SessionStart hook (not just AGENTS.md guidance):
    AGENTS.md guidance is a *soft* constraint — an agent may or may not honor
    "at session start, list tasks and ask the user". A SessionStart hook is a
    *hard* trigger: the IDE waits for this script's stdout and injects the
    returned ``additionalContext`` into the agent's context, so first-run task
    selection is guaranteed to surface and repeat starts reuse prior choices.

The same hard-trigger channel also injects the Team Doctrine
(``repowiki/wiki/doctrine.md``, ~3KB) into the fresh session. The doctrine is
the knowledge flywheel's aggregated consensus — cheap enough to surface up
front, and far more reliable than AGENTS.md's soft "query_wiki first" advice
(which agents routinely skip when competing with the task prompt).

Unlike the SessionEnd capture hook (which fires-and-forgets via a detached
subprocess), this hook MUST return its ``systemMessage`` synchronously — the IDE
is waiting on stdout. It is therefore deliberately lightweight: metadata reads
are small, transcript reads are byte/entry bounded and stop at the first decisive
result, and it never imports the ``codewiki`` package (no import-path dance, fast
startup, no risk of a slow import blocking the IDE).

Hosts invoke it with the event as JSON on stdin, e.g.:

    {
      "session_id": "abc123",
      "transcript_path": "/path/to/transcript.txt",
      "cwd": "/project/path",
      "hook_event_name": "SessionStart",
      "source": "startup"
    }

Stdout is emitted in the hook-expected ``{continue, hookSpecificOutput}`` shape.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # <repo>/.codebuddy/hooks/ -> <repo>
# 本副本安装所在的 IDE 配置目录名（".codebuddy"/".qoder"/…）；
# 包内源副本位于 codewiki/hooks/，取值为 "codewiki"。
IDE_DIR_NAME = Path(__file__).resolve().parents[1].name


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

    Priority: the host's *_PROJECT_DIR env var (each host injects its own:
    CODEBUDDY/QODER/GEMINI/TRAE, plus CLAUDE_PROJECT_DIR compat) > event's
    cwd > this script's repo location. Candidates that don't exist on disk
    are skipped.
    """
    candidates = [
        os.environ.get("CODEBUDDY_PROJECT_DIR"),
        os.environ.get("QODER_PROJECT_DIR"),
        os.environ.get("GEMINI_PROJECT_DIR"),
        os.environ.get("TRAE_PROJECT_DIR"),
        os.environ.get("CLAUDE_PROJECT_DIR"),
        event.get("cwd"),
        str(REPO),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return str(REPO)


# ---------------------------------------------------------------------------
# 任务清单：索引优先，缺失回退扫描 task.md
# ---------------------------------------------------------------------------


def _task_recent_ts(task_dir: Path) -> float:
    """任务目录的最近活动时间（task.md 与 memories/ 里最新的 mtime）。

    ``.index.json`` 只记 created_at；长线工作要的是「最近在推进的排前面」，否则
    最早创建的维护类任务永远占着截断后的选项位。取不到时间返回 0.0（排到最后）。
    """
    newest = 0.0
    try:
        for p in [task_dir / "task.md", *task_dir.glob("memories/*.md")]:
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
    except OSError:
        return 0.0
    return newest


def _scan_active_tasks(repo_path: str) -> list:
    """.index.json 缺席/损坏时的回退：扫 tasks/*/task.md 的 frontmatter。

    任务目录是真源，索引只是 gitignored 的本机可重建缓存——刚克隆/刚换机器的仓库
    往往没有它。不回退会让任务关联弹框列出 0 个任务，用户误以为任务层是空的。
    stdlib 逐行扫描（与 raw 回退同一口径），只读 frontmatter 内的 status/title。
    """
    tasks_dir = Path(repo_path) / "repowiki" / "tasks"
    found: list = []
    try:
        if not tasks_dir.is_dir():
            return []
        for d in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
            md = d / "task.md"
            if not md.is_file():
                continue
            try:
                lines = md.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            except OSError:
                continue
            status, title = "", d.name
            # lines[0] 是 frontmatter 的开栏 '---'，从第二行起读，遇闭栏即停
            for line in lines[1:20]:
                if line.startswith("status:"):
                    status = line[len("status:") :].strip().strip("\"'")
                elif line.startswith("title:"):
                    title = line[len("title:") :].strip().strip("\"'") or d.name
                elif line.strip() == "---":
                    break
            if status == "active":
                found.append({"id": d.name, "title": title, "recent": _task_recent_ts(d)})
    except OSError:
        return []
    return found


def _load_active_tasks(repo_path: str) -> list:
    """Return active tasks, most recently touched first.

    ``repowiki/tasks/.index.json`` is the cheap primary source; when it is
    absent or corrupt (typical right after a clone, since it is a gitignored
    rebuildable cache) this falls back to scanning ``tasks/*/task.md``
    frontmatter. Never raises — total failure yields [] and the caller then
    offers to create a task.
    """
    idx = Path(repo_path) / "repowiki" / "tasks" / ".index.json"
    tasks: list = []
    if idx.is_file():
        try:
            data = json.loads(idx.read_text(encoding="utf-8-sig", errors="replace"))
            entries = data.get("tasks", []) if isinstance(data, dict) else []
            tasks = [t for t in entries if isinstance(t, dict) and t.get("status") == "active"]
        except (OSError, json.JSONDecodeError):
            tasks = []
    if not tasks:
        tasks = _scan_active_tasks(repo_path)
    tasks_dir = Path(repo_path) / "repowiki" / "tasks"

    def recent(t: dict) -> float:
        ts = t.get("recent")
        if isinstance(ts, (int, float)):
            return float(ts)
        return _task_recent_ts(tasks_dir / str(t.get("id") or ""))

    return sorted(tasks, key=recent, reverse=True)


# ---------------------------------------------------------------------------
# 已有任务关联：同一会话重复触发 SessionStart 时不再弹框
# ---------------------------------------------------------------------------

# SessionStart 是同步 hook，不能像采集 hook 那样无界读完整 transcript。任务选择
# 通常发生在会话开头；超过上限就保守地回退到 binding/raw/弹框，不拿截断内容猜任务。
_TRANSCRIPT_MAX_BYTES = 8 * 1024 * 1024
_TRANSCRIPT_MESSAGE_MAX_BYTES = 1024 * 1024
_TRANSCRIPT_MAX_ENTRIES = 20_000
_TASK_CHOOSERS = frozenset({"askuserquestion", "askuserquestionasync", "ask_followup_question"})
_SKIP_ANSWERS = frozenset(
    {
        "跳过",
        "skip",
        "不绑定",
        "不关联",
        "不关联任务",
        "本次不做任务关联",
        "暂不关联",
        "暂不关联任务",
    }
)


def _event_session_id(event: dict) -> str:
    """读取会话 id，兼容不同宿主的字段大小写。"""
    return str(
        event.get("session_id") or event.get("sessionId") or event.get("source_session_id") or ""
    ).strip()


def _event_transcript_path(event: dict) -> str:
    """只使用当前事件显式提供的 transcript 路径。"""
    value = event.get("transcript_path") or event.get("transcriptPath") or event.get("transcript")
    return str(value).strip() if value else ""


def _read_text_bounded(path: Path, limit: int) -> str:
    """最多读取 ``limit`` 字节；超限文件按不可用处理。"""
    try:
        with path.open("rb") as fh:
            raw = fh.read(limit + 1)
    except OSError:
        return ""
    if len(raw) > limit:
        return ""
    return raw.decode("utf-8-sig", errors="replace")


def _read_json_bounded(path: Path, limit: int) -> object:
    text = _read_text_bounded(path, limit)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _safe_message_id(message_id: object) -> bool:
    value = str(message_id or "")
    return bool(
        value
        and value not in (".", "..")
        and not any(char in value for char in ("/", "\\", "\x00"))
    )


def _is_codebuddy_index(path: Path, messages: list) -> bool:
    if not messages or not (path.parent / "messages").is_dir():
        return False
    first = messages[0] if isinstance(messages[0], dict) else None
    if not first or "id" not in first:
        return False
    return not any(key in first for key in ("content", "message", "text"))


def _iter_codebuddy_entries(index_path: Path, messages: list):
    """展开 CodeBuddy 的 ``index.json + messages/*.json`` 布局，不等待 IDE 收尾。

    采集 hook 以后台方式运行，可以等 IDE 完成文件迁移；本 hook 是同步执行，
    消息文件缺失时直接跳过并回退到弹框。工具块必须保留：采集阶段会把它们压缩掉，
    但任务选择恢复需要工具调用 id 与成功/失败结果。所有消息共享一个总字节预算。
    """
    total = 0
    for meta in messages[:_TRANSCRIPT_MAX_ENTRIES]:
        if not isinstance(meta, dict):
            continue
        message_id = meta.get("id")
        if not _safe_message_id(message_id):
            continue
        message_file = index_path.parent / "messages" / f"{message_id}.json"
        try:
            size = message_file.stat().st_size
        except OSError:
            continue
        if total + size > _TRANSCRIPT_MAX_BYTES:
            return
        total += size
        data = _read_json_bounded(message_file, _TRANSCRIPT_MESSAGE_MAX_BYTES)
        if not isinstance(data, dict):
            continue
        role = data.get("role") or meta.get("role") or ""
        message_raw = data.get("message")
        message = message_raw
        if isinstance(message_raw, str):
            try:
                message = json.loads(message_raw)
            except json.JSONDecodeError:
                message = None
        if isinstance(message, dict):
            role = message.get("role") or role
            content = message.get("content")
        else:
            content = data.get("content")
        yield {"message": {"role": role, "content": content}}


def _entries_from_json(data: object, path: Path):
    if isinstance(data, list):
        if _is_codebuddy_index(path, data):
            yield from _iter_codebuddy_entries(path, data)
        else:
            for item in data:
                if isinstance(item, dict):
                    yield item
        return
    if not isinstance(data, dict):
        return
    for key in ("messages", "conversation", "turns", "transcript_turns", "chat"):
        value = data.get(key)
        if isinstance(value, list):
            if _is_codebuddy_index(path, value):
                yield from _iter_codebuddy_entries(path, value)
            else:
                for item in value:
                    if isinstance(item, dict):
                        yield item
            return
    yield data


def _iter_jsonl_entries(path: Path):
    """流式读取 JSONL 前缀，尽早出现决策时无需读完整个文件。"""
    total = 0
    count = 0
    try:
        with path.open("rb") as fh:
            for raw_line in fh:
                total += len(raw_line)
                if total > _TRANSCRIPT_MAX_BYTES or count >= _TRANSCRIPT_MAX_ENTRIES:
                    return
                line = raw_line.decode("utf-8-sig", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    count += 1
                    yield obj
    except OSError:
        return


def _iter_transcript_entries(path: Path):
    """有界加载 Qoder/Claude JSONL 或 CodeBuddy index 形态的 transcript。"""
    if not path.is_file():
        return
    if path.name == "index.json":
        data = _read_json_bounded(path, _TRANSCRIPT_MAX_BYTES)
        yield from _entries_from_json(data, path)
        return

    if path.suffix.lower() == ".jsonl":
        yield from _iter_jsonl_entries(path)
        return

    text = _read_text_bounded(path, _TRANSCRIPT_MAX_BYTES)
    if text.strip():
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            for line in text.splitlines()[:_TRANSCRIPT_MAX_ENTRIES]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
        else:
            yield from _entries_from_json(data, path)
        return

    # 未知后缀但文件超限：保守地尝试 JSONL 前缀，不能仅因后续轮次很大就拒绝整段对话。
    yield from _iter_jsonl_entries(path)


def _entry_message(entry: dict) -> dict:
    message = entry.get("message")
    return message if isinstance(message, dict) else entry


def _entry_role(entry: dict) -> str:
    return str(_entry_message(entry).get("role") or entry.get("type") or "").lower()


def _entry_blocks(entry: dict) -> list:
    content = _entry_message(entry).get("content")
    return content if isinstance(content, list) else []


def _parse_object(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _short_tool_name(name: str) -> str:
    value = str(name or "").strip().replace("-", "_").lower()
    return value.rsplit("__", 1)[-1]


def _canonical_tool(name: str, raw_input: object) -> tuple[str, dict]:
    """拆开直接 MCP 工具名与 Qoder 的通用 ``mcp_call`` 信封。"""
    tool = _short_tool_name(name)
    args = _parse_object(raw_input)
    if tool != "mcp_call":
        return tool, args
    target = args.get("toolName") or args.get("tool_name") or args.get("name") or ""
    return _short_tool_name(str(target)), _parse_object(args.get("arguments") or args.get("args"))


def _tool_call(block: dict) -> tuple[str, str, dict] | None:
    kind = str(block.get("type") or "").replace("-", "_").lower()
    if kind not in ("tool_use", "tool_call"):
        return None
    function = block.get("function")
    function = function if isinstance(function, dict) else {}
    name = (
        block.get("name") or block.get("toolName") or block.get("tool_name") or function.get("name")
    )
    if not name:
        return None
    call_id = str(
        block.get("id")
        or block.get("toolCallId")
        or block.get("tool_call_id")
        or block.get("call_id")
        or ""
    )
    raw_input = block.get("input")
    if raw_input is None:
        raw_input = block.get("args")
    if raw_input is None:
        raw_input = block.get("arguments")
    if raw_input is None:
        raw_input = function.get("arguments")
    tool, args = _canonical_tool(str(name), raw_input)
    return tool, call_id, args


def _tool_result(block: dict) -> tuple[str, str, bool] | None:
    kind = str(block.get("type") or "").replace("-", "_").lower()
    if kind != "tool_result":
        return None
    result_id = str(
        block.get("tool_use_id")
        or block.get("toolUseId")
        or block.get("toolCallId")
        or block.get("tool_call_id")
        or block.get("call_id")
        or ""
    )
    is_error = bool(block.get("is_error") or block.get("isError"))
    return result_id, str(block.get("name") or block.get("toolName") or ""), is_error


def _flatten_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_flatten_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "output", "result", "message", "value"):
            if key in value:
                return _flatten_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return ""


def _result_text(block: dict) -> str:
    for key in ("content", "text", "output", "result"):
        if key in block:
            return _flatten_text(block[key]).strip()
    return ""


def _result_is_error(block: dict, text: str) -> bool:
    if block.get("is_error") or block.get("isError"):
        return True
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict) and (value.get("error") or value.get("ok") is False):
        return True
    lowered = text.lower()
    return text.startswith("Error:") or "only available in plan mode" in lowered


def _contains_ok(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("ok") is True or value.get("success") is True:
            return True
        return any(_contains_ok(value.get(key)) for key in ("data", "result", "content"))
    if isinstance(value, list):
        return any(_contains_ok(item) for item in value)
    return False


def _result_ok(text: str) -> bool:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    return _contains_ok(value)


def _answer_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            answer = _answer_value(item)
            if answer:
                return answer
    if isinstance(value, dict):
        for key in ("answers", "answer", "selected", "selection", "value"):
            if key in value:
                answer = _answer_value(value[key])
                if answer:
                    return answer
        # Some hosts encode answers as {"<question>": "<answer>"}.
        for item in value.values():
            answer = _answer_value(item)
            if answer:
                return answer
    return ""


def _clean_answer(answer: str) -> str:
    value = answer.strip().strip("\"'")
    for prefix in ("Other:", "其他:"):
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
            break
    return value.splitlines()[0].strip() if value else ""


def _choice_answer(text: str) -> str:
    """提取同步回答；异步工具只发布问题，不返回用户答案。"""
    marker = "Your questions have been answered:"
    if marker in text:
        tail = text.split(marker, 1)[1].strip()
        match = re.search(r'="(.*?)"\.', tail, re.DOTALL)
        if match:
            return _clean_answer(match.group(1))
    try:
        answer = _answer_value(json.loads(text))
    except json.JSONDecodeError:
        answer = ""
    if answer:
        return _clean_answer(answer)
    if not text or text.startswith("Questions published"):
        return ""
    return _clean_answer(text)


def _plain_user_text(entry: dict) -> str:
    """只取用户文本；JSONL 的 tool_result 块也可能挂在 user 角色下。"""
    if _entry_role(entry) != "user":
        return ""
    content = _entry_message(entry).get("content")
    if isinstance(content, str):
        return content.strip()
    texts = [
        str(block.get("text") or "")
        for block in _entry_blocks(entry)
        if isinstance(block, dict) and str(block.get("type") or "").lower() == "text"
    ]
    return "\n".join(text for text in texts if text).strip()


def _is_task_chooser(tool: str, args: dict) -> bool:
    if tool not in _TASK_CHOOSERS:
        return False
    encoded = json.dumps(args, ensure_ascii=False)
    return (
        "任务关联" in encoded
        or "跨会话任务记忆" in encoded
        or ("task_id" in encoded and "跳过" in encoded)
    )


def _task_id_from_answer(answer: str, active: list) -> str:
    match = re.search(r"task_id=([^）)\s]+)", answer)
    if match:
        return match.group(1).strip("\"'")
    folded = answer.casefold()
    exact = [
        str(task.get("id") or "")
        for task in active
        if folded in (str(task.get("id") or "").casefold(), str(task.get("title") or "").casefold())
    ]
    if exact:
        return exact[0]
    matches = [
        str(task.get("id") or "")
        for task in active
        if folded
        and (
            folded in str(task.get("id") or "").casefold()
            or folded in str(task.get("title") or "").casefold()
        )
    ]
    return matches[0] if len(matches) == 1 else ""


def _classify_choice(answer: str, active: list) -> tuple[str, str]:
    """返回 ``(kind, task_id)``；未命中的自由文本按新建任务处理。"""
    value = _clean_answer(answer)
    folded = value.casefold()
    if folded in _SKIP_ANSWERS or folded.startswith(
        ("跳过", "不绑定", "不关联", "本次不做任务关联", "暂不关联")
    ):
        return "skip", ""
    task_id = _task_id_from_answer(value, active)
    if task_id:
        return "existing", task_id
    if value.startswith("新建任务"):
        remainder = re.sub(r"^新建任务\s*[：:]?\s*", "", value).strip()
        if remainder and not remainder.startswith(("…", "(", "（")):
            return "new", ""
        return "new_unnamed", ""
    return "new", ""


def _lookup_pending_call(
    calls: dict[str, tuple[str, dict]], result_id: str, tool: str
) -> tuple[str, dict] | None:
    if result_id and result_id in calls:
        return calls.pop(result_id)
    if result_id:
        return None
    for call_id, call in reversed(list(calls.items())):
        if call[0] == tool:
            calls.pop(call_id)
            return call
    return None


def _safe_transcript_entries(path: Path):
    try:
        yield from _iter_transcript_entries(path)
    except Exception:
        # 宿主中途改变 transcript 形状时，Hook 注入也不能失败。错误前的部分证据仍可用；
        # 没有可用证据时，调用方回退到 binding/raw/弹框。
        return


def _load_transcript_task(event: dict, active: list) -> tuple[str, str]:
    """从当前 transcript 恢复首个真实任务选择决策。

    只有任务管理工具的成功结果才算绑定。首个跳过是终态；绑定失败不是终态，
    后续重试或重选可以成功。即使选择框已被压缩掉，只要成功绑定记录仍在，也是
    直接证据。不扫描目录，也不跨会话猜测。
    """
    transcript_path = _event_transcript_path(event)
    if not transcript_path:
        return "", ""
    entries = _safe_transcript_entries(Path(transcript_path))

    calls: dict[str, tuple[str, dict]] = {}
    first_choice = False
    choice_kind = ""
    pending_choice_id = ""
    pending_choice_async = False
    awaiting_new_name = False
    saw_create = False
    created_ok = False

    for entry in entries:
        blocks = _entry_blocks(entry)
        candidates = blocks if blocks else [entry]
        for block in candidates:
            if not isinstance(block, dict):
                continue
            call = _tool_call(block)
            if call is None:
                continue
            tool, call_id, args = call
            if call_id:
                calls[call_id] = (tool, args)
            if tool == "create_task" and (
                not first_choice or choice_kind in ("new", "new_unnamed")
            ):
                saw_create = True
            elif _is_task_chooser(tool, args):
                # 只有首个决策尚未完成，或首个回答要求补输新建任务名称时，
                # 后续选择框才与当前恢复流程相关。
                if not first_choice or choice_kind == "new_unnamed":
                    pending_choice_id = call_id
                    pending_choice_async = tool == "askuserquestionasync"
                    awaiting_new_name = False

        for block in candidates:
            if not isinstance(block, dict):
                continue
            result = _tool_result(block)
            if result is None:
                continue
            result_id, result_name, is_error = result
            text = _result_text(block)
            if not result_id and result_name:
                tool_hint = _short_tool_name(result_name)
            else:
                tool_hint = ""
            pending = _lookup_pending_call(calls, result_id, tool_hint)
            if pending is None:
                continue
            tool, args = pending
            if _result_is_error(block, text):
                if tool in _TASK_CHOOSERS and result_id == pending_choice_id:
                    pending_choice_id = ""
                    pending_choice_async = False
                continue

            if tool in _TASK_CHOOSERS:
                answer = _choice_answer(text)
                if not answer:
                    continue  # async publication: wait for the user's next text
                first_choice = True
                choice_kind, _ = _classify_choice(answer, active)
                pending_choice_id = ""
                pending_choice_async = False
                awaiting_new_name = choice_kind == "new_unnamed"
                saw_create = choice_kind in ("new", "new_unnamed")
                created_ok = False
                if choice_kind == "skip":
                    return "", "skipped"
            elif tool == "create_task":
                if _result_ok(text) and (not first_choice or choice_kind in ("new", "new_unnamed")):
                    created_ok = True
            elif tool == "set_session_task":
                if not _result_ok(text):
                    continue
                task_id = str(args.get("task_id") or "").strip()
                if not task_id:
                    continue
                if saw_create and not created_ok:
                    continue
                return task_id, "transcript"

        user_text = _plain_user_text(entry)
        if not user_text:
            continue
        if pending_choice_async or awaiting_new_name:
            answer = _clean_answer(user_text)
            first_choice = True
            choice_kind, _ = _classify_choice(answer, active)
            pending_choice_id = ""
            pending_choice_async = False
            awaiting_new_name = choice_kind == "new_unnamed"
            saw_create = choice_kind in ("new", "new_unnamed")
            created_ok = False
            if choice_kind == "skip":
                return "", "skipped"

    return "", ""


def _safe_session_id(session_id: str) -> bool:
    """拒绝路径分隔符，避免把宿主传入的 id 直接当文件名使用。"""
    return bool(
        session_id
        and session_id not in (".", "..")
        and not any(char in session_id for char in ("/", "\\", "\x00"))
    )


def _load_session_task(
    repo_path: str,
    session_id: str,
    event: dict | None = None,
    active_tasks: list | None = None,
) -> tuple[str, str]:
    """返回当前会话已有的 ``(task_id, source)`` 决策。

    优先级：当前 live/consumed 绑定 > 当前事件 transcript > raw 采集索引。
    transcript 桥接兼容宿主在恢复同一逻辑对话时重新生成 ``session_id`` 的情况。
    所有读取都有界且 fail-open；没有证据时恢复首次选择弹框。
    """
    if not _safe_session_id(session_id):
        return "", ""
    bindings_dir = Path(repo_path) / "repowiki" / ".meta" / "task_bindings"
    for path in (
        bindings_dir / f"{session_id}.json",
        bindings_dir / "consumed" / f"{session_id}.json",
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            task_id = str(data.get("task_id") or "").strip()
            if task_id:
                return task_id, "binding"

    if event is not None:
        task_id, source = _load_transcript_task(event, active_tasks or [])
        if task_id or source == "skipped":
            return task_id, source

    # 旧版本可能已删除一次性绑定凭证，但 raw 仍保留归属；最新匹配采集优先。
    try:
        idx_path = Path(repo_path) / "repowiki" / "raw" / ".index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8-sig", errors="replace"))
        files = data.get("files", []) if isinstance(data, dict) else []
        for entry in reversed(files):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("source_session") or "") != session_id:
                continue
            task_id = str(entry.get("task_id") or "").strip()
            if task_id:
                return task_id, "history"
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        pass
    return "", ""


# ---------------------------------------------------------------------------
# 弹框通道差异：宿主的结构化提问工具决定「一框列全」是否物理可行
# ---------------------------------------------------------------------------
# CodeBuddy 的 ask_followup_question 只受 schema「建议 2-4 个 options」这种软约束，
# 注入文案历来硬性压过它、要求一框列全（多框是用户明确反对过的行为）。
# Qoder（含 Qoder CN）与 Trae 的 AskUserQuestion 是硬约束：单题 2-4 个 options、最多 4 题、
# header ≤12 字符、label 建议 1-5 词——进行中任务一多就物理放不下，硬凑会让弹框调用
# 直接失败。故按宿主分档：截断到选项上限，其余任务写进问题正文，由该工具自带的
# 「其他」自由输入承接（输入列表内任务名 → 关联该任务；列表外 → 新建）。
_QODER_OPTION_CAP = 4
_QODER_LABEL_MAX = 12  # 中文长标题截断为 label，完整标题与 task_id 放 description


def _chooser_channel() -> dict:
    """Return the host's structured-question channel."""
    if IDE_DIR_NAME in (".qoder", ".trae"):
        return {"tool": "AskUserQuestion", "option_cap": _QODER_OPTION_CAP}
    return {"tool": "ask_followup_question", "option_cap": None}


# capped 档的保留选项 label：与任务选项共用命名空间，渲染任务 label 时须避开
_RESERVED_LABELS = ("新建任务", "跳过")


def _capped_label(title: str, used: set) -> str:
    """任务选项 label：先取短标题，截断撞车时逐步延长直到可区分。

    长中文标题共享前 12 字是常态（task_id 多由标题生成，换用 id 反而一样撞），而
    重复 label 会让用户在弹框里分不清选项。label 没有硬字符上限（只有 header 限
    12 字符），所以延长付出的只是观感，比截断丢信息划算。
    """
    label = title[:_QODER_LABEL_MAX]
    while label in used and len(label) < len(title):
        label = title[: min(len(label) + 4, len(title))]
    n = 2
    while label in used:
        label = f"{title}（{n}）"
        n += 1
    used.add(label)
    return label


def _option_lines(tasks: list, capped: bool) -> list:
    """Render the option list lines for the chooser section."""
    lines = []
    used: set = set(_RESERVED_LABELS) if capped else set()
    for t in tasks:
        title = str(t.get("title") or t.get("id") or "")
        if capped:
            lines.append(
                f"    - label=「{_capped_label(title, used)}」 "
                f"description=「{title}」（task_id={t.get('id')}）"
            )
        else:
            lines.append(f"    - {title}（task_id={t.get('id')}）")
    return lines


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
                    status = line[len("status:") :].strip().strip("\"'")
                elif line.startswith("task_id:"):
                    task_id = line[len("task_id:") :].strip().strip("\"'")
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
                        score = int(line[len("friction_score:") :].strip())
                    except ValueError:
                        score = None
                elif line.startswith("status:"):
                    status = line[len("status:") :].strip().strip("\"'")
                elif line.startswith("friction_signals:"):
                    for part in line[len("friction_signals:") :].split(","):
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


_DOCTRINE_MAX_BYTES = 20_000


def _load_doctrine(repo_path: str) -> str:
    """Return the Team Doctrine body (repowiki/wiki/doctrine.md) for injection.

    The doctrine is the knowledge flywheel's aggregated consensus, regenerated
    by ``refresh_doctrine``. At ~3KB it is cheap enough to hard-inject at every
    session start — a hard trigger that AGENTS.md's soft "query_wiki first"
    advice cannot match. The OKF frontmatter block is stripped; the function
    degrades to "" when the file is absent, too large, or unreadable so the
    hook never breaks the task-binding prompt.
    """
    try:
        path = Path(repo_path) / "repowiki" / "wiki" / "doctrine.md"
        if not path.is_file():
            return ""
        if path.stat().st_size > _DOCTRINE_MAX_BYTES:
            return ""
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    body = text
    if body.startswith("---"):
        parts = body.split("\n---\n", 1)
        if len(parts) == 2:
            body = parts[1]
    body = body.strip()
    if not body:
        return ""
    return (
        "【项目定向】本会话已注入 Team Doctrine（知识飞轮聚合的团队共识，"
        "随 refresh_doctrine 刷新），请作为本仓库的默认做事方式参考，"
        "无需再 query_wiki(mode='overview') 拉取：\n\n" + body
    )


def _load_knowledge_overview(repo_path: str) -> str:
    """One-paragraph knowledge-base overview for the fresh session (P2-2 thin).

    claude-mem borrowing: SessionStart is the "visible before work starts"
    channel — the tool description (P0-3) only fires when the agent already
    thinks of calling query_wiki. This section says the knowledge base EXISTS
    (N notes / recent key decisions) and carries the one-line four-layer
    retrieval strategy, so agents that never thought to search still do.

    Deliberately thin: counts files and reads only the 3 newest note titles
    (stdlib-only line scan of ``metadata.date``-style filename prefixes —
    note filenames start with YYYY-MM-DD). Degrades to "" when repowiki/
    notes is absent or empty; never breaks the task prompt.
    """
    try:
        notes_dir = Path(repo_path) / "repowiki" / "notes"
        if not notes_dir.is_dir():
            return ""
        notes = sorted(
            (p for p in notes_dir.glob("*.md") if p.is_file()),
            key=lambda p: p.name,
            reverse=True,
        )
        if not notes:
            return ""
        recent = [p.name[:-3] for p in notes[:3]]
        lines = [
            f"【知识库提示】本仓库有 repowiki 知识库（{len(notes)} 条笔记），改文件/做设计前先查：",
            "- 改某文件前：query_wiki(by_file=<路径>) 查该文件的历史决策与教训；",
            "- 主题检索：query_wiki(mode='check') 先轻量预检，再全文检索（结果带 est_tokens 成本）；",
            f"- 最新笔记：{'；'.join(recent)}",
        ]
        return "\n".join(lines)
    except OSError:
        return ""


def _build_message(event: dict, repo_path: str) -> str:
    """Build the guidance injected into the fresh session.

    IMPORTANT: the user expects an interactive chooser, NOT a text paragraph.
    The message below must instruct the agent to surface the choice through the
    host's structured-question tool (see ``_chooser_channel``), so the user can
    click an option or type a task name, exactly like a native dialog. Hosts
    differ in whether "list every task in one box" is physically possible —
    Qoder's AskUserQuestion caps options at 4, so that channel truncates the
    option list and pushes the remainder into the question body + free-text
    "Other" input.
    """
    session_id = _event_session_id(event)
    active = _load_active_tasks(repo_path)
    channel = _chooser_channel()
    cap = channel["option_cap"]
    bound_task, bound_source = _load_session_task(repo_path, session_id, event, active)
    skipped = bound_source == "skipped"
    resolved = bool(bound_task) or skipped

    lines = ["[task-memory] 本会话开始前，请先处理「任务关联」（跨会话任务记忆）。"]
    if not resolved:
        lines.append("")
        lines.append(
            "【硬性执行顺序】无论用户第一条消息问什么（哪怕是关于代码、文件、bug 的具体问题），"
            "本会话的第一个动作都必须是下面这个任务关联弹框流程；弹框、绑定、拉取上下文完成后，"
            "才允许开始读文件/搜索代码/回答用户提问（有积压时先阻塞补蒸馏，"
            "见下方「补蒸馏」段落，蒸馏完成后再回答）。严禁先探索代码或直接回答，事后再补弹任务关联框。"
        )
    lines.append("")
    tool = str(channel["tool"])
    bind_call = (
        f"set_session_task(source_session_id={session_id or '<当前会话id>'}, task_id=<选中任务>)"
    )
    if bound_task:
        lines.append(
            f"【已有任务关联】会话记录显示本会话已选择任务「{bound_task}」，无需重复弹框。"
        )
        lines.append(
            f"不要再次调用 {tool} 询问任务；只有用户明确要求切换任务，"
            "或 get_task_context 返回任务不存在时，才重新选择。"
        )
    elif skipped:
        lines.append("【已有会话决策】历史对话中的首个任务选择是「跳过/不绑定」，无需重复弹框。")
        lines.append(
            f"不要再次调用 {tool} 询问任务，也不要调用 set_session_task 或 get_task_context；"
            "直接开始回答用户。只有用户明确要求关联任务时，才重新选择。"
        )
    elif cap is None:
        # 无限选项宿主（CodeBuddy 系）：一框列全，压过 schema 的「建议 2-4」。
        lines.append(
            f"【必须弹框：只弹一次，一框列全】请立即调用 {tool} 工具弹出结构化选择框"
            "（这是 IDE 的原生弹框 UI，用户可以直接点击选项），不要用纯文本输出一段话让用户自行回复。"
        )
        lines.append("  硬约束：")
        lines.append(
            f"  - 整个流程只允许调用 1 次 {tool}，且 questions 数组里只放 1 个 question"
            "（标题「任务关联」，multiSelect=false）。"
        )
        lines.append(
            "  - 这唯一一个 question 的 options 必须一次性列全：下面每个进行中任务各占一个选项，"
            "末尾再加「新建任务…（在输入框直接输入名称）」和「跳过（本次不做任务关联）」。"
        )
        lines.append(
            "  - 严禁因为工具 schema 建议「2-4 个 options」就把任务拆进多个 question 或分多次调用弹框；"
            "选项条数不受该建议限制，一框列全是硬性要求。"
        )
        lines.append(
            "  - 问题正文里写清：列表里没有想要的任务时，可直接在弹框的输入框里输入新任务名后回车。"
        )
        lines.append("  该 question 的 options（按顺序）：")
        lines.extend(_option_lines(active, capped=False))
        lines.append("    - 新建任务…（在输入框直接输入名称）")
        lines.append("    - 跳过（本次不做任务关联，直接开始干活）")
        lines.append("")
        lines.append(
            "【结果判定】用户返回的是上面列出的任务标题 → 调用 "
            f"{bind_call} 建立绑定；"
            "返回的是列表里没有的自由文本 → 先 create_task(title=<该文本>, description=<可选>) 再绑定；"
            "返回「跳过」→ 本次不关联。"
            f"只有当用户选了「新建任务…」却没给出名字时，才允许再弹一次 {tool} 要名字"
            "（标题「新建任务」，问题「请输入新任务名称」）——这是唯一允许的第二次弹框，除此之外一律不得再弹框。"
        )
    else:
        # 硬上限宿主（Qoder 系 AskUserQuestion）：截断到上限，余量走「其他」自由输入。
        # options 同时有**硬下限 2**：0 个进行中任务时只给「跳过」会让弹框调用直接
        # 失败——而那恰是新仓库首个会话（最该引导建任务的一次），故有空位时补「新建任务」。
        shown = active[: max(cap - 1, 0)]
        rest = active[len(shown) :]
        lines.append(
            f"【必须弹框：只弹一次，选项 {cap} 个以内】请立即调用 {tool} 工具弹出结构化选择框"
            "（这是 Qoder 的原生弹框 UI，用户可以直接点击选项，也可以选「其他」直接输入任务名），"
            "不要用纯文本输出一段话让用户自行回复。"
        )
        lines.append("  硬约束：")
        lines.append(
            f"  - 整个流程只允许调用 1 次 {tool}，且 questions 数组里只放 1 个 question"
            "（header 用「任务关联」，不超过 12 字符，multiSelect=false）。"
        )
        lines.append(
            f"  - 该工具的 options 是**硬上限 {cap} 个、硬下限 2 个**（都不是建议）：本框只放"
            "下面这几个选项 +「跳过」；严禁为列全所有任务而拆成多个 question 或分多次弹框。"
        )
        if rest:
            lines.append(
                f"  - 进行中共 {len(active)} 个任务，Qoder 弹框 options 硬上限 {cap} 个，"
                f"因此只把最近的 {len(shown)} 个任务放进选项；其余 {len(rest)} 个任务列在"
                "下方「正文任务清单」。请把这段说明写进 question 正文，并告诉用户："
                "想选清单里的任务时，点「其他」输入任务名或 task_id 即可关联。"
            )
        lines.append(
            "  - label 要短（工具建议 1-5 词），完整标题与 task_id 放 description；"
            "标题前缀相同导致 label 撞车时按给出的 label 原样使用，不要自行截短。"
        )
        lines.append("  该 question 的 options（按顺序）：")
        lines.extend(_option_lines(shown, capped=True))
        if len(shown) + 1 < cap:
            lines.append(
                "    - label=「新建任务」 description=「没有合适的进行中任务，新建一个（名称在本框直接输入）」"
            )
        lines.append("    - label=「跳过」 description=「本次不做任务关联，直接开始干活」")
        if rest:
            lines.append("  正文任务清单（未进选项，写进 question 正文供用户选「其他」输入）：")
            lines.extend(_option_lines(rest, capped=False))
            lines.append(
                "  操作提示：选「其他」后输入上面任一任务名、task_id 或关键字，"
                "命中即关联；未命中则视为新建任务。"
            )
        lines.append("")
        lines.append(
            "【结果判定】用户点选某个任务选项 → 取该选项 description 里的 task_id 调用 "
            f"{bind_call} 建立绑定；"
            "用户选「其他」输入的文本 → 命中上面任一任务标题或 task_id 就关联该任务，"
            "否则先 create_task(title=<该文本>, description=<可选>) 再绑定；"
            "用户点「新建任务」但没给名字 → 在回复正文里请用户给出任务名"
            f"（本宿主不得二次弹框），拿到名字后 create_task(title=<名称>) 再 {bind_call}；"
            "选「跳过」→ 本次不关联。除此之外一律不得再弹框。"
        )

    lines.append("")
    if skipped:
        lines.append("本会话不关联任务，直接开始回答；不要拉取任务上下文或按任务补蒸馏。")
    elif bound_task:
        if bound_source in ("history", "transcript"):
            restore_call = f"set_session_task(source_session_id={session_id}, task_id={bound_task})"
            lines.append(
                f"为恢复会话绑定，请先调用 {restore_call}，再调用 "
                f"get_task_context(task_id={bound_task}) 拉取该任务上下文继续工作。"
            )
        else:
            lines.append(
                f"请直接调用 get_task_context(task_id={bound_task}) 拉取该任务上下文继续工作。"
            )
    else:
        lines.append(
            "关联完成后调用 get_task_context(task_id=<选中任务>) 拉取该任务上下文继续工作。"
            "返回中的 pending_raw_count 是本任务尚未蒸馏的历史对话数：若大于 0，按下方"
            "「补蒸馏」发一个异步蒸馏 subagent（后台执行，不阻塞回答），"
            "在自然停顿点拉取蒸馏结果并展示待确认草稿。"
            "若用户明确表示本次会话与任何任务无关，可跳过本提示。"
        )

    # Catch-up distillation backlog: deterministic trigger so agents that never
    # "think to" distill still clear the backlog at session start.
    pending_counts = _count_pending_raws(repo_path)
    if pending_counts and not skipped:
        total = sum(pending_counts.values())
        lines.append("")
        lines.append(f"【补蒸馏】检测到 {total} 条未蒸馏的历史对话积压：")
        for tid, n in sorted(pending_counts.items()):
            label = f"任务 {tid}" if tid else "未关联任务"
            lines.append(f"  - {label}: {n} 条")
        binding_prefix = "已有任务关联，直接" if bound_task else "绑定任务之后，"
        if IDE_DIR_NAME == ".codebuddy":
            lines.append(
                f"{binding_prefix}立即用 Task 工具发一个**异步**「蒸馏 worker」subagent "
                "（.codebuddy/agents/distill-worker.md，已授权 codewiki MCP；"
                "Task 工具传 name=<成员名> 参数即以后台 team member 运行，不阻塞主 Agent）执行补蒸馏"
                "（**清空本任务的全部待蒸馏积压**，不设条数上限——只挑最近几条会让老积压永远轮不到）；"
                "补蒸馏只提取经验笔记（skip_memories 默认生效），任务记忆由主动沉淀通道直写；"
                "主 Agent 不必等 subagent 返回，直接开始回答用户提问，不要亲自 read_file raw 原文。"
            )
        else:
            # claude 家族（Qoder/Claude Code/Gemini CLI）：自定义子代理拿不到
            # MCP 权限（实测），委托改走内置 general-purpose 子代理，
            # 以 distill-worker.md 正文为剧本。包内源副本同走此分支。
            lines.append(
                f"{binding_prefix}立即用 Task 工具发一个**异步**内置 general-purpose 子代理执行补蒸馏："
                f"让它先读 {IDE_DIR_NAME}/agents/distill-worker.md（蒸馏 worker 剧本），"
                "再按其中 Mode C 流程执行（本宿主自定义子代理拿不到 MCP 权限，须用内置子代理；"
                "**清空本任务的全部待蒸馏积压**，不设条数上限）；"
                "补蒸馏只提取经验笔记（skip_memories 默认生效），任务记忆由主动沉淀通道直写；"
                "主 Agent 不必等 subagent 返回，直接开始回答用户提问，不要亲自 read_file raw 原文。"
            )
        lines.append("蒸馏子代理走 Mode C（纯 MCP JSON）流程：")
        lines.append(
            '  1. distill_conversation(mode="prepare", task_id=<绑定的任务id>) '
            "获取该任务的积压对话清单"
        )
        lines.append(
            "  2. 按清单逐条 read_file 阅读 raw 文件（**清单里每条都要处理，不设条数上限**），"
            "提取 notes（通用经验）；memories 默认跳过（通道互斥，任务记忆归主动沉淀直写）"
        )
        lines.append(
            '  3. distill_conversation(mode="submit", distilled=<提取结果>) 提交；'
            "产出为草稿笔记（待确认）"
        )
        lines.append(
            "  4. subagent 在后台执行，主 Agent 直接回答用户提问；"
            "在自然停顿点（任务里程碑、话题切换、收尾轮）重新 get_task_context 拉取最新上下文"
            "（新落盘的任务记忆/待确认草稿笔记会一并注入），并向用户展示待确认的草稿笔记；"
            "subagent 失败/超时不重试——未蒸馏的 raw 留在 raw/ 等下次会话再补"
        )
        lines.append(
            "  5. 向用户展示待确认的草稿笔记，经 confirm_note 确认后才正式落盘"
            "     （任务记忆已直写落盘，无需确认——ADR-0002）"
        )
        lines.append(
            "若用户明确表示紧急，可先回答提问，蒸馏结果在会话结束前展示确认即可。"
            "注意：draft 笔记在确认前只能作为只读参考，不得当作已定论的结论引用。"
            "任务记忆（memories.md）是任务进度记录，直写可信，可正常作为上下文使用。"
        )

    # K-line: the newest pending capture showed friction (score >= 20) —
    # surface a one-line hint so the agent prioritises catch-up distillation.
    friction_hint = _latest_friction_hint(repo_path)
    if friction_hint:
        lines.append("")
        lines.append(friction_hint)

    doctrine = _load_doctrine(repo_path)
    if doctrine:
        lines.append("")
        lines.append(doctrine)

    # P2-2 (claude-mem borrowing, thin): knowledge-base overview — make the
    # KB's existence and the cheapest retrieval entries visible before work
    # starts, complementing P0-3's call-time tool description.
    overview = _load_knowledge_overview(repo_path)
    if overview:
        lines.append("")
        lines.append(overview)

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
