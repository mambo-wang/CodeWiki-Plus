"""MCP tool: task_manager — task CRUD + per-task memory store.

This module adds a *task memory layer* alongside the wiki knowledge layer
(``notes/`` + ``wiki/``) and the team-memory fusion layer (``raw/``). A task is
a long-running unit of work that accumulates distilled memories across many
sessions:

    repowiki/tasks/
      .index.json             # task index: [{id, title, status, created_at, ...}]
      <task_id>/
        task.md               # task description + status (frontmatter + body)
        memories/<user_id>.md # per-user task memories (append-only; entries
                              #   carry "### YYYY-MM-DD HH:MM" headings — legacy
                              #   heading-less files parse via blank-line fallback)
        memories-archive/<user_id>.md  # per-user compacted originals
        memories.md           # legacy single-file store (read-only compat; hot
                              #   layer together with the current user's file,
                              #   converges into it on first compaction)
        memories-archive.md   # legacy archive (read-only)

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
  - Per-user memory files are append-only; each user writes ONLY their own
    ``memories/<user_id>.md`` (git-level conflict isolation, mirroring the
    telemetry per-user jsonl pattern). Concurrent writers are serialized via an
    atomic write (temp file + ``os.replace``).
  - Loading is layered (hot/warm): the current user's file (+ legacy) loads in
    full; other users' files contribute only their summary section and a couple
    of recent entries (with budget-based degradation to one-line hints).
  - Compaction is file-domain and author-exclusive: the caller compacts only
    their own file (+ the ownerless legacy file, which converges into the
    caller's file). Nobody ever rewrites another user's file.
  - ``query_wiki`` never validates task existence — ghost ``task_id`` references
    are allowed (the task may have been deleted; the note stays).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.store_bridge import (
    pending_raws_by_task,
    resolve_output_dir as _resolve_output_dir,
)
from codewiki.src.store import slugify as _slugify
from codewiki.src.store import (
    KnowledgeStore,
    SUMMARY_HEADING,
    entry_id,
    entry_is_superseded,
    entry_sort_key,
    locked_rmw,
    locked_write,
    new_entry_id,
    parse_frontmatter,
    split_entries,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #


def _read_index(output_dir: Path) -> List[Dict[str, Any]]:
    """Read the task index (self-healing) — delegates to the shared store."""
    return KnowledgeStore(output_dir).read_task_index()


def _write_index(output_dir: Path, tasks: List[Dict[str, Any]]) -> None:
    """Atomically write the task index — delegates to the shared store."""
    KnowledgeStore(output_dir).write_task_index(tasks)


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
    return KnowledgeStore(output_dir).task_path(task_id)


def _memories_path(output_dir: Path, task_id: str) -> Path:
    """Legacy single-file memory store path (read-only compat; hot layer)."""
    return KnowledgeStore(output_dir).legacy_memory_path(task_id)


_MEMORIES_DIRNAME = "memories"
_ARCHIVE_DIRNAME = "memories-archive"
# Owner label used for the ownerless legacy file's archive. Cannot collide with
# a real user_id in practice (sanitized ids derive from email/name/override).
_LEGACY_OWNER = "legacy"


def _memories_path_for(output_dir: Path, task_id: str, owner: str) -> Path:
    """Per-user memory file path — the ONLY write target for that user."""
    return KnowledgeStore(output_dir).memory_path_for(task_id, owner)


def _archive_path_for(output_dir: Path, task_id: str, owner: str) -> Path:
    """Per-user archive path (compacted originals). Legacy → 'legacy.md'."""
    return KnowledgeStore(output_dir).archive_path_for(task_id, owner)


def _current_user_id() -> str:
    """Current user's namespace id (shared with telemetry; see src/config.py)."""
    from codewiki.src.config import user_id

    return user_id()


def _collect_memory_files(
    output_dir: Path, task_id: str, uid: str
) -> Tuple[Path, Path, List[Path]]:
    """(own_path, legacy_path, other_paths) — delegates to the shared store."""
    return KnowledgeStore(output_dir).collect_memory_files(task_id, uid)


_ENTRY_TS_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")


def _entry_sort_key(entry: str) -> Tuple[int, str]:
    """Chronological sort key — delegates to the shared store implementation."""
    return entry_sort_key(entry)


def _extract_fm(text: str, key: str) -> Optional[str]:
    """Extract a frontmatter value (top-level or nested under ``metadata:``).

    Delegates to the shared store parser (json-decoded values, so no quote
    drift). Returns None when the key is absent or empty.
    """
    if not text:
        return None
    fm, _ = parse_frontmatter(text)
    v = fm.get(key)
    if v is None and isinstance(fm.get("metadata"), dict):
        v = fm["metadata"].get(key)
    if v is None or v == "":
        return None
    return v if isinstance(v, str) else str(v)


# --------------------------------------------------------------------------- #
# Task file write helpers
# --------------------------------------------------------------------------- #


def _write_task_file(output_dir: Path, task: Dict[str, Any], description: str) -> None:
    KnowledgeStore(output_dir).write_task_file(task, description)


