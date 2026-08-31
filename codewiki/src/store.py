"""Unified knowledge store for the repowiki/ tree (RFC docs/plans/knowledge-store-rfc.md).

Single persistence layer hiding every piece of plumbing that 15+ MCP tool
handlers used to re-implement locally: frontmatter read/write, path
resolution within the knowledge base, file naming (slugify + collision),
atomic writes with sidecar locking, index caches that self-heal from
directory scans, and session-binding consumption.

Pure filesystem module — no MCP/session imports. Handlers obtain a store via
``codewiki.mcp.tools.store_bridge.store_for`` (the only place that resolves
a SessionState into a root path).

Invariants:
  - The disk format (markdown + YAML frontmatter) is a contract managed by
    git, hand-edited by humans and read by external agents: never migrate it,
    never drop unknown keys on rewrite.
  - ``.index.json`` files are caches; directory scans are the truth. Every
    reader validates cheaply and rebuilds on mismatch.
  - Concurrent stdio MCP server processes serialize read-modify-write
    sequences through sidecar ``.lck`` files (a locked target cannot be
    ``os.replace``d on Windows — locking a sidecar keeps atomic replace
    working).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from codewiki.src import config as _cfg
from codewiki.src.frontmatter import (
    format_frontmatter_value,
    inject_okf_frontmatter,
    parse_frontmatter,
)
from codewiki.src.locks import file_lock

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_DASH = re.compile(r"-{2,}")
_MAX_SLUG_LEN = 60


def slugify(text: str) -> str:
    """Filesystem-safe human-readable slug; '' when nothing usable remains."""
    text = (text or "").strip()
    if not text:
        return ""
    slug = _UNSAFE_CHARS.sub("-", text)
    slug = re.sub(r"\s+", "-", slug)
    slug = _MULTI_DASH.sub("-", slug).strip("-")
    if not slug:
        return ""
    if len(slug) > _MAX_SLUG_LEN:
        slug = slug[:_MAX_SLUG_LEN].rstrip("-")
    return slug


# --------------------------------------------------------------------------- #
# Atomic write + sidecar locking
# --------------------------------------------------------------------------- #


def _atomic_replace_with_retry(src: Path, dst: Path, attempts: int = 5) -> None:
    """os.replace with short backoff retries for Windows transient sharing
    violations (AV scanners / search indexers briefly holding the destination)."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


def atomic_write(path: Path, content: str) -> None:
    """Write *content* via temp file + atomic replace (crash-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # pid + thread id: unique across processes AND across threads of this
    # process writing the same path concurrently.
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        tmp.write_text(content, encoding="utf-8")
        _atomic_replace_with_retry(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Serialize a read-modify-write sequence on *path* across threads AND
    processes via a sidecar ``<name>.lck`` file.

    Locking the sidecar (not the target) keeps ``os.replace`` on the target
    legal on Windows, where a locked/open file cannot be renamed over.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / (path.name + ".lck")
    with file_lock(lock_path):
        yield


# --------------------------------------------------------------------------- #
# Light read object
# --------------------------------------------------------------------------- #


class Page:
    """A parsed repowiki document: frontmatter dict + body, parsed once."""

    __slots__ = ("relpath", "path", "fm", "body")

    def __init__(self, relpath: str, path: Path, fm: Dict[str, Any], body: str):
        self.relpath = relpath
        self.path = path
        self.fm = fm
        self.body = body

    def get(self, key: str, default: Any = None) -> Any:
        """Top-level key first, then one level under ``metadata`` —
        the unified semantics every former hand-rolled parser approximated."""
        if key in self.fm:
            return self.fm[key]
        meta = self.fm.get("metadata")
        if isinstance(meta, dict) and key in meta:
            return meta[key]
        return default

    def text(self, key: str, default: str = "") -> str:
        """String form of :meth:`get` (booleans/numbers stringified)."""
        v = self.get(key)
        if v is None:
            return default
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)


# Memory entry structure (ADR-0001: markdown stays; the heading is the parse
# boundary for truncation/compaction).
_ENTRY_TS_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
SUMMARY_HEADING = "## 早期记忆（摘要）"
MEMORIES_DIRNAME = "memories"
ARCHIVE_DIRNAME = "memories-archive"
LEGACY_MEMORIES_FILENAME = "memories.md"
RAW_INDEX_NAME = ".index.json"


def split_entries(text: str) -> List[str]:
    """Split a memory file into entries: ``### `` headings first, blank-line
    paragraphs as the legacy fallback (see task_manager design docs)."""
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


def split_summary_and_entries(text: str) -> Tuple[str, List[str]]:
    """(summary_section, entries) — the compaction summary runs from its
    heading to the first ``### `` entry heading."""
    if not text or not text.strip():
        return "", []
    idx = text.find(SUMMARY_HEADING)
    if idx < 0:
        return "", split_entries(text)
    prefix = text[:idx].strip()
    rest = text[idx:]
    m = re.search(r"(?m)^### ", rest)
    if m:
        summary = rest[: m.start()].rstrip()
        entries_text = rest[m.start() :]
    else:
        summary = rest.rstrip()
        entries_text = ""
    entries = split_entries(prefix) if prefix else []
    entries.extend(split_entries(entries_text))
    return summary, entries


