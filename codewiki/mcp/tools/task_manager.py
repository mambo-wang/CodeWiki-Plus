"""MCP tool: task_manager — task CRUD + per-task memory store.

This module adds a *task memory layer* alongside the wiki knowledge layer
(``notes/`` + ``wiki/``) and the team-memory fusion layer (``raw/``). A task is
a long-running unit of work that accumulates distilled memories across many
sessions:

    repowiki/tasks/
      .index.json             # task index: [{id, title, status, created_at, ...}]
      <task_id>/
        task.md               # task description + status (frontmatter + body)
        memories.md           # accumulated task memories (append-only; entries
                              #   carry "### YYYY-MM-DD HH:MM" headings — legacy
                              #   heading-less files parse via blank-line fallback)
        memories-archive.md   # compacted entries' originals (append-only, P1)

Session bindings live under ``repowiki/.meta/task_bindings/<source_session_id>.json``
so an IDE session can be associated with a task. ``capture_conversation`` then
stamps ``task_id`` into raw frontmatter, ``distill_conversation`` routes distilled
memories back to the task, and ``get_task_context`` aggregates the task's knowledge
so the next session can pick up where it left off.

Distilled task memories are written DIRECTLY into ``memories.md`` (ADR-0002:
task-scoped progress knowledge carries bounded, task-lifetime noise cost, so no
confirm gate — unlike notes, which keep the confirm_note/reject_note quality gate
because they enter the shared, retrieval-indexed knowledge base).

Design constraints (must hold):
  - task_id is derived from the original title (slugified) and is immutable.
  - Duplicate detection is by original title (strip-compared); no two tasks may
    share a title, and there is no rename tool — delete then recreate instead.
  - ``delete_task`` cascades: it removes the task directory, its index entry, and
    any session binding files pointing at it.
  - ``memories.md`` is append-only; concurrent writers are serialized via an
    atomic write (temp file + ``os.replace``).
  - ``query_wiki`` never validates task existence — ghost ``task_id`` references
    are allowed (the task may have been deleted; the note stays).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.capture_conversation import (
    _resolve_output_dir,
    _slugify,
    pending_raws_by_task,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #


def _tasks_dir(output_dir: Path) -> Path:
    """Path to the repowiki/tasks directory (created lazily by callers)."""
    return output_dir / "tasks"


def _bindings_dir(output_dir: Path) -> Path:
    """Path to repowiki/.meta/task_bindings (created lazily by callers)."""
    return output_dir / ".meta" / "task_bindings"


def _index_path(output_dir: Path) -> Path:
    return _tasks_dir(output_dir) / ".index.json"


def _read_index(output_dir: Path) -> List[Dict[str, Any]]:
    """Read the task index as a list of task entries; [] when absent/corrupt."""
    p = _index_path(output_dir)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        tasks = data.get("tasks", []) if isinstance(data, dict) else []
        return [t for t in tasks if isinstance(t, dict)]
    except (json.JSONDecodeError, OSError):
        logger.warning("Task index unreadable at %s; treating as empty.", p)
        return []


def _write_index(output_dir: Path, tasks: List[Dict[str, Any]]) -> None:
    """Atomically write the task index."""
    p = _index_path(output_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _atomic_replace_with_retry(tmp, p)


def _find_by_id(tasks: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def _find_by_title(tasks: List[Dict[str, Any]], title: str) -> Optional[Dict[str, Any]]:
    needle = title.strip()
    for t in tasks:
        if str(t.get("title", "")).strip() == needle:
            return t
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_path(output_dir: Path, task_id: str) -> Path:
    return _tasks_dir(output_dir) / task_id / "task.md"


def _memories_path(output_dir: Path, task_id: str) -> Path:
    return _tasks_dir(output_dir) / task_id / "memories.md"


def _extract_fm(text: str, key: str) -> Optional[str]:
    """Extract a frontmatter value (top-level or nested under ``metadata:``).

    Mirrors ``knowledge_loop._extract_frontmatter`` semantics: the value may sit
    at the top level of the YAML block, or one level deep under ``metadata:``.
    """
    if not text:
        return None
    # Grab the first frontmatter block if present.
    m = re.match(r"\A---\s*\n(.*?)\n---", text, re.DOTALL)
    block = m.group(1) if m else text
    lines = block.splitlines()
    in_metadata = False
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_metadata = line.strip().lower() == "metadata:"
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        if k.strip() == key and v.strip():
            # Only honor top-level keys, or keys nested exactly one level.
            if indent == 0 or (in_metadata and indent >= 2):
                return v.strip().strip("'\"")
    return None


# --------------------------------------------------------------------------- #
# Task file write helpers
# --------------------------------------------------------------------------- #


def _task_frontmatter(task: Dict[str, Any]) -> str:
    """Render the YAML frontmatter block for a task.md file."""
    lines = [
        "---",
        "type: task",
        f"task_id: {task['id']}",
        f"title: {task['title']}",
        f"status: {task['status']}",
        f"created_at: {task['created_at']}",
    ]
    if task.get("completed_at"):
        lines.append(f"completed_at: {task['completed_at']}")
    lines.append("---")
    return "\n".join(lines)


def _write_task_file(output_dir: Path, task: Dict[str, Any], description: str) -> None:
    p = _task_path(output_dir, task["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (description or "").strip()
    content = _task_frontmatter(task) + "\n\n" + body + "\n"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    _atomic_replace_with_retry(tmp, p)


def _atomic_replace_with_retry(src: Path, dst: Path, attempts: int = 5) -> None:
    """os.replace with a short retry for Windows transient sharing violations.

    On Windows, AV scanners / search indexers can hold the destination file
    briefly, making os.replace fail with PermissionError (WinError 5) even
    though nothing is logically wrong. Retry with a tiny backoff; a persistent
    failure (real permission problem) still raises the last error.
    """
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


def _append_memory_atomic(path: Path, content: str) -> None:
    """Append a memory entry to memories.md using an atomic read-modify-write.

    Entries are stamped with a ``### YYYY-MM-DD HH:MM`` heading (P0 entry
    structuring, ADR-0001: format stays markdown; the heading is the parse
    boundary for truncation/compaction). Legacy files without headings are
    parsed by blank-line fallback — no migration is performed here; the file
    is rewritten lazily into headed form only when compaction runs (P1).

    The read + write is not lock-protected across processes, but the final
    replace is atomic, so no reader ever observes a partially written file.
    Callers that need cross-process serialization should serialize externally;
    within a single MCP server the tool dispatch already serializes handlers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8").rstrip("\n")
        if existing:
            existing += "\n\n"
    entry = f"### {datetime.now():%Y-%m-%d %H:%M}\n\n{(content or '').strip()}\n"
    new_content = existing + entry
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    _atomic_replace_with_retry(tmp, path)