# Compaction thresholds live in limits.py (ADR-0013 single-source module);
# re-exported here under their historical private names so existing imports
# and tests keep working.
from codewiki.mcp.tools.limits import (  # noqa: E402
    COMPACTION_KEEP as _COMPACTION_KEEP,
    COMPACTION_SUMMARY_MAX_CHARS as _COMPACTION_SUMMARY_MAX_CHARS,
    COMPACTION_THRESHOLD_BYTES as _COMPACTION_THRESHOLD_BYTES,
    COMPACTION_THRESHOLD_COUNT as _COMPACTION_THRESHOLD_COUNT,
)
from codewiki.mcp.tools.limits import (  # noqa: E402
    COMPACTION_LEVEL_ORANGE as _COMPACTION_LEVEL_ORANGE,
    COMPACTION_LEVEL_YELLOW as _COMPACTION_LEVEL_YELLOW,
)

_SUMMARY_HEADING = SUMMARY_HEADING  # re-export of the shared store constant


def _split_memories(text: str) -> List[str]:
    """Split memories.md content into entries — delegates to the shared store."""
    return split_entries(text)


def _compaction_needed(total_entries: int, mem_bytes: int) -> bool:
    """Whether compaction would actually help.

    Requires entries beyond the keep window (otherwise there is nothing to
    compress — a single oversized entry inside the keep window cannot be
    compacted away) AND at least one threshold exceeded.
    """
    return total_entries > _COMPACTION_KEEP and (
        total_entries > _COMPACTION_THRESHOLD_COUNT or mem_bytes > _COMPACTION_THRESHOLD_BYTES
    )


# ADR-0009 D9: compaction level — yellow/orange/red at 75%/87.5%/100% of the
# existing thresholds (count and bytes, whichever is worse).


def _compaction_level(total_entries: int, mem_bytes: int) -> str:
    """ADR-0009 D9: green/yellow/orange/red signal over the hot layer.

    ``compaction_due`` (red) keeps its existing semantics — beyond the keep
    window AND at least one threshold exceeded. yellow/orange are pure
    observe signals (no behaviour change), interpolated from the same
    thresholds so no new judgement criteria are introduced. Boundaries are
    inclusive (D9: yellow ≥75%, orange ≥87.5% of a threshold).
    """
    if _compaction_needed(total_entries, mem_bytes):
        return "red"
    for level, fraction in (
        ("orange", _COMPACTION_LEVEL_ORANGE),
        ("yellow", _COMPACTION_LEVEL_YELLOW),
    ):
        if (
            total_entries >= _COMPACTION_THRESHOLD_COUNT * fraction
            or mem_bytes >= _COMPACTION_THRESHOLD_BYTES * fraction
        ):
            return level
    return "green"


# Layered loading (multi-user split design §4.3): warm layer shape constants.
_WARM_RECENT_ENTRIES = 2  # per other author: recent entries injected (Q11)
_WARM_ENTRY_BUDGET = 2048  # per other author: chars before degrading (Q12)
_HINT_LINE_MAX = 60  # degraded hint: first-content-line truncation
_WARM_SECTION_HEADING = "## 其他成员记忆"


def _warm_hint(owner: str, entry: str) -> str:
    """One-line degraded hint for a warm entry (Q12: keep the clue, drop bulk)."""
    ts = ""
    m = _ENTRY_TS_RE.match(entry)
    if m:
        ts = m.group(1)[5:10]  # MM-DD
    first = ""
    for line in entry.splitlines():
        line = line.strip()
        if line and not line.startswith("### "):
            first = line
            break
    if len(first) > _HINT_LINE_MAX:
        first = first[:_HINT_LINE_MAX] + "…"
    return f"- @{owner} {ts}：{first} … → {_MEMORIES_DIRNAME}/{owner}.md"


def _parse_memory_file(path: Path) -> Optional[Tuple[str, str, List[str], int]]:
    """(raw_text, summary_section, entries, file_bytes); None when missing."""
    return KnowledgeStore.parse_memory_file(path)


def _render_warm_author(owner: str, summary: str, entries: List[str], include_entries: bool) -> str:
    """Render one other author's warm block: summary + recent entries / hints."""
    parts = [f"### @{owner}"]
    if summary:
        # Drop the canonical "## 早期记忆（摘要）" heading line; the @owner
        # heading above already frames the section.
        body = summary[len(_SUMMARY_HEADING) :].strip()
        if body:
            parts.append(body)
    if include_entries and entries:
        recent = sorted(entries, key=_entry_sort_key)[-_WARM_RECENT_ENTRIES:]
        kept: List[str] = []
        hints: List[Tuple[Tuple[int, str], str]] = []
        budget = _WARM_ENTRY_BUDGET
        # Newest first: keep entries that fit the per-author budget, degrade
        # the rest to one-line hints. The summary never degrades (Q12).
        for e in reversed(recent):
            if len(e) <= budget:
                kept.append(e)
                budget -= len(e)
            else:
                hints.append((_entry_sort_key(e), _warm_hint(owner, e)))
        parts.extend(sorted(kept, key=_entry_sort_key))
        parts.extend(h for _, h in sorted(hints, key=lambda x: x[0]))
    return "\n\n".join(p for p in parts if p)


