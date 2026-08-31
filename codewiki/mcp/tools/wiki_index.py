"""MCP tool helpers: index.md and log.md auto-generation.

Provides ``rebuild_index`` (rebuilds the content catalog) and ``append_log``
(appends a timestamped operation entry).  Both are designed to be called
at the end of other tool handlers, wrapped in try/except so failures never
block the primary operation.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.src.locks import file_lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-platform file locking lives in codewiki.src.locks; _append_with_lock
# below is a thin convenience wrapper over the generic read-modify-write lock.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Module-level lock for index rebuilds (serialises concurrent rebuild calls)
# ---------------------------------------------------------------------------
_index_lock = threading.Lock()

# Lock for log file creation (prevents duplicate headers on first concurrent call)
_log_create_lock = threading.Lock()

# Timezone: UTC+8 for display, but we use utcnow() + format manually
_TZ_CST = timezone(timedelta(hours=8))

# Files to exclude from the module-docs table in index.md
_EXCLUDED_FROM_INDEX = {"index.md", "log.md", "overview.md", "schema.yaml"}


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

        # Index always lives in wiki/index.md (create wiki/ if needed)
        wiki_dir = output_dir / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)
        index_path = wiki_dir / INDEX_FILENAME

        # --- Collect wiki pages by type ---
        type_entries: Dict[str, List[Dict[str, str]]] = {pt: [] for pt in PAGE_TYPE_DIRS}
        # Root-level wiki/ files (doctrine.md, reading-guide.md, ...) — not a
        # subdirectory page type, but real pages that must appear in the index
        # so they are reachable (and not flagged as orphans).
        root_entries: List[Dict[str, str]] = []
        note_entries: List[Dict[str, str]] = []

        # Scan wiki/ subdirectories
        if wiki_dir.is_dir():
            # wiki/ 根下的页面文件（非系统文件、非子目录）
            for md_file in sorted(wiki_dir.iterdir()):
                if not md_file.is_file() or md_file.suffix != ".md":
                    continue
                if md_file.name in _EXCLUDED_FROM_INDEX:
                    continue
                title, summary = _extract_doc_title_and_summary(md_file)
                root_entries.append(
                    {
                        "title": title,
                        "summary": summary,
                        "relpath": md_file.name,
                    }
                )
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
                    # Paths relative to wiki/ (where index.md lives)
                    rel_path = str(md_file.relative_to(wiki_dir)).replace("\\", "/")
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
                        "date": str(
                            fm.get("date", "") or (fm.get("metadata") or {}).get("date", "")
                        ),
                        "relpath": f"../{NOTES_DIR}/{note_file.name}",
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
        content = _render_index(type_entries, note_entries, now, health_score, root_entries)
        _atomic_write(index_path, content)
        logger.debug("Rebuilt %s", index_path)


def _compute_health_score(output_dir: Path) -> int:
    """Compute a 0-100 health score for the wiki.

    Uses the same calculation as lint_wiki (the authoritative source):
    run file-based lint checks and apply the scoring formula
    (100 - 10*errors - 3*warnings - 1*info, clamped to 0).
    """
    try:
        from codewiki.mcp.tools.wiki_lint import (
            _check_stale_refs,
            _check_broken_links,
            _check_orphan_pages,
            _check_no_outlinks,
            _check_missing_aliases,
            _check_stale_sources,
            _check_superseded_pages,
            _check_overview_stale_lint,
            _check_unsupported_claims,
            _load_module_tree,
            _build_anchor_map,
        )

        module_tree = _load_module_tree(output_dir)
        anchor_map = _build_anchor_map(output_dir)

        issues: list = []
        issues.extend(_check_stale_refs(output_dir, module_tree))
        issues.extend(_check_broken_links(output_dir))
        issues.extend(_check_orphan_pages(output_dir, anchor_map))
        issues.extend(_check_no_outlinks(output_dir, anchor_map))
        issues.extend(_check_missing_aliases(output_dir))
        issues.extend(_check_stale_sources(output_dir))
        issues.extend(_check_superseded_pages(output_dir))
        issues.extend(_check_overview_stale_lint(output_dir))
        issues.extend(_check_unsupported_claims(output_dir))

        # Same scoring formula as lint_wiki
        score = 100
        for issue in issues:
            sev = issue.get("severity", "info")
            if sev == "error":
                score -= 10
            elif sev == "warning":
                score -= 3
            else:
                score -= 1
        return max(0, score)
    except Exception:
        # If lint checks fail entirely, fall back to neutral score
        return 50


def append_log(
    output_dir: str | Path,
    operation: str,
    summary: str,
) -> None:
    """Record one operation in ``wiki/log.md`` (OKF v0.2 §9 format).

    §9: flat list of date-grouped entries, newest first::

        # Directory Update Log

        ## 2026-08-03
        * **write_doc_file**: Created foo.md

    Entries for the same day are appended to that day's block; a new day
    section is inserted at the top.  Legacy v5.1.x table logs are kept
    below the new sections, marked once with an archive comment.
    Silently returns if *output_dir* does not exist.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return

    from codewiki.src.config import LOG_FILENAME, WIKI_DIR

    # Log always lives in wiki/log.md (create wiki/ if needed)
    wiki_dir = output_dir / WIKI_DIR
    wiki_dir.mkdir(parents=True, exist_ok=True)
    log_path = wiki_dir / LOG_FILENAME

    safe_op = operation.replace("\n", " ").replace("|", "/")
    safe_summary = summary.replace("\n", " ").replace("|", "/")
    now = datetime.now(_TZ_CST)
    date_str = now.strftime("%Y-%m-%d")
    entry = f"* **{safe_op}**: {safe_summary}"

    with _log_create_lock:
        if not log_path.exists():
            header = (
                "# 操作日志\n\n> 按日期倒序分组的操作记录，由系统自动维护（OKF v0.2 §9 格式）\n\n"
            )
            try:
                log_path.write_text(header, encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to create log.md: %s", e)
                return

        try:
            content = log_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read log.md: %s", e)
            return

        lines = content.split("\n")
        n = len(lines)

        # Anchor: first date heading, or legacy table row (v5.1.x format)
        idx = 0
        while idx < n and not lines[idx].startswith("## ") and not lines[idx].startswith("|"):
            idx += 1

        if idx < n and lines[idx].startswith("|"):
            # Legacy table log: insert new-format section before the table,
            # marking the archive boundary once.
            marker = "<!-- 以下为 v5.1.x 旧格式日志存档 -->"
            block = [f"## {date_str}", entry, ""]
            if marker not in content:
                block.append(marker)
            lines = lines[:idx] + block + lines[idx:]
        elif idx < n and lines[idx].strip() == f"## {date_str}":
            # Same-day section exists: append after its last non-empty line
            j = idx + 1
            while j < n and not lines[j].startswith("## "):
                j += 1
            k = j
            while k > idx + 1 and lines[k - 1].strip() == "":
                k -= 1
            lines.insert(k, entry)
        else:
            # New day section at the top (newest first)
            lines = lines[:idx] + [f"## {date_str}", entry, ""] + lines[idx:]

        _atomic_write(log_path, "\n".join(lines))
    logger.debug("Appended log entry: %s", safe_op)


# ===================================================================
# Internal helpers
# ===================================================================


def _extract_doc_title_and_summary(filepath: Path) -> Tuple[str, str]:
    """Extract title + summary for an index entry.

    OKF v0.2 §8: entries SHOULD carry the concept's frontmatter
    ``description``.  Prefer ``title``/``description`` from YAML
    frontmatter, falling back to H1 / first-paragraph scanning.
    """
    fm = _parse_note_frontmatter(filepath)  # generic frontmatter parser
    fm_title = fm.get("title")
    fm_desc = fm.get("description")
    if (
        isinstance(fm_title, str)
        and fm_title.strip()
        and isinstance(fm_desc, str)
        and fm_desc.strip()
    ):
        return fm_title.strip(), fm_desc.strip()[:120]

    title: Optional[str] = (
        fm_title.strip() if isinstance(fm_title, str) and fm_title.strip() else None
    )
    summary: Optional[str] = (
        fm_desc.strip()[:120] if isinstance(fm_desc, str) and fm_desc.strip() else None
    )
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
    "scenario": "场景方法",
}


