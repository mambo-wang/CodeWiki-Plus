"""MCP tool: task_manager — task CRUD + per-task memory store.

This module adds a *task memory layer* alongside the wiki knowledge layer
(``notes/`` + ``wiki/``) and the team-memory fusion layer (``raw/``). A task is
a long-running unit of work that accumulates distilled memories across many
sessions:

    repowiki/tasks/
      .index.json             # task index: [{id, title, status, created_at, ...}]
      <task_id>/
        task.md               # task description + status (frontmatter + body)
        memories.md           # accumulated task memories (append-only)
        pending-memories.json # staged (unconfirmed) distilled memories

Session bindings live under ``repowiki/.meta/task_bindings/<source_session_id>.json``
so an IDE session can be associated with a task. ``capture_conversation`` then
stamps ``task_id`` into raw frontmatter, ``distill_conversation`` routes distilled
memories back to the task, and ``get_task_context`` aggregates the task's knowledge
so the next session can pick up where it left off.

Distilled memories are NOT appended to ``memories.md`` directly: they are staged in
``pending-memories.json`` first, then the host agent presents them to the user and
calls ``confirm_task_memories`` (persist) or ``reject_task_memories`` (drop) — the
same quality gate notes get via confirm_note/reject_note.

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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    os.replace(tmp, p)


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
    os.replace(tmp, p)


def _append_memory_atomic(path: Path, content: str) -> None:
    """Append a memory entry to memories.md using an atomic read-modify-write.

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
    entry = (content or "").strip()
    new_content = existing + entry + "\n"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, path)


def _pending_memories_path(output_dir: Path, task_id: str) -> Path:
    """Path to a task's staged (unconfirmed) distilled memories."""
    return _tasks_dir(output_dir) / task_id / "pending-memories.json"


def _read_pending_memories(output_dir: Path, task_id: str) -> List[Dict[str, Any]]:
    """Read pending memories as a list of entries; [] when absent/corrupt."""
    p = _pending_memories_path(output_dir, task_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        mems = data.get("memories", []) if isinstance(data, dict) else []
        return [m for m in mems if isinstance(m, dict)]
    except (json.JSONDecodeError, OSError):
        logger.warning("Pending memories unreadable at %s; treating as empty.", p)
        return []


def _write_pending_memories(
    output_dir: Path, task_id: str, memories: List[Dict[str, Any]]
) -> None:
    """Atomically write a task's pending memories (temp file + os.replace)."""
    p = _pending_memories_path(output_dir, task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"task_id": task_id, "memories": memories}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, p)


