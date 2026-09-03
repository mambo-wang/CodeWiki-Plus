"""injection_budget — 注入预算降级（V2, OpenViking auto-recall 借鉴）.

docs/OpenViking借鉴全景路线图.md V2：AGENTS.md 约定段与 query_wiki 结果
是 CodeWiki 向 IDE 上下文"注入"的两个出口，此前无预算控制——知识越多、
上下文越挤。借鉴 OpenViking auto-recall 的降级形态：预算内条目给完整
内容，超预算条目压为一行 ``路径 | 分数 | description``（不丢线索，只降
信息量，Agent 需要时再读）。

配置（schema.yaml conventions 段，0 = 关闭降级保持现状）::

    conventions:
      injection_budget:
        search_result_chars: 1200   # query_wiki 结果 snippet 总预算（字符）
        agents_md_module_lines: 30  # AGENTS.md 模块列表行数上限

预算按字符近似（中文场景 len()），不引 tokenizer——这是排序提示预算，
不是计费精度。
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BUDGET = {
    "search_result_chars": 1200,
    "agents_md_module_lines": 30,
}

# P0-1 (claude-mem borrowing): retrieval-cost visibility defaults. est_tokens
# = ceil(chars / chars_per_token) — a decision hint, never billing precision.
_DEFAULT_RETRIEVAL_COST = {
    "enabled": 1,  # truthy int so a missing schema yields legacy-off-safe config
    "chars_per_token": 4,
    "expand_hint": 1,
}

_DESC_RE = re.compile(r'^description:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)


def load_budget(schema: Optional[dict]) -> Dict[str, int]:
    """Resolve injection budget config (defaults → schema overrides; 0 = off)."""
    cfg = dict(_DEFAULT_BUDGET)
    conv = (schema or {}).get("conventions") or {}
    raw = conv.get("injection_budget")
    if isinstance(raw, dict):
        for k in _DEFAULT_BUDGET:
            try:
                if raw.get(k) is not None:
                    cfg[k] = max(0, int(raw[k]))
            except (TypeError, ValueError):
                continue
    return cfg


def load_retrieval_cost(schema: Optional[dict]) -> Dict[str, Any]:
    """Resolve retrieval-cost config (defaults → schema overrides).

    P0-1（claude-mem 借鉴）: ``conventions.retrieval_cost`` —
    ``enabled`` false = legacy (no est_tokens field), ``chars_per_token``
    is the len()/token divisor, ``expand_hint`` false = no cost_hint.
    Boolean-ish values are coerced via bool().
    """
    cfg: Dict[str, Any] = {
        "enabled": bool(_DEFAULT_RETRIEVAL_COST["enabled"]),
        "chars_per_token": int(_DEFAULT_RETRIEVAL_COST["chars_per_token"]),
        "expand_hint": bool(_DEFAULT_RETRIEVAL_COST["expand_hint"]),
    }
    conv = (schema or {}).get("conventions") or {}
    raw = conv.get("retrieval_cost")
    if isinstance(raw, dict):
        if raw.get("enabled") is not None:
            cfg["enabled"] = bool(raw.get("enabled"))
        if raw.get("expand_hint") is not None:
            cfg["expand_hint"] = bool(raw.get("expand_hint"))
        try:
            cpt = int(raw.get("chars_per_token") or 0)
            if cpt > 0:
                cfg["chars_per_token"] = cpt
        except (TypeError, ValueError):
            pass
    return cfg


def estimate_tokens(char_count: int, chars_per_token: int = 4) -> int:
    """Approximate LLM token count from character count (P0-1).

    Calibrated for the mixed zh/en corpus this project targets: zh ~1.5
    tokens/char in real tokenizers, en ~0.25 — /4 sits close enough for a
    *decision hint* and is never used for billing or hard truncation.
    """
    if char_count <= 0:
        return 0
    return max(1, math.ceil(char_count / chars_per_token))


def _doc_description(path: Path) -> str:
    """Best-effort description from a doc's frontmatter (≤80 chars)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not raw.startswith("---"):
        return ""
    m = re.match(r"\A---\s*\n(.*?)\n---", raw, re.DOTALL)
    if not m:
        return ""
    d = _DESC_RE.search(m.group(1))
    return (d.group(1).strip() if d else "")[:80]


def apply_snippet_budget(
    results: List[Dict[str, Any]],
    output_dir: Path,
    schema: Optional[dict],
) -> int:
    """Degrade snippets beyond the character budget to one-line pointers.

    Mutates *results* in place: entries whose cumulative snippet length exceeds
    ``search_result_chars`` get ``snippet`` replaced by
    ``description | score``（无 description 时仅路径提示） and gain
    ``"degraded": True``。file/title/score 等字段不受影响——降级降的是
    信息量，不是可达性。Returns the number of degraded entries.
    """
    budget = load_budget(schema).get("search_result_chars", 0)
    if budget <= 0 or not results:
        return 0
    od = Path(output_dir)
    used = 0
    degraded = 0
    for r in results:
        snippet = str(r.get("snippet") or "")
        # 纯预算约束：累计超预算即降级（首条亦然）——degraded 行本身是
        # 可用线索（路径|分数|description），全降级的响应仍可导航。
        if used + len(snippet) <= budget:
            used += len(snippet)
            continue
        # over budget — degrade to a one-line pointer
        desc = ""
        fp = r.get("file")
        if fp:
            desc = _doc_description(od / str(fp))
        score = r.get("relevance_score", "")
        bits = [b for b in (desc, f"score {score}") if b]
        r["snippet"] = (" | ".join(bits)) or "(budget-degraded; read the file for content)"
        r["degraded"] = True
        degraded += 1
    return degraded


def cap_module_lines(
    modules: List[str],
    output_dir: Path,
    schema: Optional[dict],
) -> Dict[str, Any]:
    """Cap the AGENTS.md module list; overflow collapses to a pointer line.

    Ordering: usage heat (telemetry hits) desc when available, else input
    order. Returns ``{"lines": [...], "hidden_count": n}`` — the caller
    renders ``lines`` verbatim.
    """
    cap = load_budget(schema).get("agents_md_module_lines", 0)
    if cap <= 0 or len(modules) <= cap:
        return {"lines": list(modules), "hidden_count": 0}
    ordered = list(modules)
    try:
        from codewiki.mcp.tools import telemetry

        heat = {
            str(fp): int(e.get("hits", 0) or 0)
            for fp, e in telemetry.aggregate_usage(output_dir).items()
        }

        # module heat = max hit count among its doc paths
        def _m_heat(m: str) -> int:
            keys = (f"wiki/modules/{m}.md", f"wiki\\modules\\{m}.md")
            return max((heat.get(k, 0) for k in keys), default=0)

        ordered.sort(key=lambda m: -_m_heat(m))
    except Exception as e:  # telemetry unavailable — keep tree order
        logger.debug("module heat ordering skipped: %s", e)
    return {"lines": ordered[:cap], "hidden_count": len(modules) - cap}