def _entry_display_ids(entries: List[str]) -> Dict[int, str]:
    """ADR-0009: display id per entry (by index) — the persistent id from the
    heading when present, else a lazy ordinal ``#e01`` assigned in
    chronological order. The file on disk is never rewritten; the ordinal is
    stable as long as the file is unchanged (same rule as supersede matching
    in the store)."""
    ids: Dict[int, str] = {}
    ordinal = 0
    order = sorted(range(len(entries)), key=lambda i: _entry_sort_key(entries[i]))
    for i in order:
        pid = entry_id(entries[i])
        if pid:
            ids[i] = pid
        else:
            ordinal += 1
            ids[i] = f"#e{ordinal:02d}"
    return ids


def _annotate_entry(entry: str, display_id: str) -> str:
    """Render an entry with its display id on the heading line (lazy ordinals
    only — persistent ids are already on the heading)."""
    if entry_id(entry):
        return entry
    m = _ENTRY_TS_RE.match(entry)
    if m:
        return entry.replace(m.group(0), f"{m.group(0)} {display_id}", 1)
    return entry


def _load_memories_layered(
    output_dir: Path, task_id: str, max_memories: Optional[int], include_warm_entries: bool
) -> Tuple[str, int, bool, bool]:
    """Layered hot/warm read of a task's memories.

    Hot layer (current user's file + legacy memories.md): full summary section
    + most recent ``max_memories`` entries — a task whose only hot file is the
    legacy file renders byte-identically to the pre-split single-file reader.
    Warm layer (each other user's file): summary + last _WARM_RECENT_ENTRIES
    entries, degraded to one-line entries past the per-author budget.

    ADR-0009: superseded entries are filtered out of the hot layer injection;
    lazy ordinal ids are annotated onto legacy headings so the agent can
    reference them for supersede.

    Returns (rendered_text, total_entries_all_files, hot_truncated,
    compaction_due, compaction_level). ``compaction_due`` and
    ``compaction_level`` are computed over the HOT layer only —
    only the current user's own (+ legacy) files are theirs to compact.
    """
    uid = _current_user_id()
    own_path, legacy_path, other_paths = _collect_memory_files(output_dir, task_id, uid)
    own = _parse_memory_file(own_path)
    leg = _parse_memory_file(legacy_path)

    own_has = own is not None and (own[1] or own[2])
    leg_has = leg is not None and (leg[1] or leg[2])

    hot_entries = (own[2] if own else []) + (leg[2] if leg else [])
    hot_total = len(hot_entries)
    hot_bytes = (own[3] if own else 0) + (leg[3] if leg else 0)
    compaction_due = _compaction_needed(hot_total, hot_bytes)
    compaction_level = _compaction_level(hot_total, hot_bytes)

    # ADR-0009: display ids over the FULL hot layer (before filtering and
    # truncation), so an entry's lazy ordinal does not shift when superseded
    # entries disappear or max_memories truncates.
    display_ids = _entry_display_ids(hot_entries)
    live_idx = [i for i, e in enumerate(hot_entries) if not entry_is_superseded(e)]
    live = [hot_entries[i] for i in live_idx]

    def _render_hot(summary: str, entries: List[str], idxs: List[int]) -> Tuple[str, int, bool]:
        total = len(entries)
        if max_memories is None or max_memories <= 0 or max_memories >= total:
            kept, kept_idx, truncated = entries, idxs, False
        else:
            kept, kept_idx, truncated = entries[-max_memories:], idxs[-max_memories:], True
        annotated = [_annotate_entry(e, display_ids[i]) for e, i in zip(kept, kept_idx)]
        body = "\n\n".join(annotated)
        rendered = f"{summary}\n\n{body}" if summary else body
        return rendered, total, truncated

    if own_has and not leg_has:
        hot_rendered, hot_entries_total, hot_truncated = _render_hot(own[1], live, live_idx)
    elif leg_has and not own_has:
        hot_rendered, hot_entries_total, hot_truncated = _render_hot("", live, live_idx)
    elif own_has and leg_has:
        # Both hot files: merge chronologically. Legacy summary is annotated;
        # the current user's own summary stays canonical.
        summaries: List[str] = []
        if own[1]:
            summaries.append(own[1])
        if leg[1]:
            summaries.append(leg[1].replace(_SUMMARY_HEADING, _SUMMARY_HEADING + "（legacy）", 1))
        order = sorted(range(len(live)), key=lambda i: _entry_sort_key(live[i]))
        merged = [live[i] for i in order]
        merged_idx = [live_idx[i] for i in order]
        if max_memories is None or max_memories <= 0 or max_memories >= len(merged):
            kept, kept_idx, hot_truncated = merged, merged_idx, False
        else:
            kept, kept_idx, hot_truncated = merged[-max_memories:], merged_idx[-max_memories:], True
        annotated = [_annotate_entry(e, display_ids[i]) for e, i in zip(kept, kept_idx)]
        hot_rendered = "\n\n".join(summaries + annotated)
        hot_entries_total = len(merged)
    else:
        hot_rendered, hot_entries_total, hot_truncated = "", 0, False

    total_all = hot_entries_total
    warm_blocks: List[str] = []
    for p in other_paths:
        parsed = _parse_memory_file(p)
        if parsed is None or not (parsed[1] or parsed[2]):
            continue
        total_all += len(parsed[2])
        block = _render_warm_author(p.stem, parsed[1], parsed[2], include_warm_entries)
        if block and block != f"### @{p.stem}":
            warm_blocks.append(block)

    sections = [s for s in (hot_rendered,) if s]
    if warm_blocks:
        sections.append(_WARM_SECTION_HEADING + "\n\n" + "\n\n".join(warm_blocks))
    rendered = "\n\n".join(sections)
    return rendered, total_all, hot_truncated, compaction_due, compaction_level