def _ids_mean_all(memory_ids: Any) -> bool:
    """Treat empty/omitted memory_ids (or ["*"]) as 'all pending memories'."""
    if not isinstance(memory_ids, list) or not memory_ids:
        return True
    return any(str(i).strip() == "*" for i in memory_ids)


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

    return json.dumps({
        "ok": True,
        "task": task,
        "description": description,
    }, ensure_ascii=False)


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
    """Return a single task's details plus its accumulated memories."""
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

    memories = ""
    mem_path = _memories_path(output_dir, task_id)
    if mem_path.exists():
        memories = mem_path.read_text(encoding="utf-8").strip()

    pending = _read_pending_memories(output_dir, task_id)
    return json.dumps({
        "ok": True,
        "task": task,
        "description": description,
        "memories": memories,
        "pending_memories": pending,
    }, ensure_ascii=False)


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

    return json.dumps({
        "ok": True,
        "deleted": task_id,
        "cleared_bindings": cleared_bindings,
    }, ensure_ascii=False)


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
    os.replace(tmp, p)

    return json.dumps({
        "ok": True,
        "source_session_id": source_session_id,
        "task_id": task_id,
    }, ensure_ascii=False)


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

    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "appended_chars": len(content),
    }, ensure_ascii=False)


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

    memories = ""
    mem_path = _memories_path(output_dir, task_id)
    if mem_path.exists():
        memories = mem_path.read_text(encoding="utf-8").strip()

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
    pending_payload = [
        {"relpath": e["relpath"], "captured_at": e["captured_at"]}
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

    return json.dumps({
        "ok": True,
        "task": task,
        "description": description,
        "memories": memories,
        "pending_memories": _read_pending_memories(output_dir, task_id),
        "related_notes": related_notes,
        "pending_raw_count": len(pending_raws),
        "pending_raws": pending_payload,
        "pending_raws_truncated": len(pending_raws) > _MAX_PENDING_SHOWN,
        **({"aggregation": aggregation} if aggregation else {}),
    }, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Pending-memory confirmation gate
# --------------------------------------------------------------------------- #

def handle_stage_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Stage distilled task memories in a pending area awaiting user confirmation.

    Distilled memories are NOT appended to ``memories.md`` directly. They land in
    ``repowiki/tasks/<task_id>/pending-memories.json`` first; the host agent
    presents them to the user, then calls ``confirm_task_memories`` to persist
    (atomic append to memories.md) or ``reject_task_memories`` to drop. Content
    already staged for this task is skipped (best-effort dedup).
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

    pending = _read_pending_memories(output_dir, task_id)
    raw = arguments.get("memories")
    if not isinstance(raw, list) or not raw:
        return json.dumps({
            "ok": True,
            "task_id": task_id,
            "staged": 0,
            "pending_total": len(pending),
            "pending": pending,
        }, ensure_ascii=False)

    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    source_raw = str(arguments.get("source_raw") or "").strip() or None
    existing = {str(m.get("content") or "").strip() for m in pending}
    now = _now_iso()
    staged = 0
    for m in raw:
        content = str(m or "").strip()
        if not content or content in existing:
            continue
        pending.append({
            "id": f"mem-{uuid.uuid4().hex[:12]}",
            "content": content,
            "source_raw": source_raw,
            "staged_at": now,
        })
        existing.add(content)
        staged += 1
    _write_pending_memories(output_dir, task_id, pending)

    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "staged": staged,
        "pending_total": len(pending),
        "pending": pending,
    }, ensure_ascii=False)


def handle_list_pending_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """List a task's pending (staged, unconfirmed) memories.

    Like ``query_wiki``, this does not validate the task exists — ghost task ids
    simply return an empty pending list.
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

    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "pending": _read_pending_memories(output_dir, task_id),
    }, ensure_ascii=False)


def handle_confirm_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Confirm pending memories: append them to memories.md and drop from pending.

    ``memory_ids`` selects which pending entries to confirm. Omit it (or pass
    ``["*"]``) to confirm ALL pending. Confirmed entries land via the same atomic
    append-only write used by ``add_task_memory``.
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

    pending = _read_pending_memories(output_dir, task_id)
    if _ids_mean_all(arguments.get("memory_ids")):
        chosen = pending
        remaining: List[Dict[str, Any]] = []
    else:
        id_set = {str(i).strip() for i in arguments.get("memory_ids", []) if str(i).strip()}
        chosen = [m for m in pending if m.get("id") in id_set]
        remaining = [m for m in pending if m.get("id") not in id_set]

    confirmed = 0
    mem_path = _memories_path(output_dir, task_id)
    for m in chosen:
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        _append_memory_atomic(mem_path, content)
        confirmed += 1

    _write_pending_memories(output_dir, task_id, remaining)
    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "confirmed": confirmed,
        "remaining": remaining,
    }, ensure_ascii=False)


def handle_reject_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Reject pending memories: drop them from the pending area without persisting.

    ``memory_ids`` selects which pending entries to discard. Omit it (or pass
    ``["*"]``) to reject ALL pending. ``reason`` is optional and informational
    only — rejected entries are simply removed.
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

    pending = _read_pending_memories(output_dir, task_id)
    if _ids_mean_all(arguments.get("memory_ids")):
        remaining: List[Dict[str, Any]] = []
        rejected = len(pending)
    else:
        id_set = {str(i).strip() for i in arguments.get("memory_ids", []) if str(i).strip()}
        remaining = [m for m in pending if m.get("id") not in id_set]
        rejected = len(pending) - len(remaining)

    _write_pending_memories(output_dir, task_id, remaining)
    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "rejected": rejected,
        "remaining": remaining,
    }, ensure_ascii=False)
