"""note_merge — 字段级预合并（V3, OpenViking merge_op 借鉴）.

docs/OpenViking借鉴全景路线图.md V3：同主题多条 draft 笔记按**字段策略**
预合并为一条 draft——标题/元信息取最新（replace），正文按树龄升序拼接并带
来源标记（append），tags 并集（union），计数类累加（sum）。借的是 OpenViking
的合并**粒度**，不借其无闸门直写：合并产物一律 status: draft，过
confirm_note 闸门后才转正；被合并的原 draft 组由调用方在确认后经
batch_set_status 置 superseded。

策略来源：note_types 权威表的 ``merge_fields``（V4），可按类型覆盖。

纯函数优先：``merge_notes(..., write=False)`` 只返回合并产物（不落盘，
拒绝路径原组零变化）；``write=True`` 写出一条新 draft。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split_fm(text: str) -> Tuple[Dict[str, str], str]:
    """Minimal flat frontmatter scan (string values only, quotes stripped)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line[:1] in ("#", "-"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip("'\"")
    return fm, text[m.end() :]


def _note_age_key(fm: Dict[str, str]) -> str:
    """Sort key: metadata.date / date / generated-at, ascending (oldest first)."""
    return (
        fm.get("metadata.date", "").strip("{}").split("at:")[-1].strip("'\" }")
        or fm.get("date", "")
        or "9999"
    )


def _slugify(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-")
    return text[:60] or "merged-note"


def _list_field(fm_text: str, key: str) -> List[str]:
    """Pull a YAML list field (inline or block) out of raw frontmatter text."""
    m = _FM_RE.match(fm_text)
    block = m.group(1) if m else ""
    out: List[str] = []
    inline = re.search(rf"^[ 	]*{key}:\s*\[(.*?)\]\s*$", block, re.MULTILINE)
    if inline and inline.group(1).strip():
        out = [v.strip().strip("'\"") for v in inline.group(1).split(",") if v.strip()]
        return out
    bl = re.search(rf"^{key}:\s*\n((?:\s+-\s+.*\n?)+)", block, re.MULTILINE)
    if bl:
        out = [
            v.strip().lstrip("-").strip().strip("'\"")
            for v in bl.group(1).splitlines()
            if v.strip()
        ]
    return out


def merge_notes(
    output_dir: Path,
    files: List[str],
    schema: Optional[dict] = None,
    *,
    write: bool = False,
    new_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge same-topic draft notes into one draft per field strategies.

    Returns ``{"sources": [...], "title": ..., "content": ...}`` and, when
    *write* is True, additionally ``{"written": "<rel path>"}``.  Sources are
    never modified here — marking them superseded is the caller's job after
    the merged draft passes the confirm gate.
    """
    od = Path(output_dir)
    loaded: List[Tuple[str, str, Dict[str, str], str]] = []  # (rel, fm_text, fm, body)
    for raw in files:
        rel = str(raw).replace("\\", "/")
        p = od / rel
        if not p.is_file():
            return {"error": f"source not found: {rel}"}
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, body = _split_fm(text)
        loaded.append((rel, text, fm, body))
    if len(loaded) < 2:
        return {"error": "merge_notes requires at least two source files"}

    # Ascending age: oldest body first so the merged story reads chronologically.
    loaded.sort(key=lambda t: _note_age_key(t[2]))
    newest = loaded[-1]
    note_type = (newest[2].get("type") or newest[2].get("note_type") or "general").lower()

    from codewiki.mcp.tools.note_types import merge_fields_for

    strategies = merge_fields_for(note_type, schema)

    title = (new_title or newest[2].get("title") or newest[0].rsplit("/", 1)[-1]).strip("'\"")

    # replace 取最新（排序列表末位）；union 全量并集保序。
    related_new = _list_field(newest[1], "related_modules")
    related_all: List[str] = []
    for _, fm_text, _, _ in loaded:
        for m in _list_field(fm_text, "related_modules"):
            if m not in related_all:
                related_all.append(m)
    tags_all: List[str] = []
    for _, fm_text, _, _ in loaded:
        for t in _list_field(fm_text, "tags"):
            if t not in tags_all:
                tags_all.append(t)
    if note_type not in tags_all:
        tags_all.append(note_type)

    related = related_new if strategies.get("related_modules") == "replace" else related_all
    tags = (
        tags_all if strategies.get("tags", "union") == "union" else _list_field(newest[1], "tags")
    )

    # body: append 策略——按树龄升序，每段带来源标记；replace 则只留最新正文。
    body_parts: List[str] = []
    if strategies.get("body", "append") == "replace":
        body_parts.append(newest[3].strip())
    else:
        for rel, _, _, body in loaded:
            body_parts.append(f"> 合并自 `{rel}`\n\n{body.strip()}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_lines = [
        "---",
        f'title: "{title}"',
        f"type: {note_type}",
        "status: draft",
        f"generated: {{ by: note_merge, at: {now} }}",
    ]
    if related:
        fm_lines.append("related_modules: [" + ", ".join(f'"{r}"' for r in related) + "]")
    if tags:
        fm_lines.append("tags: [" + ", ".join(f'"{t}"' for t in tags) + "]")
    fm_lines.append("metadata:")
    fm_lines.append("  merged_from: [" + ", ".join(f'"{r}"' for r, _, _, _ in loaded) + "]")
    content = "\n".join(fm_lines) + "\n\n" + "\n\n---\n\n".join(body_parts) + "\n"

    result: Dict[str, Any] = {
        "sources": [rel for rel, _, _, _ in loaded],
        "title": title,
        "note_type": note_type,
        "strategies": strategies,
        "content": content,
    }
    if write:
        from codewiki.src.config import NOTES_DIR

        notes_dir = od / NOTES_DIR
        notes_dir.mkdir(parents=True, exist_ok=True)
        out_path = notes_dir / f"{_slugify(title)}.md"
        n = 1
        while out_path.exists():
            n += 1
            out_path = notes_dir / f"{_slugify(title)}-{n}.md"
        # Phase 2 (§5.3): unique-filename new-file write — locked_write
        # (two processes merging the same title resolve different -N names;
        # the lock only protects against torn writes of the same path).
        from codewiki.src.store import locked_write

        locked_write(out_path, content)
        result["written"] = str(out_path.relative_to(od)).replace("\\", "/")
    return result