# Compaction thresholds and keep-window (see docs/任务记忆存储与加载扩展性
# 设计方案.md §3 Q6/Q7; ADR-0001). The compact tool is a stateless two-phase
# (prepare/submit) MCP tool — the LLM summary is produced by the CALLER, never
# by this tool (same constraint as distill_conversation's Mode C).
_COMPACTION_THRESHOLD_COUNT = 40
_COMPACTION_THRESHOLD_BYTES = 24 * 1024
_COMPACTION_KEEP = 20
_COMPACTION_SUMMARY_MAX_CHARS = 2048
_SUMMARY_HEADING = "## 早期记忆（摘要）"
_ARCHIVE_FILENAME = "memories-archive.md"


def _split_memories(text: str) -> List[str]:
    """Split memories.md content into entries (P0 entry structuring).

    Headed form: entries delimited by ``### `` headings; a heading and its
    multi-paragraph body stay together. Legacy form (no headings): entries
    fall back to blank-line separated paragraphs. Mixed files (legacy block
    before the first heading — the lazy-migration intermediate state) use
    heading boundaries where present and blank-line splitting for the legacy
    pre-heading block. The compaction summary section (``## 早期记忆（摘要）``)
    is NOT an entry — use ``_split_summary_and_entries`` for files that may
    carry one.
    """
    if not text or not text.strip():
        return []
    if re.search(r"^### ", text, re.M):
        entries: List[str] = []
        for part in re.split(r"(?m)^(?=### )", text):
            part = part.strip()
            if not part:
                continue
            if part.startswith("### "):
                entries.append(part)
            else:
                entries.extend(p.strip() for p in re.split(r"\n\s*\n", part) if p.strip())
        return entries
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_summary_and_entries(text: str) -> Tuple[str, List[str]]:
    """Split memories.md content into (summary_section, entries).

    Post-compaction files carry a ``## 早期记忆（摘要）`` section (summary body
    + archive pointer line) before the kept entries. The summary section runs
    from the heading to the first ``### `` entry heading; anything BEFORE the
    summary heading (should not exist in canonical files, tolerated if it does)
    parses as legacy entries. Returns ("", entries) when no summary section.
    """
    if not text or not text.strip():
        return "", []
    idx = text.find(_SUMMARY_HEADING)
    if idx < 0:
        return "", _split_memories(text)
    prefix = text[:idx].strip()
    rest = text[idx:]
    m = re.search(r"(?m)^### ", rest)
    if m:
        summary = rest[: m.start()].rstrip()
        entries_text = rest[m.start() :]
    else:
        summary = rest.rstrip()
        entries_text = ""
    entries = _split_memories(prefix) if prefix else []
    entries.extend(_split_memories(entries_text))
    return summary, entries