def _render_index(
    type_entries: Dict[str, List[Dict[str, str]]],
    note_entries: List[Dict[str, str]],
    generated_at: str,
    health_score: int = 100,
    root_entries: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Produce the full index.md markdown string (OKF v0.2 §8 format).

    §8: body sections group concepts as ``* [Title](url) - description``
    bullets.  §12: the bundle-root index may carry only ``okf_version``
    frontmatter; generation metadata lives in an HTML comment so the file
    stays conformant while keeping its self-describing header.
    """
    try:
        from codewiki.src.config import OKF_VERSION
    except Exception:
        OKF_VERSION = "0.2"
    parts: List[str] = [
        "---",
        f'okf_version: "{OKF_VERSION}"',
        "aliases:",
        "- 项目文档索引",
        "- 文档索引",
        "- 知识笔记索引",
        "---",
        "",
        f"<!-- 自动生成于 {generated_at} | Health Score: {health_score}/100 | 本文件由系统自动维护 -->",
        "",
        "# 项目文档索引",
        "",
    ]

    # Root-level pages (wiki/doctrine.md, wiki/reading-guide.md, ...)
    if root_entries:
        parts.append("## 入门指引")
        parts.append("")
        for entry in root_entries:
            parts.append(f"* [{entry['title']}]({entry['relpath']}) - {entry['summary']}")
        parts.append("")

    # Render each page type section (§8 bullet lists)
    for page_type, label in _PAGE_TYPE_LABELS.items():
        entries = type_entries.get(page_type, [])
        if not entries:
            continue
        parts.append(f"## {label}")
        parts.append("")
        for entry in entries:
            parts.append(f"* [{entry['title']}]({entry['relpath']}) - {entry['summary']}")
        parts.append("")

    # Notes section
    if note_entries:
        parts.append("## 知识笔记")
        parts.append("")
        for entry in note_entries:
            meta = f" ({entry['type']}, {entry['date']})" if entry.get("date") else ""
            parts.append(f"* [{entry['title']}]({entry['relpath']}) - {entry['type']}{meta}")
        parts.append("")

    return "\n".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* via a temp file + atomic rename.

    Delegates to the shared store implementation (adds Windows retry); failure
    is logged and swallowed, matching this module's best-effort contract.
    """
    from codewiki.src.store import atomic_write

    try:
        atomic_write(path, content)
    except OSError as e:
        logger.warning("Atomic write failed for %s: %s", path, e)


def _append_with_lock(filepath: Path, line: str) -> None:
    """Append a single line to *filepath* with an exclusive file lock.

    Thin wrapper over :func:`codewiki.src.locks.file_lock` (cross-platform:
    ``fcntl.flock`` on Unix, ``msvcrt.locking`` on Windows, plus a
    process-local thread layer on every platform).  All I/O goes through
    the handle that holds the lock (required on Windows).
    """
    try:
        with file_lock(filepath) as f:
            f.seek(0, 2)  # end of file
            f.write(line + "\n")
    except Exception as e:
        logger.warning("Failed to append to %s: %s", filepath, e)
