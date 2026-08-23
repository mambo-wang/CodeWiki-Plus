"""doc_update_notify — Wiki 文档更新后的关联笔记主动提醒（V7'，用户改造版）.

原 V7 设计（lint 拉取式输入感知复核）被用户改造为**推送式**：更新代码
Wiki 文档后，主动在工具响应里提醒"哪些笔记声明依赖了这个模块、其结论
是否仍然成立"。触发点在写侧（write_doc_file / edit_doc_file 完成时），
而非读侧（lint 周期扫描）——刚改完文档的时刻，关联笔记的复核语境最热。

匹配规则：扫描 notes/*.md frontmatter 的 ``related_modules``（或
``related``），与本次更新的模块名（page stem / 标题，大小写与连字符归一）
求交集。命中笔记按修改时间倒序列出（最近动过的优先复核）。

输出形态：``affected_notes(output_dir, module_names)`` 返回结构化列表，
doc_writer 把它渲染进响应 JSON 的 ``note_review_reminder`` 字段——
提醒而非强制，Agent 应转告用户并等 confirm/review 指令。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _norm(name: str) -> str:
    """Module-name normalisation: case/underscore/hyphen insensitive."""
    return re.sub(r"[\s_\-]+", "", str(name)).lower()


def _note_related(fm_block: str) -> List[str]:
    """Extract related_modules (inline or block list) from frontmatter text."""
    out: List[str] = []
    inline = re.search(r"^[ 	]*related_modules:\s*\[(.*?)\]\s*$", fm_block, re.MULTILINE)
    if inline and inline.group(1).strip():
        out = [v.strip().strip("'\"") for v in inline.group(1).split(",") if v.strip()]
        return out
    bl = re.search(r"^related_modules:\s*\n((?:\s+-\s+.*\n?)+)", fm_block, re.MULTILINE)
    if bl:
        out = [
            v.strip().lstrip("-").strip().strip("'\"")
            for v in bl.group(1).splitlines() if v.strip()
        ]
    return out


def affected_notes(
    output_dir: Path,
    module_names: List[str],
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Notes whose ``related_modules`` reference any of *module_names*.

    Returns ``[{file, title, note_type, status, matched_module}]`` sorted by
    note mtime desc (most recently touched first — those matter most to the
    user's current context).  Best-effort: unreadable notes are skipped.
    """
    if not module_names:
        return []
    wanted = {_norm(m) for m in module_names if str(m).strip()}
    if not wanted:
        return []
    od = Path(output_dir)
    from codewiki.src.config import NOTES_DIR
    notes_dir = od / NOTES_DIR
    if not notes_dir.is_dir():
        return []
    hits: List[Dict[str, Any]] = []
    for note_path in sorted(notes_dir.glob("*.md")):
        try:
            text = note_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _FM_RE.match(text)
        if not m:
            continue
        block = m.group(1)
        related = _note_related(block)
        matched = next(
            (r for r in related if _norm(r) in wanted), None
        )
        if matched is None:
            continue
        title = next(
            (ln.split(":", 1)[1].strip().strip("'\"")
             for ln in block.splitlines() if ln.startswith("title:")),
            note_path.stem,
        )
        ntype = ""
        for ln in block.splitlines():
            if ln.startswith("type:") or ln.startswith("note_type:"):
                ntype = ln.split(":", 1)[1].strip()
                break
        status = "stable"
        for ln in block.splitlines():
            if ln.startswith("status:"):
                status = ln.split(":", 1)[1].strip()
                break
        hits.append({
            "file": str(note_path.relative_to(od)).replace("\\", "/"),
            "title": title,
            "note_type": ntype,
            "status": status,
            "matched_module": matched,
            "_mtime": note_path.stat().st_mtime,
        })
    hits.sort(key=lambda h: -h["_mtime"])
    for h in hits:
        h.pop("_mtime")
    return hits[:limit]


def reminder_payload(
    output_dir: Path,
    module_names: List[str],
) -> Optional[Dict[str, Any]]:
    """Build the ``note_review_reminder`` response field (None when empty).

    The message addresses the calling agent: surface it to the user and let
    them decide (confirm the note still holds, review, or edit) — this is a
    nudge, never an automatic status change.
    """
    notes = affected_notes(output_dir, module_names)
    if not notes:
        return None
    return {
        "updated_modules": module_names,
        "notes": notes,
        "message": (
            f"{len(notes)} note(s) declare these module(s) in related_modules. "
            "The wiki page just changed — their conclusions may be stale. "
            "Surface this list to the user and ask whether to review/confirm "
            "each note (confirm_note renews stale_after; edit if outdated)."
        ),
    }