def _archive_path(output_dir: Path, task_id: str) -> Path:
    """Path to a task's memory archive (compacted entry originals)."""
    return _tasks_dir(output_dir) / task_id / _ARCHIVE_FILENAME


def _compaction_needed(total_entries: int, mem_bytes: int) -> bool:
    """Whether compaction would actually help.

    Requires entries beyond the keep window (otherwise there is nothing to
    compress — a single oversized entry inside the keep window cannot be
    compacted away) AND at least one threshold exceeded.
    """
    return total_entries > _COMPACTION_KEEP and (
        total_entries > _COMPACTION_THRESHOLD_COUNT or mem_bytes > _COMPACTION_THRESHOLD_BYTES
    )


def _load_memories_limited(mem_path: Path, max_memories: Optional[int]) -> Tuple[str, int, bool]:
    """Read memories.md, returning (rendered_text, total_entries, truncated).

    ``max_memories`` keeps only the most recent entries (file order); the
    compaction summary section, when present, is always kept in the rendered
    text ahead of the entries. ``None`` or a non-positive / oversized value
    means "no limit" — call sites default to bounded reads (get_task_context:
    20, get_task: 5), but unlimited reads remain available.
    """
    if not mem_path.exists():
        return "", 0, False
    text = mem_path.read_text(encoding="utf-8").strip()
    summary, entries = _split_summary_and_entries(text)
    total = len(entries)
    if max_memories is None or max_memories <= 0 or max_memories >= total:
        return text, total, False
    body = "\n\n".join(entries[-max_memories:])
    rendered = f"{summary}\n\n{body}" if summary else body
    return rendered, total, True


