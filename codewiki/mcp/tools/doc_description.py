"""doc_description — frontmatter description 抽取与回填（V2 前置）.

V1（独立 abstract 字段）已决策不做：OKF frontmatter 本就有 ``description``
标准键（frontmatter.py 白名单），只是从未被写入（真实 repowiki 26 篇 wiki
文档 0 篇有值）。本模块把"目录级摘要"落到**既有** description 键上：

- ``extract_lede(body)`` — 纯函数：首个 ``## `` 标题前的段落，截前两句、
  上限 160 字符。零 LLM 依赖（规则抽取），幂等。
- ``ensure_description(path)`` — 文档缺 description 时补写（有则不动），
  返回是否写入。frontmatter 无 ``---`` 头的文档跳过（不破坏非 OKF 文件）。
- ``backfill_dir(output_dir)`` — 批量回填 wiki 目录，返回统计。

消费方：query_wiki 注入预算降级行（wiki_search/knowledge_loop）、
doc_writer 写入路径（新文档落盘即带 description）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_MAX_CHARS = 160
_MAX_SENTENCES = 2
# 句末切分：中英文句末标点均可（中文标点后无空白，用 finditer 切）。
_SENT_END = re.compile(r"[。！？!?\.]")


def _first_sentences(text: str, n: int) -> str:
    """First *n* sentences — CJK-aware (sentence-end punct needs no space)."""
    ends = [m.end() for m in _SENT_END.finditer(text)]
    if not ends:
        return text.strip()
    if len(ends) < n:
        return text.strip()
    return text[: ends[n - 1]].strip()


def extract_lede(body: str) -> str:
    """First paragraph (before the first ``## `` heading) → ≤2 sentences, ≤160 chars."""
    # strip frontmatter if still present
    if body.lstrip().startswith("---"):
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?", body.lstrip(), re.DOTALL)
        if m:
            body = body.lstrip()[m.end() :]

    # leading blockquote (project convention: meta blockquote) counts as lede
    # only when no plain paragraph precedes it — take the first non-empty,
    # non-heading, non-table block.
    # module 文档约定正文为 "# 标题 → ## 章节 → 段落"：H1 与首个 H2 之间
    # 常无导语段，此时 lede 取首个 H2 章节内的第一个段落（"模块职责"的
    # 开头正是文档的事实摘要）。
    def _first_para(text: str) -> str:
        for block in re.split(r"\n\s*\n", text):
            b = block.strip()
            if not b or b.startswith("#") or b.startswith("|") or b.startswith("<!--"):
                continue
            return "\n".join(ln.strip() for ln in b.splitlines())
        return ""

    head = body.split("\n## ", 1)[0]
    lines = head.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    para = _first_para("\n".join(lines))
    if not para and "\n## " in body:
        # strip the section heading itself, take the first paragraph after it
        after = body.split("\n## ", 1)[1]
        after = re.split(r"\n", after, 1)[1] if "\n" in after else after
        para = _first_para(after)
    if not para:
        return ""
    lede = _first_sentences(para, _MAX_SENTENCES)
    lede = re.sub(r"\s+", " ", lede)
    return lede[:_MAX_CHARS]


def ensure_description(path: Path) -> bool:
    """Write ``description:`` into *path*'s frontmatter when absent. Idempotent.

    Byte-level rewrite (read_bytes/write_bytes): the codebase has a known pitfall
    where ``write_text`` re-translates line endings on mixed-CRLF files and
    corrupts diffs.  The inserted line inherits the file's dominant EOL.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if not raw.startswith(b"---"):
        return False  # not an OKF/frontmatter file — leave untouched
    m = re.match(rb"\A---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
    if not m:
        return False
    block = m.group(1)
    if re.search(rb"^description:\s*\S", block, re.MULTILINE):
        return False
    body = raw[m.end() :]
    lede = extract_lede(body.decode("utf-8", errors="replace"))
    if not lede:
        return False
    lede_escaped = lede.replace("\\", "\\\\").replace('"', '\\"')
    line = f'description: "{lede_escaped}"'.encode("utf-8")
    # 纯插入式写入（不重建 frontmatter 头尾，原字节零改动）：
    # 在 frontmatter 结束 ``\n---`` 的换行后插入一行。CRLF 文件下该 \n 前
    # 有 \r（属上一行行尾）——插入形态为 head(\r) + \n + line + (\r) + tail(\n---)，
    # 保证不产生孤立 \r（git clean 不可规范化，会造成整文件 diff）。
    fm_end = raw.find(b"\n---", 3)
    if fm_end == -1:
        return False
    head_part = raw[:fm_end]  # ends with b"\r" on CRLF files, else content
    tail_part = raw[fm_end:]  # starts with b"\n---"
    crlf = head_part.endswith(b"\r")
    new_raw = head_part + b"\n" + line + (b"\r" if crlf else b"") + tail_part
    try:
        path.write_bytes(new_raw)
        return True
    except OSError as e:
        logger.warning("description backfill failed for %s: %s", path, e)
        return False


def backfill_dir(output_dir: Path) -> Dict[str, int]:
    """Backfill description for all wiki .md files. Returns {written, skipped, total}."""
    od = Path(output_dir)
    wiki = od / "wiki"
    roots = [wiki] if wiki.is_dir() else [od]
    written = scanned = 0
    for root in roots:
        for p in sorted(root.rglob("*.md")):
            scanned += 1
            if ensure_description(p):
                written += 1
    return {"written": written, "skipped": scanned - written, "total": scanned}
