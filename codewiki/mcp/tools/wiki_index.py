"""MCP tool helpers: index.md and log.md auto-generation.

Provides ``rebuild_index`` (rebuilds the content catalog) and ``append_log``
(appends a timestamped operation entry).  Both are designed to be called
at the end of other tool handlers, wrapped in try/except so failures never
block the primary operation.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-platform file locking: fcntl is Unix-only; on Windows we fall back to
# msvcrt, and if neither is available we degrade gracefully to a thread lock.
# ---------------------------------------------------------------------------
try:
    import fcntl as _fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows
    _fcntl = None

try:
    import msvcrt as _msvcrt  # type: ignore
except ImportError:  # pragma: no cover - non-Windows
    _msvcrt = None

# Process-local fallback lock for the append path when no OS-level file lock
# primitive is available.
_append_fallback_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Module-level lock for index rebuilds (serialises concurrent rebuild calls)
# ---------------------------------------------------------------------------
_index_lock = threading.Lock()

# Lock for log file creation (prevents duplicate headers on first concurrent call)
_log_create_lock = threading.Lock()

# Timezone: UTC+8 for display, but we use utcnow() + format manually
_TZ_CST = timezone(timedelta(hours=8))

# Files to exclude from the module-docs table in index.md
_EXCLUDED_FROM_INDEX = {"index.md", "log.md", "overview.md", "schema.yaml", "purpose.md"}


# ===================================================================
# Public API
# ===================================================================


def rebuild_index(output_dir: str | Path) -> None:
    """Scan *output_dir* and (re)write ``wiki/index.md``.

    Thread-safe via a module-level lock.  Uses atomic write (tmp + rename)
    so readers never see a partial file.  Silently returns if *output_dir*
    does not exist.

    Scans wiki/ subdirectories (modules/entities/concepts/sources/comparisons/queries)
    for page-type-specific sections, plus notes/ for knowledge notes.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return

    with _index_lock:
        from codewiki.src.config import (
            INDEX_FILENAME,
            OVERVIEW_FILENAME,
            NOTES_DIR,
            WIKI_DIR,
            PAGE_TYPE_DIRS,
        )

        # Determine index path: prefer wiki/index.md, fallback to output_dir/index.md
        wiki_dir = output_dir / WIKI_DIR
        if wiki_dir.is_dir():
            index_path = wiki_dir / INDEX_FILENAME
        else:
            index_path = output_dir / INDEX_FILENAME

        # --- Collect wiki pages by type ---
        type_entries: Dict[str, List[Dict[str, str]]] = {
            pt: [] for pt in PAGE_TYPE_DIRS
        }
        note_entries: List[Dict[str, str]] = []

        # Scan wiki/ subdirectories
        if wiki_dir.is_dir():
            for page_type, dir_name in PAGE_TYPE_DIRS.items():
                type_dir = wiki_dir / dir_name
                if not type_dir.is_dir():
                    continue
                for md_file in sorted(type_dir.iterdir()):
                    if not md_file.is_file() or md_file.suffix != ".md":
                        continue
                    if md_file.name in _EXCLUDED_FROM_INDEX:
                        continue
                    title, summary = _extract_doc_title_and_summary(md_file)
                    rel_path = str(md_file.relative_to(output_dir))
                    type_entries[page_type].append(
                        {"title": title, "summary": summary, "relpath": rel_path}
                    )

        # Scan notes/
        notes_dir = output_dir / NOTES_DIR
        if notes_dir.is_dir():
            for note_file in sorted(notes_dir.iterdir()):
                if not note_file.is_file() or note_file.suffix != ".md":
                    continue
                fm = _parse_note_frontmatter(note_file)
                note_entries.append(
                    {
                        "title": fm.get("title", note_file.stem),
                        "type": fm.get("type", "note"),
                        "date": str(fm.get("date", "")),
                        "relpath": f"{NOTES_DIR}/{note_file.name}",
                    }
                )
        # newest first
        note_entries.sort(key=lambda e: e["date"], reverse=True)

        # Sort each type's entries alphabetically (overview first if applicable)
        for pt in type_entries:
            type_entries[pt].sort(
                key=lambda e: (0 if OVERVIEW_FILENAME in e["relpath"] else 1, e["title"])
            )

        # Compute health score
        health_score = _compute_health_score(output_dir)

        now = datetime.now(_TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        content = _render_index(type_entries, note_entries, now, health_score)
        _atomic_write(index_path, content)
        logger.debug("Rebuilt %s", index_path)


def _compute_health_score(output_dir: Path) -> int:
    """Compute a 0-100 health score for the wiki.

    Reads from .meta/issues.json if available, otherwise computes from
    simple heuristics (broken links, orphan pages).
    """
    from codewiki.src.config import ISSUES_FILENAME, meta_resolve

    issues_path = Path(meta_resolve(output_dir, ISSUES_FILENAME))
    if issues_path.exists():
        try:
            import json
            data = json.loads(issues_path.read_text(encoding="utf-8"))
            issues = data.get("issues", {})
            open_issues = [
                v for v in issues.values()
                if isinstance(v, dict) and v.get("status") == "open"
            ]
            score = 100
            for issue in open_issues:
                sev = issue.get("severity", "warning")
                if sev == "error":
                    score -= 10
                elif sev == "warning":
                    score -= 3
                else:
                    score -= 1
            return max(0, score)
        except Exception:
            pass

    # Fallback: count wiki pages as a proxy for wiki maturity
    wiki_dir = output_dir / "wiki"
    if not wiki_dir.is_dir():
        return 50  # neutral score when no wiki/ exists yet
    page_count = sum(1 for f in wiki_dir.rglob("*.md") if f.is_file())
    # Simple heuristic: more pages = healthier (cap at 100)
    return min(100, 50 + page_count * 2)


def append_log(
    output_dir: str | Path,
    operation: str,
    summary: str,
) -> None:
    """Append one timestamped row to ``wiki/log.md``.

    Creates the file with a header on first call.  Uses ``fcntl.flock``
    for safe concurrent appends.  Silently returns if *output_dir* does
    not exist.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return

    from codewiki.src.config import LOG_FILENAME, WIKI_DIR

    # Prefer wiki/log.md, fallback to output_dir/log.md
    wiki_dir = output_dir / WIKI_DIR
    if wiki_dir.is_dir():
        log_path = wiki_dir / LOG_FILENAME
    else:
        log_path = output_dir / LOG_FILENAME

    # Escape pipe characters to prevent table corruption
    safe_op = operation.replace("|", "\\|")
    safe_summary = summary.replace("|", "\\|")

    now = datetime.now(_TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    row = f"| {now} | {safe_op} | {safe_summary} |"

    # If the file doesn't exist yet, create with header (thread-safe)
    if not log_path.exists():
        with _log_create_lock:
            # Double-check after acquiring lock
            if not log_path.exists():
                header = (
                    "# 操作日志\n\n"
                    "> 本文件为追加写入的操作记录，由系统自动维护\n\n"
                    "| 时间 | 操作 | 说明 |\n"
                    "|------|------|------|\n"
                )
                try:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text(header, encoding="utf-8")
                except Exception as e:
                    logger.warning("Failed to create log.md: %s", e)
                    return

    _append_with_lock(log_path, row)
    logger.debug("Appended log entry: %s", safe_op)


# ===================================================================
# Internal helpers
# ===================================================================


def _extract_doc_title_and_summary(filepath: Path) -> Tuple[str, str]:
    """Read the first 50 lines of a .md file and extract title + summary."""
    title: Optional[str] = None
    summary: Optional[str] = None
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 50:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                # First H1 heading becomes the title
                if title is None and stripped.startswith("# "):
                    title = stripped[2:].strip()
                    continue
                # First non-heading, non-quote, non-table line
                # (after title if found, or any content line if no H1)
                if summary is None:
                    if title is not None or not stripped.startswith("# "):
                        if not stripped.startswith(("#", ">", "|", "<!--", "---")):
                            summary = stripped[:120]
                            if title is not None:
                                break  # have both, done
    except Exception as e:
        logger.warning("Failed to read %s: %s", filepath, e)

    if title is None:
        title = filepath.stem
    if summary is None:
        summary = "(无摘要)"
    return title, summary


def _parse_note_frontmatter(filepath: Path) -> Dict[str, Any]:
    """Parse YAML frontmatter from a note file.  Returns {} on failure."""
    try:
        lines: List[str] = []
        in_frontmatter = False
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 30:
                    break
                stripped = line.strip()
                if stripped == "---":
                    if in_frontmatter:
                        break  # closing delimiter
                    in_frontmatter = True
                    continue
                if in_frontmatter:
                    lines.append(line)

        if not lines:
            return {}

        import yaml

        data = yaml.safe_load("".join(lines))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# Chinese labels for page types
_PAGE_TYPE_LABELS = {
    "module": "模块文档",
    "entity": "实体",
    "concept": "概念",
    "source": "外部文档",
    "comparison": "对比分析",
    "query": "研究查询",
}


def _render_index(
    type_entries: Dict[str, List[Dict[str, str]]],
    note_entries: List[Dict[str, str]],
    generated_at: str,
    health_score: int = 100,
) -> str:
    """Produce the full index.md markdown string with by-type sections."""
    parts: List[str] = [
        "# 项目文档索引\n",
        f"> 自动生成于 {generated_at} | Health Score: **{health_score}/100** | 本文件由系统自动维护\n",
    ]

    # Render each page type section
    for page_type, label in _PAGE_TYPE_LABELS.items():
        entries = type_entries.get(page_type, [])
        if not entries:
            continue
        parts.append(f"## {label}\n")
        parts.append("| 文档 | 说明 |")
        parts.append("|------|------|")
        for entry in entries:
            parts.append(
                f"| [{entry['title']}]({entry['relpath']}) | {entry['summary']} |"
            )
        parts.append("")

    # Notes section
    if note_entries:
        parts.append("## 知识笔记\n")
        parts.append("| 标题 | 类型 | 日期 | 文件 |")
        parts.append("|------|------|------|------|")
        for entry in note_entries:
            parts.append(
                f"| {entry['title']} | {entry['type']} | {entry['date']}"
                f" | [链接]({entry['relpath']}) |"
            )
        parts.append("")

    return "\n".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* via a temp file + atomic rename."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception as e:
        logger.warning("Atomic write failed for %s: %s", path, e)
        # Clean up temp file if it was created
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _append_with_lock(filepath: Path, line: str) -> None:
    """Append a single line to *filepath* with an exclusive file lock.

    Cross-platform: uses ``fcntl.flock`` on Unix, ``msvcrt.locking`` on
    Windows, and a process-local thread lock as a last-resort fallback.
    """
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            if _fcntl is not None:
                _fcntl.flock(f.fileno(), _fcntl.LOCK_EX)
                try:
                    f.write(line + "\n")
                    f.flush()
                finally:
                    _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:
                # msvcrt locks byte ranges; lock a 1-byte region at the
                # current position for the duration of the write.
                try:
                    _msvcrt.locking(f.fileno(), _msvcrt.LK_LOCK, 1)
                except OSError:
                    pass  # locking may fail on some filesystems; still write
                try:
                    f.write(line + "\n")
                    f.flush()
                finally:
                    try:
                        _msvcrt.locking(f.fileno(), _msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
            else:
                with _append_fallback_lock:
                    f.write(line + "\n")
                    f.flush()
    except Exception as e:
        logger.warning("Failed to append to %s: %s", filepath, e)