def _parse_max_memories(arguments: Dict[str, Any], default: int) -> Optional[int]:
    """Parse the optional max_memories argument; invalid values mean no limit."""
    raw = arguments.get("max_memories")
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def append_task_memories_direct(
    output_dir: Path,
    task_id: str,
    contents: List[str],
    at: Optional[datetime] = None,
) -> int:
    """Direct-write distilled task memories (no confirm gate).

    ADR-0002: task memories are task-scoped progress knowledge — noise cost is
    bounded by the task's lifetime and never enters the retrieval index — so
    distillation writes them directly (timestamp-headed entries, atomic
    append), unlike notes which keep the confirm_note quality gate. Ghost
    task_id (task deleted after capture) is tolerated: returns 0, no write.

    ``at`` (optional) stamps the entries with the distilled conversation's
    captured_at (dialogue time) instead of the distillation moment.

    Writes go to the CURRENT USER's ``memories/<user_id>.md`` only (per-user
    file ownership is the git-level conflict isolation invariant), under the
    store's cross-process sidecar lock.

    Returns the number of entries actually appended.
    """
    if not task_id or not contents:
        return 0
    return KnowledgeStore(output_dir).append_memories(
        task_id, contents, user=_current_user_id(), at=at
    )


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

    # Team-layout Phase 2 (§5.3): the read→duplicate-check→append→write
    # sequence must be atomic across processes — two servers creating
    # different tasks concurrently would otherwise lose one index entry
    # (and two same-title tasks would both pass the check).
    from codewiki.src.store import KnowledgeStore, locked

    ks = KnowledgeStore(output_dir)
    with locked(ks.tasks_dir / ".index.json"):
        tasks = ks.read_task_index()
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
        ks.write_task_index(tasks)
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

    # Team-layout Phase 2 (#12): piggy-back the stale-binding sweep on this
    # low-frequency read — abandoned session vouchers (never captured) would
    # otherwise accumulate forever. Best-effort, never blocks listing.
    try:
        KnowledgeStore(output_dir).gc_bindings(max_age_days=30)
    except Exception as e:
        logger.debug("gc_bindings skipped: %s", e)

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

    memories, mem_total, mem_truncated, _due, _level = _load_memories_layered(
        output_dir,
        task_id,
        _parse_max_memories(arguments, default=5),
        include_warm_entries=False,  # summary view: others' summaries only (Q9)
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

    # Phase 2 §5.3: complete is an index RMW — same locked sequence as
    # create_task so a concurrent create/complete cannot lose an entry.
    from codewiki.src.store import KnowledgeStore, locked

    ks = KnowledgeStore(output_dir)
    with locked(ks.tasks_dir / ".index.json"):
        tasks = ks.read_task_index()
        task = _find_by_id(tasks, task_id)
        if task is None:
            return json.dumps({"error": f"Task '{task_id}' does not exist."})
        if task.get("status") == "completed":
            return json.dumps({"ok": True, "task": task, "note": "Task was already completed."})

        task["status"] = "completed"
        task["completed_at"] = _now_iso()
        ks.write_task_index(tasks)

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

    # Full cascade (directory + index entry + bindings) lives in the store.
    cleared_bindings = KnowledgeStore(output_dir).delete_task(task_id)

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

    KnowledgeStore(output_dir).write_binding(source_session_id, task_id)

    return json.dumps(
        {
            "ok": True,
            "source_session_id": source_session_id,
            "task_id": task_id,
        },
        ensure_ascii=False,
    )


# ADR-0009 write check constants (design doc D3/D4/D5):
_WRITE_CHECK_SIMILARITY = 0.85  # difflib ratio above which a write is rejected
_WRITE_CHECK_TAIL = 10  # compare against the most recent N live entries
_WRITE_WINDOW_SOFT_LIMIT = 5  # per compaction window: warn (never block) past this


def _read_text_or_empty(path: Path) -> str:
    """Best-effort read; empty string when missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _entry_body(entry: str) -> str:
    """Entry text without its heading line (and any superseded marker)."""
    lines = entry.splitlines()
    if lines and lines[0].startswith("### "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _write_check(
    output_dir: Path, task_id: str, content: str
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """ADR-0009 write check: deterministic dedup + window soft limit.

    Returns (allow, rejection_payload, hint). ``rejection_payload`` is set
    when a near-duplicate (difflib ratio > 0.85) exists in the comparison
    scope (tail of live entries + compaction summary); ``hint`` is set when
    the write is allowed but the compaction window is over the soft limit
    (fail-open: warn, never block).
    """
    import difflib

    ks = KnowledgeStore(output_dir)
    own_path, legacy_path, _ = ks.collect_memory_files(task_id, _current_user_id())
    own = _parse_memory_file(own_path)
    leg = _parse_memory_file(legacy_path)
    hot_entries = (own[2] if own else []) + (leg[2] if leg else [])
    live = [e for e in hot_entries if not entry_is_superseded(e)]

    # Comparison scope: tail of live entries + compaction summary (D5).
    # Entry bodies only — the timestamp/id heading differs by construction and
    # would dilute the ratio of an otherwise-identical duplicate.
    # Short texts (< 20 chars) skip the dedup: a one-char difference in a
    # tiny string yields a high ratio with no meaningful signal (fail-open).
    scope_texts = [_entry_body(e) for e in live[-_WRITE_CHECK_TAIL:] if len(_entry_body(e)) >= 20]
    # Summaries are compared individually (D5): concatenating them into one
    # long text dilutes the ratio and lets "repeats a conclusion the summary
    # already covers" slip through. The canonical summary heading is stripped
    # first — same rationale as entry headings (it differs by construction).
    summaries = [
        s[len(_SUMMARY_HEADING) :].strip() if s.startswith(_SUMMARY_HEADING) else s
        for p in (own, leg)
        if p and p[1]
        for s in [p[1]]
    ]
    scope_texts.extend(s for s in summaries if s)

    best_ratio, best_entry = 0.0, None
    for e in scope_texts:
        ratio = difflib.SequenceMatcher(None, content, e).ratio()
        if ratio > best_ratio:
            best_ratio, best_entry = ratio, e
    if best_ratio > _WRITE_CHECK_SIMILARITY and best_entry is not None:
        return (
            False,
            {
                "error": (
                    f"Rejected: {best_ratio:.2f} similar to an existing entry "
                    f"(threshold {_WRITE_CHECK_SIMILARITY}). Supersede it or merge "
                    "and rewrite, then retry."
                ),
                "similar_to": best_entry,
                "similarity": round(best_ratio, 2),
            },
            None,
        )

    # Window soft limit: live entries of the caller's own file (the summary
    # section is the compaction boundary — a file WITH a summary has already
    # been compacted, so its live entries are the post-compaction window; a
    # file WITHOUT one has never been compacted, so all its live entries are
    # the window). The count INCLUDES the entry being appended (验收链 5:
    # the 6th write in a fresh window carries the hint). Fail-open: warn only.
    hint = None
    window_entries = [e for e in (own[2] if own else []) if not entry_is_superseded(e)]
    if len(window_entries) + 1 > _WRITE_WINDOW_SOFT_LIMIT:
        hint = (
            f"{len(window_entries) + 1} entries in the current compaction window "
            f"(soft limit {_WRITE_WINDOW_SOFT_LIMIT}) — consider compacting via "
            "compact_task_memories(mode='prepare')."
        )
    return True, None, hint


def handle_add_task_memory(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Append a memory entry to the current user's per-user memory file.

    ADR-0009: optional ``supersedes`` marks the referenced entry as retired
    (single-line marker under its heading; original text preserved). The
    write check rejects near-duplicates deterministically and warns (never
    blocks) past the per-window soft limit.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    task_id = str(arguments.get("task_id") or "").strip()
    content = str(arguments.get("content") or "").strip()
    supersedes = str(arguments.get("supersedes") or "").strip() or None
    if not task_id:
        return json.dumps({"error": "task_id is required."})
    if not content:
        return json.dumps({"error": "content is required."})

    tasks = _read_index(output_dir)
    if _find_by_id(tasks, task_id) is None:
        return json.dumps({"error": f"Task '{task_id}' does not exist."})

    ks = KnowledgeStore(output_dir)
    uid = _current_user_id()

    # ADR-0009 write check (skip when superseding — the new entry is by
    # definition a revision of the old one, similarity is expected).
    hint = None
    if not supersedes:
        allow, rejection, hint = _write_check(output_dir, task_id, content)
        if not allow:
            return json.dumps(rejection, ensure_ascii=False)

    # ADR-0009 验收链 2: validate the ref BEFORE appending — a bad ref must
    # return an error and leave no orphan new entry on disk. The real marker
    # write happens after the append (same locked_rmw ordering as before).
    if supersedes:
        err = ks.supersede_memory(task_id, user=uid, ref=supersedes, new_id="", dry_run=True)
        if err:
            return json.dumps({"error": err, "supersedes": supersedes}, ensure_ascii=False)

    # Generate the new entry's persistent id first (it is referenced by the
    # supersede marker), then append, then mark the old entry.
    own_path = ks.memory_path_for(task_id, uid)
    new_id = new_entry_id(
        entry_id(e) for e in split_entries(_read_text_or_empty(own_path)) if entry_id(e)
    )
    ks.append_memories(task_id, [content], user=uid, entry_id_override=new_id)

    superseded_ref = None
    if supersedes:
        err = ks.supersede_memory(task_id, user=uid, ref=supersedes, new_id=new_id)
        if err:
            # The append already happened; report the supersede failure
            # explicitly (never silent) but keep the write.
            return json.dumps(
                {
                    "ok": True,
                    "task_id": task_id,
                    "entry_id": new_id,
                    "appended_chars": len(content),
                    "supersede_error": err,
                },
                ensure_ascii=False,
            )
        superseded_ref = supersedes

    # Hot-layer count for the write-side signal (D4/Q10): computed over the
    # post-write hot layer.
    own = _parse_memory_file(own_path)
    leg = _parse_memory_file(ks.legacy_memory_path(task_id))
    hot_total = len(own[2] if own else []) + len(leg[2] if leg else [])
    hot_bytes = (own[3] if own else 0) + (leg[3] if leg else 0)

    resp: Dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "entry_id": new_id,
        "appended_chars": len(content),
        "hot_entries": f"{hot_total}/{_COMPACTION_THRESHOLD_COUNT}",
    }
    if superseded_ref:
        resp["superseded"] = superseded_ref
    if hint:
        resp["hint"] = hint
    if _compaction_needed(hot_total, hot_bytes):
        resp["hint"] = (
            (resp.get("hint") + " ") if resp.get("hint") else ""
        ) + f"Hot layer at {hot_total} entries — compaction due, see get_task_context."
    return json.dumps(resp, ensure_ascii=False)


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

    # Bounded LAYERED memories read (multi-user split design §4.3): hot layer
    # = current user's file (+ legacy) keeps the most recent max_memories
    # entries; warm layer = other users' summaries + a couple of recent entries
    # (budget-degraded to one-line hints). memories_total counts all files;
    # memories_truncated refers to the hot layer. compaction_due is the
    # pull-style signal over the HOT layer — the only files the current user
    # may compact (file-domain, author-exclusive) — meaning it exceeded the
    # compaction thresholds AND has entries beyond the keep window.
    memories, mem_total, mem_truncated, compaction_due, compaction_level = _load_memories_layered(
        output_dir,
        task_id,
        _parse_max_memories(arguments, default=20),
        include_warm_entries=True,
    )

    # Auto-compaction driver (docs/任务记忆检索与自动压缩设计.md D6): when
    # compaction is due, carry the PREPARED work inline so the calling agent
    # cannot miss it — it writes the summary and submits without a user gate
    # (ADR-0002 extension: compaction is reversible via the archives). The
    # payload comes from the SAME helper compact_task_memories(mode="prepare")
    # serves (single source of truth — the two must never drift apart).
    compaction_work: Optional[Dict[str, Any]] = None
    if compaction_due:
        payload = _prepare_compaction_payload(output_dir, task_id)
        if payload is not None:
            payload["submit"] = (
                "compact_task_memories(mode='submit', task_id=..., summary=<按 "
                "instruction 写的摘要>) — 压缩直写落盘，无需用户确认（原文进 "
                "memories-archive，可回溯）。"
            )
            compaction_work = payload

    # Discover related notes by frontmatter task_id. The ``status`` field lets
    # the host agent tell drafts apart from confirmed knowledge when injecting
    # this context (draft → must be labelled "待确认", never cited as settled).
    # Phase5 T3: shadow-confidence notes (rejected / misrecalled / unverified)
    # are excluded from task context — context assembly must not feed
    # reference-only knowledge into a fresh session unawares.
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
            if _extract_fm(text, "confidence_level") == "shadow":
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
            # ADR-0009 D9: graded signal; compaction_due stays as the red alias.
            "compaction_level": compaction_level,
            **({"compaction_work": compaction_work} if compaction_work else {}),
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


def _compact_instruction(max_chars: int) -> str:
    """Localized compaction instruction.

    Resolved per call (not at import) so the instruction follows the language
    chosen when the server process started.
    """
    from codewiki.mcp import i18n

    return i18n.t("tools.task_manager.compact_instruction", max_chars=max_chars)


def _compact_threshold_state(
    output_dir: Path, task_id: str
) -> Tuple[Path, Path, List[str], List[Tuple[str, str]], int, bool]:
    """Load the HOT layer (own + legacy files) as one compaction unit.

    Returns (own_path, legacy_path, summaries, entries_with_origin, hot_bytes,
    compaction_needed). ``entries_with_origin`` is [(owner, entry)] merged
    chronologically; owner is the current user id for own-file entries and
    ``_LEGACY_OWNER`` for legacy-file entries. Other users' files are NEVER
    part of the compaction unit (file-domain, author-exclusive invariant).
    """
    uid = _current_user_id()
    own_path, legacy_path, _others = _collect_memory_files(output_dir, task_id, uid)
    own = _parse_memory_file(own_path)
    leg = _parse_memory_file(legacy_path)
    own_has = own is not None and (own[1] or own[2])
    leg_has = leg is not None and (leg[1] or leg[2])

    summaries: List[str] = []
    entries: List[Tuple[str, str]] = []
    hot_bytes = 0
    if own_has:
        summaries.append(own[1])
        entries.extend((uid, e) for e in own[2])
        hot_bytes += own[3]
    if leg_has:
        # Annotate the legacy summary only when it sits next to the user's own.
        s = leg[1]
        if s and own_has:
            s = s.replace(_SUMMARY_HEADING, _SUMMARY_HEADING + "（legacy）", 1)
        summaries.append(s)
        entries.extend((_LEGACY_OWNER, e) for e in leg[2])
        hot_bytes += leg[3]
    # Chronological merge (stable): file order preserved for equal keys.
    entries.sort(key=lambda oe: _entry_sort_key(oe[1]))
    needed = _compaction_needed(len(entries), hot_bytes)
    return own_path, legacy_path, summaries, entries, hot_bytes, needed


def _prepare_compaction_payload(output_dir: Path, task_id: str) -> Optional[Dict[str, Any]]:
    """Shared prepare payload for compaction work (single source of truth).

    Used by both ``compact_task_memories(mode="prepare")`` and the
    get_task_context auto-compaction driver (``compaction_work``) — the
    two must never drift apart. Returns None when compaction is not due.
    """
    _own, _leg, summaries, entries, _bytes, needed = _compact_threshold_state(output_dir, task_id)
    if not needed:
        return None
    # ADR-0009 D8: superseded entries are the lowest-value content — they go
    # to the compress set FIRST (oldest superseded first), then live entries
    # oldest-first, until the keep window boundary.
    compress, _keep = _split_compaction(entries)
    return {
        "entries_to_compress": [e for _, e in compress],
        "existing_summary": "\n\n".join(s for s in summaries if s),
        "keep_recent": _COMPACTION_KEEP,
        "summary_max_chars": _COMPACTION_SUMMARY_MAX_CHARS,
        "summary_heading": _SUMMARY_HEADING,
        "archive_owners": sorted({owner for owner, _ in compress}),
        "instruction": _compact_instruction(_COMPACTION_SUMMARY_MAX_CHARS),
    }


def _split_compaction(
    entries: List[Tuple[str, str]],
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """ADR-0009 D8: pick the compress set with superseded entries first.

    ``entries`` is the chronological hot layer [(owner, entry)]. The compress
    set is the oldest ``len - keep`` entries, but superseded entries are
    pulled to the front of the candidate queue (they are retired — keeping
    them live in the hot layer is dead weight). Keep-set membership is
    unchanged: exactly the most recent ``keep`` live entries stay.

    Returns (compress_set, keep_set) — membership by index, so duplicate
    texts never cause a keep entry to be dropped via equality comparison.
    """
    n_compress = len(entries) - _COMPACTION_KEEP
    if n_compress <= 0:
        return [], list(entries)
    superseded = [oe for oe in entries if entry_is_superseded(oe[1])]
    live = [oe for oe in entries if not entry_is_superseded(oe[1])]
    # Superseded first (chronological), then live oldest-first.
    picked = superseded[:n_compress]
    picked.extend(live[: n_compress - len(picked)])
    picked_ids = {id(oe) for oe in picked}
    keep = [oe for i, oe in enumerate(entries) if id(oe) not in picked_ids]
    return picked, keep


def handle_compact_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Compress the CALLER's old memories into a summary section (two-phase).

    Stateless Mode-C design (mirrors distill_conversation): this tool never
    calls an LLM. ``mode="prepare"`` (default) returns the entries to compress
    plus instructions — the CALLER (host agent / subagent) writes the summary.
    ``mode="submit"`` with that ``summary`` performs the deterministic rewrite.

    File-domain, author-exclusive (multi-user split design §4.4): the
    compaction unit is the current user's own file PLUS the ownerless legacy
    ``memories.md`` — compacted together as one, so the legacy file converges
    into the user's own file and is then removed. Other users' per-user files
    are never read for compaction and never rewritten.

      memories/<user_id>.md := "## 早期记忆（摘要）" + summary + archive pointer
                               + the most recent _COMPACTION_KEEP entries
      memories-archive/<owner>.md (append-only) := compressed entries'
                               originals, per origin owner (user id / legacy)
      memories.md (legacy)  := removed after convergence

    Failure ordering: per-owner archive writes happen FIRST (superset — no
    information loss), then the own-file rewrite, then the legacy removal. A
    crash mid-sequence leaves originals duplicated in archives (safe,
    retry-able) — never lost. Compaction output is written directly, without
    a confirm gate: the operation is reversible (originals live in the
    archives; re-running regenerates), which the confirm philosophy does not
    cover (ADR-0001 / design doc §3 Q8).

    Idempotent: when the hot layer is below the thresholds or has no entries
    beyond the keep window, both modes return ``compaction_needed: false``.
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

    own_path, legacy_path, summaries, entries, _bytes, needed = _compact_threshold_state(
        output_dir, task_id
    )
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

    compress, keep = _split_compaction(entries)
    archive_owners = sorted({owner for owner, _ in compress})

    if mode == "prepare":
        payload = _prepare_compaction_payload(output_dir, task_id)
        assert payload is not None  # needed=True was checked above
        return json.dumps(
            {
                "ok": True,
                "mode": "prepare",
                "task_id": task_id,
                "compaction_needed": True,
                **payload,
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
                    f"(got {len(new_summary)}, over by {len(new_summary) - _COMPACTION_SUMMARY_MAX_CHARS}); "
                    f"shorten it by at least {len(new_summary) - _COMPACTION_SUMMARY_MAX_CHARS} chars."
                )
            }
        )

    # NOTE: the split is recomputed at submit time. Entries appended between
    # prepare and submit land in the keep window; the compress set may gain the
    # entry that was previously the oldest kept one — the caller's summary may
    # not cover it. Tolerated: append-only writes are rare mid-compaction and
    # the entry is preserved verbatim in the archive either way.
    date = datetime.now().strftime("%Y-%m-%d")
    archive_relpaths = ", ".join(f"{_ARCHIVE_DIRNAME}/{owner}.md" for owner in archive_owners)
    pointer = f"> 原文归档于 {archive_relpaths}，截至 {date}，共 {len(compress)} 条。"
    new_text = (
        f"{_SUMMARY_HEADING}\n\n{new_summary}\n\n{pointer}\n\n"
        + "\n\n".join(e for _, e in keep)
        + "\n"
    )

    # Archive blocks per origin owner: verbatim entries; legacy heading-less
    # entries get a synthetic heading so the archive stays scannable.
    blocks_by_owner: Dict[str, List[str]] = {}
    for owner, e in compress:
        if not e.startswith("### "):
            e = "### 历史条目（存量格式，无时间戳）\n\n" + e
        blocks_by_owner.setdefault(owner, []).append(e)

    # Safe failure ordering, step 1: per-owner archive appends FIRST (superset
    # — no information loss). A failure later leaves originals in BOTH the
    # archives and the live files; a retry re-archives (duplicate) but never
    # loses.
    for owner, parts in blocks_by_owner.items():
        archive_path = _archive_path_for(output_dir, task_id, owner)

        def _append_archive(existing: str) -> str:
            base = existing.rstrip("\n")
            return (base + "\n\n" if base else "") + "\n\n".join(parts) + "\n"

        # locked_rmw: append-only archive write funnels through the store's
        # sidecar lock (same-user two-process compaction can no longer race).
        locked_rmw(archive_path, _append_archive)

    # Step 2: rewrite the caller's own file (create it when only legacy data
    # existed — legacy converges into the user's own file here).
    locked_write(own_path, new_text)

    # Step 3: remove the converged legacy file (originals already archived;
    # kept entries + summary live in the own file now).
    legacy_removed = False
    if legacy_path.exists():
        try:
            legacy_path.unlink()
            legacy_removed = True
            # keep the git index in step with the removal (auto-stage
            # companion; silent no-op outside a repo / config off)
            from codewiki.src.store import _stage_removal

            _stage_removal(legacy_path)
        except OSError:
            logger.warning("Failed to remove converged legacy memories.md at %s", legacy_path)

    return json.dumps(
        {
            "ok": True,
            "mode": "submit",
            "task_id": task_id,
            "compressed": len(compress),
            "kept": len(keep),
            "archives": [f"{_ARCHIVE_DIRNAME}/{o}.md" for o in archive_owners],
            "legacy_converged": legacy_removed,
            "memories_total": len(keep),
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# search_task_memories (memory recall — docs/任务记忆检索与自动压缩设计.md D2)
# --------------------------------------------------------------------------- #


def handle_search_task_memories(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Entry-level keyword recall over ONE task's memories.

    The complement of get_task_context's tail injection: answers "which OLD
    entry (truncated away by max_memories, or already compacted into the
    archive) said X". In-memory BM25 over the task's own corpus — always
    fresh, never persisted, never coupled to the wiki search index.

    Privacy mirrors the layered reader: defaults to the current user's own
    live file + legacy + their archives; ``include_others=true`` opts into
    other users' memories. Read-only: no usage-heat events, no git sync.
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
    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "query is required."})
    try:
        max_results = min(20, max(1, int(arguments.get("max_results", 10))))
    except (TypeError, ValueError):
        max_results = 10

    result = KnowledgeStore(output_dir).search_memories(
        task_id,
        query,
        uid=_current_user_id(),
        include_archive=bool(arguments.get("include_archive", True)),
        include_others=bool(arguments.get("include_others", False)),
        max_results=max_results,
    )
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)
    result["ok"] = True
    archived_hits = sum(1 for r in result["results"] if r.get("archived"))
    if archived_hits:
        result["hint"] = (
            f"{archived_hits} result(s) come from the compaction archive — "
            "the entry's full text lives in memories-archive/<owner>.md (append-only); "
            "read that file for the full context around the snippet."
        )
    return json.dumps(result, ensure_ascii=False)