def entry_sort_key(entry: str) -> Tuple[int, str]:
    """Chronological key: dated entries first (by timestamp), undated last."""
    m = _ENTRY_TS_RE.match(entry)
    if m:
        return (0, m.group(1))
    return (1, "")


def format_memory_entry(content: str) -> str:
    """One timestamp-headed memory entry."""
    return f"### {datetime.now():%Y-%m-%d %H:%M}\n\n{(content or '').strip()}\n"


# --------------------------------------------------------------------------- #
# The store
# --------------------------------------------------------------------------- #


class KnowledgeStore:
    """Persistence facade over one repowiki/ root.

    The root must already be resolved (layout routing happens in the bridge);
    the store only knows paths under it.
    """

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root)

    # ── paths ──────────────────────────────────────────────────────────────

    @property
    def notes_dir(self) -> Path:
        return self.root / _cfg.NOTES_DIR

    @property
    def raw_dir(self) -> Path:
        return self.root / _cfg.RAW_DIR

    @property
    def tasks_dir(self) -> Path:
        return self.root / _cfg.TASKS_DIR

    @property
    def meta_dir(self) -> Path:
        return self.root / _cfg.META_DIR

    @property
    def bindings_dir(self) -> Path:
        return self.meta_dir / _cfg.TASK_BINDINGS_DIR

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def relpath(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def _read_text(self, p: Path) -> Optional[str]:
        try:
            return p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None

    # ── generic read ───────────────────────────────────────────────────────

    def page(self, relpath: str) -> Optional[Page]:
        """Parse one document; None when missing/unreadable."""
        p = self.root / relpath
        if not p.is_file():
            return None
        text = self._read_text(p)
        if text is None:
            return None
        fm, body = parse_frontmatter(text)
        return Page(relpath, p, fm, body)

    def iter_pages(self, scope: str = "", pattern: str = "*.md") -> Iterator[Page]:
        """Lazily parse every document under *scope* (e.g. ``notes``,
        ``wiki/modules``); unreadable files are skipped, never raised."""
        base = self.root / scope if scope else self.root
        if not base.is_dir():
            return
        for f in sorted(base.rglob(pattern)):
            if not f.is_file():
                continue
            text = self._read_text(f)
            if text is None:
                continue
            fm, body = parse_frontmatter(text)
            yield Page(f.relative_to(self.root).as_posix(), f, fm, body)

    # ── generic write (escape hatches) ────────────────────────────────────

    def write(self, relpath: str, content: str) -> Path:
        """Atomic write of arbitrary content; returns the absolute path."""
        p = self.root / relpath
        atomic_write(p, content)
        return p

    def update_frontmatter(self, relpath: str, **fields: Any) -> bool:
        """Rewrite ONLY the given frontmatter keys, preserving every other
        line verbatim (body untouched, unknown keys kept, no reordering).
        Returns False when the file is missing."""
        p = self.root / relpath
        text = self._read_text(p)
        if text is None:
            return False
        m = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.DOTALL)
        if m:
            lines = m.group(1).splitlines()
            remaining = dict(fields)
            out: List[str] = []
            in_meta = False
            meta_end: Optional[int] = None  # insert point = end of metadata block
            for line in lines:
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                if indent == 0:
                    in_meta = stripped.lower() == "metadata:"
                    key = stripped.partition(":")[0].strip()
                    if key in remaining:
                        out.append(f"{key}: {format_frontmatter_value(remaining.pop(key))}")
                        continue
                elif in_meta and indent >= 2 and ":" in stripped:
                    key = stripped.partition(":")[0].strip()
                    meta_key = f"metadata.{key}"
                    if meta_key in remaining:
                        out.append(
                            " " * indent
                            + f"{key}: {format_frontmatter_value(remaining.pop(meta_key))}"
                        )
                    else:
                        out.append(line)
                    meta_end = len(out)
                    continue
                out.append(line)
                if in_meta:
                    meta_end = len(out)
            # Fields the file did not carry yet: top-level keys are appended;
            # "metadata.x" keys go INTO the metadata block (creating it when
            # absent) — never as literal top-level "metadata.x:" lines.
            meta_extra: Dict[str, Any] = {}
            for key in list(remaining):
                if key.startswith("metadata."):
                    meta_extra[key[len("metadata.") :]] = remaining.pop(key)
            for key, value in remaining.items():
                out.append(f"{key}: {format_frontmatter_value(value)}")
            if meta_extra:
                block = [f"  {k}: {format_frontmatter_value(v)}" for k, v in meta_extra.items()]
                if meta_end is not None:
                    out[meta_end:meta_end] = block
                else:
                    out.append("metadata:")
                    out.extend(block)
            new_text = "---\n" + "\n".join(out) + "\n---\n" + text[m.end() :]
        else:
            fm_lines: List[str] = []
            meta_extra = {}
            for key, value in fields.items():
                if key.startswith("metadata."):
                    meta_extra[key[len("metadata.") :]] = value
                else:
                    fm_lines.append(f"{key}: {format_frontmatter_value(value)}")
            if meta_extra:
                fm_lines.append("metadata:")
                fm_lines.extend(
                    f"  {k}: {format_frontmatter_value(v)}" for k, v in meta_extra.items()
                )
            new_text = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + text
        with locked(p):
            atomic_write(p, new_text)
        return True

    # ── session bindings (.meta/task_bindings) ─────────────────────────────

    def read_binding(self, source_session_id: str) -> str:
        """task_id bound to *source_session_id*; '' when absent/corrupt."""
        if not source_session_id:
            return ""
        p = self.bindings_dir / f"{source_session_id}.json"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return ""
        return str(data.get("task_id") or "").strip() if isinstance(data, dict) else ""

    def write_binding(self, source_session_id: str, task_id: str) -> Path:
        self.bindings_dir.mkdir(parents=True, exist_ok=True)
        p = self.bindings_dir / f"{source_session_id}.json"
        binding = {"task_id": task_id, "bound_at": datetime.now(timezone.utc).isoformat()}
        atomic_write(p, json.dumps(binding, ensure_ascii=False, indent=2))
        return p

    def remove_binding(self, source_session_id: str) -> bool:
        try:
            (self.bindings_dir / f"{source_session_id}.json").unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def clear_bindings_for_task(self, task_id: str) -> int:
        """Delete every binding pointing at *task_id* (delete_task cascade)."""
        cleared = 0
        if not self.bindings_dir.exists():
            return 0
        for bf in self.bindings_dir.glob("*.json"):
            try:
                data = json.loads(bf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("task_id") == task_id:
                try:
                    bf.unlink()
                    cleared += 1
                except OSError:
                    logger.warning("Failed to remove binding %s", bf)
        return cleared

    # ── raw/ staging area ──────────────────────────────────────────────────

    @staticmethod
    def content_hash(turns: List[Dict[str, str]], link_to: str, task_id: str = "") -> str:
        """task_id participates: the same conversation under two tasks is NOT
        deduplicated away."""
        payload = json.dumps(
            {"turns": turns, "link_to": link_to, "task_id": task_id},
            ensure_ascii=False,
            sort_keys=True,
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _raw_index_path(self) -> Path:
        return self.raw_dir / RAW_INDEX_NAME

    @staticmethod
    def _raw_rel(relpath: str) -> str:
        """Normalise a raw-file relpath to the bare filename.

        Callers hold either convention: capture results are root-relative
        (``raw/<name>``) while pending_raws/distill lists carry the bare
        filename. Accepting both keeps the verbs footgun-free.
        """
        relpath = str(relpath).replace("\\", "/").strip()
        prefix = f"{_cfg.RAW_DIR}/"
        if relpath.startswith(prefix):
            relpath = relpath[len(prefix) :]
        return relpath.lstrip("/")

    def _rebuild_raw_index(self) -> Dict[str, Any]:
        """Scan conv-*.md frontmatter (the truth) and rebuild the index."""
        files: List[Dict[str, str]] = []
        for existing in sorted(self.raw_dir.glob("conv-*.md")):
            text = self._read_text(existing)
            if text is None:
                continue
            fm, _ = parse_frontmatter(text)
            ch = str(fm.get("content_hash") or "")
            if not ch:
                continue
            files.append(
                {
                    "relpath": existing.name,
                    "content_hash": ch,
                    "source_session": str(fm.get("source_session") or ""),
                    "status": str(fm.get("status") or "pending"),
                    "task_id": str(fm.get("task_id") or ""),
                    "captured_at": str(fm.get("captured_at") or ""),
                }
            )
        return {"files": files}

    def _raw_index(self, rebuild_on_missing: bool = True) -> Dict[str, Any]:
        idx_path = self._raw_index_path()
        index: Optional[Dict[str, Any]] = None
        if idx_path.is_file():
            try:
                data = json.loads(idx_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("files"), list):
                    index = data
            except (OSError, ValueError):
                index = None
        if index is None and rebuild_on_missing:
            index = self._rebuild_raw_index()
        return index or {"files": []}

    def _write_raw_index(self, index: Dict[str, Any]) -> None:
        """Best-effort: a failed index update must never break the capture."""
        try:
            atomic_write(self._raw_index_path(), json.dumps(index, ensure_ascii=False))
        except OSError:
            logger.debug("raw index write failed (non-fatal)", exc_info=True)

    def capture_raw(
        self,
        turns: List[Dict[str, str]],
        *,
        source_session_id: str = "",
        task_id: str = "",
        link_to: str = "",
        keep_raw: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        transcript_title: str = "",
    ) -> Dict[str, Any]:
        """Persist one transcript into raw/ with dedup + session-supersede.

        Returns a dict with ``kind`` ∈ captured | duplicate | superseded |
        error plus relpath/conversation_id/content_hash/task_id/task_source/
        captured_at/turn_count. A session binding that supplied the task_id
        is consumed (deleted) here once the write succeeds; the result's
        ``consumed_binding`` flag is informational.
        """
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        if not task_id and source_session_id:
            bound = self.read_binding(source_session_id)
            if bound:
                task_id, task_source = bound, "binding"
            else:
                task_source = ""
        else:
            task_source = "argument" if task_id else ""

        chash = self.content_hash(turns, link_to, task_id)
        index = self._raw_index()

        def _find(entries: List[Dict[str, Any]]):
            dup, sup = None, None
            for entry in entries:
                if entry.get("content_hash") == chash:
                    dup = entry.get("relpath")
                    break
                if (
                    source_session_id
                    and entry.get("source_session") == source_session_id
                    and entry.get("status") == "pending"
                ):
                    sup = entry.get("relpath")
            return dup, sup

        dup_rel, sup_rel = _find(index.get("files", []))
        if dup_rel is None and sup_rel is None:
            rebuilt = self._rebuild_raw_index()
            if len(rebuilt.get("files", [])) != len(index.get("files", [])):
                index = rebuilt
                dup_rel, sup_rel = _find(index.get("files", []))

        if dup_rel is not None:
            return {
                "kind": "duplicate",
                "relpath": f"{_cfg.RAW_DIR}/{dup_rel}",
                "conversation_id": Path(str(dup_rel)).stem,
                "content_hash": chash,
                "task_id": task_id,
                "task_source": task_source,
            }

        superseded = sup_rel is not None
        if superseded and not task_id:
            # Binding was consumed on the first capture; inherit task_id from
            # the superseded entry so attribution survives re-capture.
            for entry in index.get("files", []):
                if entry.get("relpath") == sup_rel:
                    inherited = str(entry.get("task_id") or "").strip()
                    if inherited:
                        task_id = inherited
                        task_source = "binding-inherited"
                        chash = self.content_hash(turns, link_to, task_id)
                    break

        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        if superseded:
            dest = self.raw_dir / str(sup_rel)
        else:
            slug = slugify(transcript_title)
            if slug:
                base = f"conv-{slug}"
                dest = self.raw_dir / f"{base}.md"
                n = 2
                while dest.exists():
                    dest = self.raw_dir / f"{base}-{n}.md"
                    n += 1
            else:
                safe_link = "".join(c if c.isalnum() else "-" for c in link_to)[:40]
                fname = f"conv-{stamp}{('-' + safe_link) if safe_link else ''}.md"
                dest = self.raw_dir / fname
                if dest.exists():
                    dest = self.raw_dir / f"conv-{stamp}-{int(now.timestamp() * 1000) % 100000}.md"

        body_lines = [f"{t['role']}: {t['content']}" for t in turns]
        meta: Dict[str, Any] = {
            "captured_at": now_iso,
            "content_hash": chash,
            "turn_count": len(turns),
            "link_to": link_to,
            "source_session": source_session_id,
            "keep_raw": keep_raw,
        }
        if metadata:
            meta.update(metadata)
        if task_id:
            meta["task_id"] = task_id

        try:
            actor = _cfg.actor_id()
        except Exception:
            actor = "codewiki"
        content = inject_okf_frontmatter(
            "# Conversation Transcript\n\n" + "\n".join(body_lines) + "\n",
            type_="Conversation",
            title="conversation " + stamp,
            output_dir=self.root,
            status="pending",
            stale_days=90,
            top_level_extra=meta,
            actor=actor,
            now_iso=now_iso,
        )
        try:
            with locked(dest):
                atomic_write(dest, content)
        except OSError as e:
            return {"kind": "error", "error": f"Failed to write conversation file: {e}"}

        # Index maintenance (single writer). Supersede updates in place.
        entries = [dict(e) for e in index.get("files", []) if isinstance(e, dict)]
        new_entry = {
            "relpath": dest.name,
            "content_hash": chash,
            "source_session": source_session_id,
            "status": "pending",
            "task_id": task_id,
            "captured_at": now_iso,
        }
        if superseded:
            for i, e in enumerate(entries):
                if e.get("relpath") == dest.name:
                    entries[i] = new_entry
                    break
        else:
            entries.append(new_entry)
        self._write_raw_index({"files": entries})

        # One-shot binding consumption: the binding exists only to route this
        # capture; once the file is safely on disk it has served its purpose.
        # Only consume when the task_id actually came from the binding —
        # explicit task_id arguments and inherited attribution leave it alone.
        if task_source == "binding" and source_session_id:
            self.remove_binding(source_session_id)

        return {
            "kind": "superseded" if superseded else "captured",
            "relpath": f"{_cfg.RAW_DIR}/{dest.name}",
            "conversation_id": dest.stem,
            "content_hash": chash,
            "task_id": task_id,
            "task_source": task_source,
            "captured_at": now_iso,
            "turn_count": len(turns),
            "consumed_binding": task_source == "binding",
        }

    def pending_raws_by_task(self) -> Dict[str, List[Dict[str, str]]]:
        """Pending (not-yet-distilled) raws grouped by task_id; '' key for
        unbound captures. Index-first with a frontmatter fallback for files
        missing from the index."""
        if not self.raw_dir.is_dir():
            return {}
        index = self._raw_index(rebuild_on_missing=False)
        indexed: Dict[str, Dict[str, Any]] = {}
        for e in index.get("files", []):
            if isinstance(e, dict) and e.get("relpath"):
                indexed[str(e["relpath"])] = e

        by_task: Dict[str, List[Dict[str, str]]] = {}
        try:
            candidates = sorted(self.raw_dir.glob("conv-*.md"))
        except OSError:
            return {}
        for p in candidates:
            if not p.is_file():
                continue
            entry = indexed.get(p.name)
            if entry is not None:
                if str(entry.get("status") or "pending") == "distilled":
                    continue
                task_id = str(entry.get("task_id") or "")
                captured_at = str(entry.get("captured_at") or "")
            else:
                text = self._read_text(p)
                if text is None:
                    continue
                fm, _ = parse_frontmatter(text)
                if str(fm.get("status") or "pending") == "distilled":
                    continue
                task_id = str(fm.get("task_id") or "")
                captured_at = str(fm.get("captured_at") or "")
            by_task.setdefault(task_id, []).append(
                {"relpath": p.name, "task_id": task_id, "captured_at": captured_at}
            )
        return by_task

    def mark_raw_distilled(self, relpath: str) -> bool:
        """Flip a raw file's status to distilled (index updated too).

        ``relpath`` may be the bare filename (as returned by
        :meth:`pending_raws_by_task`) or root-relative ``raw/<name>`` (as
        returned by :meth:`capture_raw`) — both are accepted. Deletion of the
        file itself is a separate decision (:meth:`delete_raw`).
        """
        relpath = self._raw_rel(relpath)
        p = self.raw_dir / relpath
        if not p.is_file():
            return False
        self.update_frontmatter(f"{_cfg.RAW_DIR}/{relpath}", status="distilled")
        index = self._raw_index(rebuild_on_missing=False)
        entries = [dict(e) for e in index.get("files", []) if isinstance(e, dict)]
        changed = False
        for e in entries:
            if e.get("relpath") == relpath:
                e["status"] = "distilled"
                changed = True
                break
        if changed:
            self._write_raw_index({"files": entries})
        return True

    def delete_raw(self, relpath: str) -> bool:
        """Remove a raw file and its index entry. Accepts both relpath
        conventions (see :meth:`mark_raw_distilled`)."""
        relpath = self._raw_rel(relpath)
        p = self.raw_dir / relpath
        try:
            p.unlink(missing_ok=True)
        except OSError:
            return False
        index = self._raw_index(rebuild_on_missing=False)
        entries = [
            dict(e)
            for e in index.get("files", [])
            if isinstance(e, dict) and e.get("relpath") != relpath
        ]
        self._write_raw_index({"files": entries})
        return True

    def sync_raw_index(self, relpath: str, *, removed: bool) -> None:
        """Keep ``raw/.index.json`` consistent after distillation (best-effort).

        ``removed=True`` drops the entry (the file left raw/ — deleted or
        archived into conversations/); ``removed=False`` flips it to
        status=distilled (kept via keep_raw). The file itself is NOT touched:
        the distill flow owns deletion/archival. A failed index write is
        logged and swallowed — this must never block distillation.
        """
        relpath = self._raw_rel(relpath)
        index = self._raw_index(rebuild_on_missing=False)
        files = [dict(e) for e in index.get("files", []) if isinstance(e, dict)]
        if removed:
            files = [e for e in files if e.get("relpath") != relpath]
        else:
            for e in files:
                if e.get("relpath") == relpath:
                    e["status"] = "distilled"
                    break
        self._write_raw_index({"files": files})

    # ── tasks/ ─────────────────────────────────────────────────────────────

    def _task_index_path(self) -> Path:
        return self.tasks_dir / RAW_INDEX_NAME

    def read_task_index(self) -> List[Dict[str, Any]]:
        """Task entries; the tasks/ DIRECTORY is truth, .index.json a cache.

        Cheap id-set validation (directory names are task ids); rebuild by
        scanning task.md frontmatter only on mismatch/corruption.
        """
        p = self._task_index_path()
        tasks: List[Dict[str, Any]] = []
        corrupt = False
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                raw = data.get("tasks", []) if isinstance(data, dict) else []
                tasks = [t for t in raw if isinstance(t, dict)]
            except (ValueError, OSError):
                logger.warning("Task index unreadable at %s; rebuilding from disk.", p)
                corrupt = True

        tdir = self.tasks_dir
        if not tdir.is_dir():
            return tasks

        disk_ids = {d.name for d in tdir.iterdir() if d.is_dir()}
        index_ids = {str(t.get("id") or "") for t in tasks}
        if not corrupt and disk_ids == index_ids:
            return tasks

        rebuilt: List[Dict[str, Any]] = []
        for tf in sorted(tdir.glob("*/task.md")):
            text = self._read_text(tf)
            if text is None:
                logger.warning("Unreadable task file %s during index rebuild.", tf)
                continue
            fm, _ = parse_frontmatter(text)
            entry: Dict[str, Any] = {
                "id": str(fm.get("task_id") or tf.parent.name),
                "title": str(fm.get("title") or tf.parent.name),
                "status": str(fm.get("status") or "active"),
                "created_at": str(fm.get("created_at") or ""),
            }
            completed = fm.get("completed_at")
            if completed:
                entry["completed_at"] = str(completed)
            rebuilt.append(entry)
        # Mid-create race: directory exists but task.md unreadable → keep entry.
        rebuilt_ids = {t["id"] for t in rebuilt}
        for t in tasks:
            if t.get("id") not in rebuilt_ids and t.get("id") in disk_ids:
                rebuilt.append(t)
        try:
            self.write_task_index(rebuilt)
        except OSError:
            logger.warning("Failed to rewrite task index at %s after rebuild.", p)
        return rebuilt

    def write_task_index(self, tasks: List[Dict[str, Any]]) -> None:
        atomic_write(
            self._task_index_path(),
            json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2),
        )

    def find_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        for t in self.read_task_index():
            if t.get("id") == task_id:
                return t
        return None

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / task_id / "task.md"

    def task_description(self, task_id: str) -> str:
        p = self.task_path(task_id)
        if not p.exists():
            return ""
        text = self._read_text(p)
        if text is None:
            return ""
        _, body = parse_frontmatter(text)
        return body.strip()

    def write_task_file(self, task: Dict[str, Any], description: str) -> None:
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
        body = (description or "").strip()
        content = "\n".join(lines) + "\n\n" + body + "\n"
        atomic_write(self.task_path(task["id"]), content)

    def delete_task_tree(self, task_id: str) -> None:
        task_dir = self.tasks_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)

    def delete_task(self, task_id: str) -> int:
        """Full delete cascade: task directory, index entry, and every
        session binding pointing at the task. Returns the number of bindings
        cleared (0 when the task did not exist or had none)."""
        self.delete_task_tree(task_id)
        remaining = [t for t in self.read_task_index() if t.get("id") != task_id]
        try:
            self.write_task_index(remaining)
        except OSError:
            logger.warning("Failed to rewrite task index after deleting %s.", task_id)
        return self.clear_bindings_for_task(task_id)

    # ── task memories ──────────────────────────────────────────────────────

    def memory_path_for(self, task_id: str, owner: str) -> Path:
        """Per-user memory file — the ONLY write target for that owner."""
        return self.tasks_dir / task_id / MEMORIES_DIRNAME / f"{owner}.md"

    def legacy_memory_path(self, task_id: str) -> Path:
        return self.tasks_dir / task_id / LEGACY_MEMORIES_FILENAME

    def archive_path_for(self, task_id: str, owner: str) -> Path:
        return self.tasks_dir / task_id / ARCHIVE_DIRNAME / f"{owner}.md"

    def collect_memory_files(self, task_id: str, uid: str) -> Tuple[Path, Path, List[Path]]:
        """(own_path, legacy_path, other_paths) — paths, existing or not."""
        own = self.memory_path_for(task_id, uid)
        mdir = self.tasks_dir / task_id / MEMORIES_DIRNAME
        others: List[Path] = []
        if mdir.is_dir():
            others = [p for p in sorted(mdir.glob("*.md")) if p.name != own.name]
        return own, self.legacy_memory_path(task_id), others

    @staticmethod
    def parse_memory_file(path: Path) -> Optional[Tuple[str, str, List[str], int]]:
        """(raw_text, summary_section, entries, file_bytes); None when missing.

        Static — does not need a store root (reads a single file), so module
        helpers that hold only a path can delegate to it directly.
        """
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None
        text = text.strip()
        summary, entries = split_summary_and_entries(text)
        return (text, summary, entries, path.stat().st_size)

    def append_memories(self, task_id: str, contents: List[str], *, user: str) -> int:
        """Append timestamp-headed entries to the user's memory file under a
        cross-process lock (the old path admitted it had none). Ghost tasks
        (deleted after capture) return 0 without writing."""
        if not task_id or not contents:
            return 0
        if self.find_task(task_id) is None:
            return 0
        path = self.memory_path_for(task_id, user)
        written = 0
        for c in contents:
            c = str(c or "").strip()
            if not c:
                continue
            with locked(path):
                existing = ""
                if path.exists():
                    existing = self._read_text(path) or ""
                    existing = existing.rstrip("\n")
                    if existing:
                        existing += "\n\n"
                atomic_write(path, existing + format_memory_entry(c))
            written += 1
        return written

    # ── notes/ ─────────────────────────────────────────────────────────────

    def find_note_by_title(self, title: str) -> Optional[Page]:
        needle = (title or "").strip()
        if not needle:
            return None
        for page in self.iter_pages(_cfg.NOTES_DIR):
            if str(page.get("title") or "").strip() == needle:
                return page
        return None