def _parse_max_memories(arguments: Dict[str, Any], default: int) -> Optional[int]:
    """Parse the optional max_memories argument; invalid values mean no limit."""
    raw = arguments.get("max_memories")
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def append_task_memories_direct(output_dir: Path, task_id: str, contents: List[str]) -> int:
    """Direct-write distilled task memories into memories.md (no confirm gate).

    ADR-0002: task memories are task-scoped progress knowledge — noise cost is
    bounded by the task's lifetime and never enters the retrieval index — so
    distillation writes them directly (timestamp-headed entries, atomic
    append), unlike notes which keep the confirm_note quality gate. Ghost
    task_id (task deleted after capture) is tolerated: returns 0, no write.

    Returns the number of entries actually appended.
    """
    if not task_id or not contents:
        return 0
    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return 0
    mem_path = _memories_path(output_dir, task_id)
    written = 0
    for c in contents:
        c = str(c or "").strip()
        if not c:
            continue
        _append_memory_atomic(mem_path, c)
        written += 1
    return written


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def handle_create_task(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Create a new task. Duplicate titles are rejected; no rename is supported."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    title = str(arguments.get("title") or "").strip()
    if not title:
        return json.dumps({"error": "title is required to create a task."})

    task_id = _slugify(title)
    if not task_id:
        return json.dumps({"error": "title did not produce a usable task id."})

    tasks = _read_index(output_dir)
    if _find_by_title(tasks, title):
        return json.dumps({"error": f"A task titled '{title}' already exists."})
    if _find_by_id(tasks, task_id):
        return json.dumps({"error": f"A task with id '{task_id}' already exists."})

    description = str(arguments.get("description") or "").strip()
    task = {
        "id": task_id,
        "title": title,
        "status": "active",
        "created_at": _now_iso(),
    }
    tasks.append(task)
    _write_index(output_dir, tasks)
    _write_task_file(output_dir, task, description)

    return json.dumps(
        {
            "ok": True,
            "task": task,
            "description": description,
        },
        ensure_ascii=False,
    )


def handle_list_tasks(arguments: Dict[str, Any], store: SessionStore) -> str:
    """List tasks, optionally filtered by status ('active'/'completed')."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    tasks = _read_index(output_dir)
    status = arguments.get("status")
    if status:
        status = str(status).strip()
        tasks = [t for t in tasks if t.get("status") == status]

    return json.dumps({"ok": True, "tasks": tasks}, ensure_ascii=False)


def handle_get_task(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Return a single task's details plus its most recent memories.

    ``max_memories`` (default 5) bounds the memories payload: only the most
    recent entries are returned, with ``memories_total`` / ``memories_truncated``
    telling the caller whether older entries exist (pass a larger value to page
    back through them). Task detail — not full history — is this tool's job;
    ``get_task_context`` is the full-history reader.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    tasks = _read_index(output_dir)
    task = _find_by_id(tasks, task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    task_file = _task_path(output_dir, task_id)
    description = ""
    if task_file.exists():
        text = task_file.read_text(encoding="utf-8")
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?(.*)", text, re.DOTALL)
        description = (m.group(1) if m else text).strip()

    memories, mem_total, mem_truncated = _load_memories_limited(
        _memories_path(output_dir, task_id),
        _parse_max_memories(arguments, default=5),
    )

    return json.dumps(
        {
            "ok": True,
            "task": task,
            "description": description,
            "memories": memories,
            "memories_total": mem_total,
            "memories_truncated": mem_truncated,
        },
        ensure_ascii=False,
    )


def handle_complete_task(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Mark an active task as completed."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    tasks = _read_index(output_dir)
    task = _find_by_id(tasks, task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})
    if task.get("status") == "completed":
        return json.dumps({"ok": True, "task": task, "note": "Task was already completed."})

    task["status"] = "completed"
    task["completed_at"] = _now_iso()
    _write_index(output_dir, tasks)

    task_file = _task_path(output_dir, task_id)
    if task_file.exists():
        text = task_file.read_text(encoding="utf-8")
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?(.*)", text, re.DOTALL)
        body = (m.group(1) if m else "").strip()
        _write_task_file(output_dir, task, body)

    return json.dumps({"ok": True, "task": task}, ensure_ascii=False)


def handle_delete_task(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Delete a task, its directory, and any session bindings pointing at it."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    tasks = _read_index(output_dir)
    task = _find_by_id(tasks, task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    # 1. Remove from index.
    remaining = [t for t in tasks if t.get("id") != task_id]
    _write_index(output_dir, remaining)

    # 2. Remove the task directory tree (task.md + memories.md).
    import shutil

    task_dir = _tasks_dir(output_dir) / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)

    # 3. Cascade: drop session bindings that point at this task.
    cleared_bindings = 0
    bdir = _bindings_dir(output_dir)
    if bdir.exists():
        for bf in bdir.glob("*.json"):
            try:
                data = json.loads(bf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("task_id") == task_id:
                try:
                    bf.unlink()
                    cleared_bindings += 1
                except OSError:
                    logger.warning("Failed to remove binding %s", bf)

    return json.dumps(
        {
            "ok": True,
            "deleted": task_id,
            "cleared_bindings": cleared_bindings,
        },
        ensure_ascii=False,
    )


def handle_set_session_task(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Bind a source (IDE) session id to a task id.

    The binding is consumed by capture_conversation (stamps task_id into raw
    frontmatter). The binding file is intentionally NOT auto-deleted here —
    the caller decides when the association is done.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    source_session_id = str(arguments.get("source_session_id") or "").strip()
    task_id = str(arguments.get("task_id") or "").strip()
    if not source_session_id:
        return json.dumps({"error": "source_session_id is required."})
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    # Validate the task exists (unlike query_wiki, bindings should not dangle).
    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    bdir = _bindings_dir(output_dir)
    bdir.mkdir(parents=True, exist_ok=True)
    binding = {"task_id": task_id, "bound_at": _now_iso()}
    p = bdir / f"{source_session_id}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8")
    _atomic_replace_with_retry(tmp, p)

    return json.dumps(
        {
            "ok": True,
            "source_session_id": source_session_id,
            "task_id": task_id,
        },
        ensure_ascii=False,
    )


def handle_add_task_memory(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Append a memory entry to a task's memories.md (atomic, append-only)."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    content = str(arguments.get("content") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})
    if not content:
        return json.dumps({"error": "content is required."})

    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    _append_memory_atomic(_memories_path(output_dir, task_id), content)

    return json.dumps(
        {
            "ok": True,
            "task_id": task_id,
            "appended_chars": len(content),
        },
        ensure_ascii=False,
    )


def handle_get_task_context(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Aggregate a task's full context: task.md + memories.md + related notes.

    Related notes are discovered by scanning repowiki/notes/ for files whose
    frontmatter carries a matching ``task_id`` (top-level or under metadata).
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    tasks = _read_index(output_dir)
    task = _find_by_id(tasks, task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    description = ""
    task_file = _task_path(output_dir, task_id)
    if task_file.exists():
        text = task_file.read_text(encoding="utf-8")
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?(.*)", text, re.DOTALL)
        description = (m.group(1) if m else text).strip()

    # Bounded memories read (P0): default keeps the most recent 20 entries;
    # memories_total / memories_truncated let the host agent page back if it
    # needs older context. compaction_due is the pull-style signal that the
    # file exceeded the compaction thresholds AND has entries beyond the keep
    # window (i.e. compaction would actually help) — run compact_task_memories.
    memories, mem_total, mem_truncated = _load_memories_limited(
        _memories_path(output_dir, task_id),
        _parse_max_memories(arguments, default=20),
    )
    mem_path = _memories_path(output_dir, task_id)
    mem_bytes = mem_path.stat().st_size if mem_path.exists() else 0
    compaction_due = _compaction_needed(mem_total, mem_bytes)

    # Discover related notes by frontmatter task_id. The ``status`` field lets
    # the host agent tell drafts apart from confirmed knowledge when injecting
    # this context (draft → must be labelled "待确认", never cited as settled).
    related_notes: List[Dict[str, str]] = []
    notes_dir = output_dir / "notes"
    if notes_dir.exists():
        for nf in sorted(notes_dir.glob("*.md")):
            try:
                text = nf.read_text(encoding="utf-8")
            except OSError:
                continue
            if _extract_fm(text, "task_id") != task_id:
                continue
            title = _extract_fm(text, "title") or nf.stem
            status = _extract_fm(text, "status") or "stable"
            related_notes.append({"relpath": nf.name, "title": title, "status": status})

    # Pending (not-yet-distilled) raw captures bound to this task. This is the
    # deterministic catch-up distillation trigger: pending_raw_count > 0 means
    # the agent should run distill_conversation(mode="prepare", task_id=...)
    # BEFORE answering the user's actual question (see sessionStart hook).
    # The listing is truncated to keep the context payload bounded.
    pending_raws = pending_raws_by_task(output_dir).get(task_id, [])
    _MAX_PENDING_SHOWN = 10

    def _raw_friction_score(raw_dir: Path, relpath: str) -> int:
        """Line-scan a raw conv file's top-level ``friction_score:`` (0 default).

        Bounded to the shown entries (≤ _MAX_PENDING_SHOWN files) so the cost
        stays negligible. Any read/parse failure degrades to 0.
        """
        try:
            text = (raw_dir / relpath).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return 0
        m = re.search(r"^friction_score:\s*(-?\d+)", text, re.MULTILINE)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except ValueError:
            return 0

    raw_dir = output_dir / "raw"
    pending_payload = [
        {
            "relpath": e["relpath"],
            "captured_at": e["captured_at"],
            # K-line: friction score as the catch-up distillation priority hint
            # (score >= 20 → the conversation likely holds a worth-keeping lesson).
            "friction_score": _raw_friction_score(raw_dir, e["relpath"]),
        }
        for e in pending_raws[:_MAX_PENDING_SHOWN]
    ]

    # P2 (§4.5): aggregation counters surfaced next to pending_raw_count —
    # a pull-style signal that consolidation may be due. Best-effort: any
    # failure omits the section without affecting task context restoration.
    aggregation = None
    try:
        from codewiki.mcp.tools import aggregation_state as agg

        aggregation = agg.aggregation_summary(output_dir)
    except Exception:
        pass

    return json.dumps(
        {
            "ok": True,
            "task": task,
            "description": description,
            "memories": memories,
            "memories_total": mem_total,
            "memories_truncated": mem_truncated,
            "compaction_due": compaction_due,
            "related_notes": related_notes,
            "pending_raw_count": len(pending_raws),
            "pending_raws": pending_payload,
            "pending_raws_truncated": len(pending_raws) > _MAX_PENDING_SHOWN,
            **({"aggregation": aggregation} if aggregation else {}),
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# Memory compaction (P1 — see docs/任务记忆存储与加载扩展性设计方案.md §5.2)
# --------------------------------------------------------------------------- #

_COMPACT_INSTRUCTION = (
    "阅读 entries_to_compress（若 existing_summary 非空，它包含此前压缩的旧摘要，"
    "新摘要应覆盖其内容），生成一份任务早期记忆的中文 Markdown 摘要，"
    "不超过 {max_chars} 字。摘要应覆盖：关键事实与已完成决策、未决事项、"
    "仍可能影响后续工作的上下文（历史坑、约定、外部依赖）。"
    "丢掉纯过程性细节，保留结论性信息。"
    "完成后调用 compact_task_memories(mode='submit', task_id=..., summary=...)。"
)


def _compact_threshold_state(
    output_dir: Path, task_id: str
) -> Tuple[str, str, List[str], int, bool]:
    """Load (text, summary_section, entries, file_bytes, compaction_needed)."""
    mem_path = _memories_path(output_dir, task_id)
    if not mem_path.exists():
        return "", "", [], 0, False
    text = mem_path.read_text(encoding="utf-8").strip()
    summary, entries = _split_summary_and_entries(text)
    mem_bytes = mem_path.stat().st_size
    needed = _compaction_needed(len(entries), mem_bytes)
    return text, summary, entries, mem_bytes, needed


def handle_compact_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Compress a task's old memories into a summary section (two-phase).

    Stateless Mode-C design (mirrors distill_conversation): this tool never
    calls an LLM. ``mode="prepare"`` (default) returns the entries to compress
    plus instructions — the CALLER (host agent / subagent) writes the summary.
    ``mode="submit"`` with that ``summary`` performs the deterministic rewrite:

      memories.md    := "## 早期记忆（摘要）" + summary + archive pointer
                        + the most recent _COMPACTION_KEEP entries (full text)
      memories-archive.md (append-only) := the compressed entries' originals,
                        legacy heading-less entries get a synthetic heading

    Failure ordering: the archive replace happens BEFORE the memories replace,
    so a crash between the two leaves the originals duplicated in the archive
    (safe, retry-able) — never lost. Compaction output is written directly,
    without a confirm gate: the operation is reversible (originals live in the
    archive; re-running regenerates), which the confirm philosophy does not
    cover (ADR-0001 / design doc §3 Q8).

    Idempotent: when the file is below the thresholds or has no entries beyond
    the keep window, both modes return ``compaction_needed: false`` as a no-op.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required."})

    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    mode = str(arguments.get("mode") or "prepare").strip().lower()
    if mode not in ("prepare", "submit"):
        return json.dumps({"error": "mode must be 'prepare' or 'submit'."})

    text, summary, entries, mem_bytes, needed = _compact_threshold_state(output_dir, task_id)
    if not needed:
        return json.dumps(
            {
                "ok": True,
                "task_id": task_id,
                "compaction_needed": False,
                "entries_total": len(entries),
                "note": "Below compaction thresholds or nothing beyond the keep window; no-op.",
            },
            ensure_ascii=False,
        )

    compress = entries[:-_COMPACTION_KEEP]
    keep = entries[-_COMPACTION_KEEP:]

    if mode == "prepare":
        return json.dumps(
            {
                "ok": True,
                "mode": "prepare",
                "task_id": task_id,
                "compaction_needed": True,
                "entries_to_compress": compress,
                "existing_summary": summary,
                "keep_recent": _COMPACTION_KEEP,
                "summary_max_chars": _COMPACTION_SUMMARY_MAX_CHARS,
                "summary_heading": _SUMMARY_HEADING,
                "instruction": _COMPACT_INSTRUCTION.format(max_chars=_COMPACTION_SUMMARY_MAX_CHARS),
            },
            ensure_ascii=False,
        )

    # mode == "submit": apply the caller-authored summary.
    new_summary = str(arguments.get("summary") or "").strip()
    if not new_summary:
        return json.dumps(
            {"error": "summary is required for mode='submit' (produce it via mode='prepare')."}
        )
    if len(new_summary) > _COMPACTION_SUMMARY_MAX_CHARS:
        return json.dumps(
            {
                "error": (
                    f"summary exceeds {_COMPACTION_SUMMARY_MAX_CHARS} chars "
                    f"(got {len(new_summary)}); shorten it."
                )
            }
        )

    # NOTE: the split is recomputed at submit time. Entries appended between
    # prepare and submit land in the keep window; the compress set may gain the
    # entry that was previously the oldest kept one — the caller's summary may
    # not cover it. Tolerated: append-only writes are rare mid-compaction and
    # the entry is preserved verbatim in the archive either way.
    date = datetime.now().strftime("%Y-%m-%d")
    pointer = f"> 原文归档于 {_ARCHIVE_FILENAME}，截至 {date}，共 {len(compress)} 条。"
    new_text = f"{_SUMMARY_HEADING}\n\n{new_summary}\n\n{pointer}\n\n" + "\n\n".join(keep) + "\n"

    # Archive block: verbatim entries; legacy heading-less entries get a
    # synthetic heading so the archive stays scannable (and re-parseable).
    archive_parts: List[str] = []
    for e in compress:
        if e.startswith("### "):
            archive_parts.append(e)
        else:
            archive_parts.append("### 历史条目（存量格式，无时间戳）\n\n" + e)
    archive_block = "\n\n".join(archive_parts) + "\n"

    # Safe failure ordering: archive replace first (superset — no information
    # loss), then the memories rewrite. A failure between the two leaves the
    # originals in BOTH files; a retry re-archives (duplicate) but never loses.
    archive_path = _archive_path(output_dir, task_id)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing_archive = ""
    if archive_path.exists():
        existing_archive = archive_path.read_text(encoding="utf-8").rstrip("\n")
    new_archive = (existing_archive + "\n\n" if existing_archive else "") + archive_block
    archive_tmp = archive_path.with_suffix(".tmp")
    archive_tmp.write_text(new_archive, encoding="utf-8")
    _atomic_replace_with_retry(archive_tmp, archive_path)

    mem_path = _memories_path(output_dir, task_id)
    mem_tmp = mem_path.with_suffix(".tmp")
    mem_tmp.write_text(new_text, encoding="utf-8")
    _atomic_replace_with_retry(mem_tmp, mem_path)

    return json.dumps(
        {
            "ok": True,
            "mode": "submit",
            "task_id": task_id,
            "compressed": len(compress),
            "kept": len(keep),
            "archive": _ARCHIVE_FILENAME,
            "memories_total": len(keep),
        },
        ensure_ascii=False,
    )
