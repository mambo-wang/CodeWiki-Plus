"""MCP tool helpers: index.md and log.md auto-generation.

Provides ``rebuild_index`` (rebuilds the content catalog) and ``append_log``
(appends a timestamped operation entry).  Both are designed to be called
at the end of other tool handlers, wrapped in try/except so failures never
block the primary operation.
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lock for index rebuilds (serialises concurrent rebuild calls)
# ---------------------------------------------------------------------------
_index_lock = threading.Lock()

# Lock for log file creation (prevents duplicate headers on first concurrent call)
_log_create_lock = threading.Lock()

# Timezone: UTC+8 for display, but we use utcnow() + format manually
_TZ_CST = timezone(timedelta(hours=8))

# Files to exclude from the module-docs table in index.md
_EXCLUDED_FROM_INDEX = {"index.md", "log.md"}


# ===================================================================
# Public API
# ===================================================================


def rebuild_index(output_dir: str | Path) -> None:
    """Scan *output_dir* and (re)write ``index.md``.

    Thread-safe via a module-level lock.  Uses atomic write (tmp + rename)
    so readers never see a partial file.  Silently returns if *output_dir*
    does not exist.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return

    with _index_lock:
        module_entries: List[Dict[str, str]] = []
        note_entries: List[Dict[str, str]] = []

        # --- module docs (root-level *.md) ---
        from codewiki.src.config import (
            INDEX_FILENAME,
            LOG_FILENAME,
            OVERVIEW_FILENAME,
            NOTES_DIR,
        )

        _EXCLUDED = {INDEX_FILENAME, LOG_FILENAME}

        for md_file in sorted(output_dir.iterdir()):
            if not md_file.is_file():
                continue
            if md_file.suffix != ".md":
                continue
            if md_file.name in _EXCLUDED:
                continue
            title, summary = _extract_doc_title_and_summary(md_file)
            module_entries.append(
                {"title": title, "summary": summary, "filename": md_file.name}
            )

        # overview.md first, then alphabetical
        module_entries.sort(
            key=lambda e: (0 if e["filename"] == OVERVIEW_FILENAME else 1, e["title"])
        )

        # --- notes ---
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

        now = datetime.now(_TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        content = _render_index(module_entries, note_entries, now)
        _atomic_write(output_dir / INDEX_FILENAME, content)
        logger.debug("Rebuilt %s", output_dir / INDEX_FILENAME)


def append_log(
    output_dir: str | Path,
    operation: str,
    summary: str,
) -> None:
    """Append one timestamped row to ``log.md``.

    Creates the file with a header on first call.  Uses ``fcntl.flock``
    for safe concurrent appends.  Silently returns if *output_dir* does
    not exist.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return

    from codewiki.src.config import LOG_FILENAME

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


def _render_index(
    module_entries: List[Dict[str, str]],
    note_entries: List[Dict[str, str]],
    generated_at: str,
) -> str:
    """Produce the full index.md markdown string."""
    parts: List[str] = [
        "# 项目文档索引\n",
        f"> 自动生成于 {generated_at} | 本文件由系统自动维护\n",
        "## 模块文档\n",
        "| 文档 | 说明 |",
        "|------|------|",
    ]
    for entry in module_entries:
        parts.append(
            f"| [{entry['title']}]({entry['filename']}) | {entry['summary']} |"
        )

    parts.append("")
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
    """Append a single line to *filepath* with an exclusive file lock."""
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line + "\n")
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.warning("Failed to append to %s: %s", filepath, e)
