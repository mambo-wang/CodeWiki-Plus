"""Retrieval kernel: the text-level core both BM25 paths share.

Deep module extracted from ``codewiki/mcp/cache.py`` (architecture review
2026-09, candidate #2). Small interface, pure text logic:

    tokenize(text) -> list[str]
    extract_snippet(content, query_tokens) -> str
    build_indexable_text(content, page_type) -> str
    load_ontology(output_dir) / expand_with_ontology(tokens, ontology)
    doc_authority(doc_key, source, content) -> float
    compute_usage_heat(...) / usage_context(...)
    load_usage_ranking_config(schema)

The SQLite path (AnalysisCache) and the legacy JSON path (wiki_search)
both sit on this kernel so ranking semantics cannot drift between
adapters. Constants ``K1``/``B``/``STOPWORDS`` are public API.
"""
from __future__ import annotations

import logging
import math
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Public renames of the former cache.py privates. K1/_B were cache.py
# module constants; the region below defines the rest (_STOPWORDS etc.).
# Aliases keep both spellings working inside this module.
K1 = _K1 = 1.5
B = _B = 0.75

# ------------------------------------------------------------------ Shared BM25 tokeniser

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKUP_RE = re.compile(r"[#*`\[\]|>_~]")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;:!?。？！，；：（）(){}<>\[\]/\\]+")

_STOPWORDS: Set[str] = {
    # English function words
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "need",
    "must",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "our",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "where",
    "when",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "because",
    "but",
    "and",
    "or",
    "if",
    "while",
    "about",
    "with",
    "of",
    "at",
    "by",
    "for",
    "in",
    "on",
    "to",
    "from",
    "as",
    "into",
    # Chinese function words
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "那",
    "些",
    "什么",
    "怎么",
    "如何",
    "可以",
    "能",
    "吗",
    "呢",
    "吧",
    "啊",
    "哦",
    "嗯",
    "这个",
    "那个",
    "已经",
    "还是",
    "因为",
    "所以",
    "但是",
    "而且",
    "或者",
}

_JIEBA_AVAILABLE: Optional[bool] = None


def _check_jieba() -> bool:
    """Cache jieba availability to avoid repeated import attempts."""
    global _JIEBA_AVAILABLE
    if _JIEBA_AVAILABLE is None:
        try:
            import jieba

            jieba.setLogLevel(logging.WARNING)
            _JIEBA_AVAILABLE = True
        except ImportError:
            _JIEBA_AVAILABLE = False
            logger.info("jieba not installed — regex tokeniser fallback")
    return _JIEBA_AVAILABLE


def _tokenize(text: str) -> List[str]:
    """Tokenise markdown / source text.

    Single authoritative tokeniser shared by cache.py, wiki_search.py and
    knowledge_loop.py.  Uses jieba for CJK segmentation when available,
    otherwise falls back to regex splitting.
    """
    text = _HTML_COMMENT_RE.sub("", text)
    text = _FRONTMATTER_RE.sub("", text)
    text = _MARKUP_RE.sub(" ", text)
    if _check_jieba():
        import jieba

        raw = jieba.lcut(text)
    else:
        raw = _TOKEN_SPLIT_RE.split(text.lower())
    return [
        t.strip().lower()
        for t in raw
        if t.strip()
        and len(t.strip()) >= 2
        and not t.strip().isdigit()
        and t.strip().lower() not in _STOPWORDS
    ]


def _extract_snippet(content: str, query_tokens: List[str]) -> str:
    """Extract ~3 lines around the best keyword match in *content*."""
    # Strip leading YAML frontmatter so it is never returned as snippet text
    content = _FRONTMATTER_RE.sub("", content)
    lines = content.splitlines()
    if not lines:
        return ""
    best_idx, best_count = 0, 0
    for i, line in enumerate(lines):
        c = sum(1 for qt in query_tokens if qt in line.lower())
        if c > best_count:
            best_count = c
            best_idx = i
    start = max(0, best_idx - 1)
    end = min(len(lines), best_idx + 3)
    return "\n".join(lines[start:end]).strip()


def _parse_frontmatter_dict(text: str) -> Dict[str, Any]:
    """Parse a document's YAML frontmatter into a dict. Returns {} on failure.

    Thin delegation to the frontmatter module's reader (architecture review
    2026-09, candidate #3) — one parser for the whole codebase instead of a
    yaml copy here plus per-tool hand-rolled variants. The stdlib reader
    absorbs every shape the write side emits (plain scalars, json-encoded
    scalars, block lists, nested metadata blocks, verified mapping lists).
    """
    try:
        from codewiki.src.frontmatter import parse_frontmatter

        fm, _ = parse_frontmatter(text)
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {}


# Ontology term expansion — expansion map cached by file mtime.
_ontology_cache: Dict[str, Tuple[float, Dict[str, List[str]]]] = {}


def _load_ontology(output_dir: Optional[Path]) -> Dict[str, List[str]]:
    """Load ontology.yaml and build synonym expansion map.

    Returns a dict mapping each term (canonical + aliases) to the full list
    of all synonyms in its group. Cached by file mtime.

    Example ontology.yaml:
        terms:
          搜索索引:
            aliases: [BM25缓存, retrieval cache, 倒排索引]

    Result: {"搜索索引": ["搜索索引","BM25缓存","retrieval cache","倒排索引"],
             "bm25缓存": ["搜索索引","BM25缓存","retrieval cache","倒排索引"], ...}
    """
    if output_dir is None:
        return {}
    onto_path = Path(output_dir) / "ontology.yaml"
    if not onto_path.exists():
        return {}
    try:
        mtime = onto_path.stat().st_mtime
        cached = _ontology_cache.get(str(onto_path))
        if cached and cached[0] == mtime:
            return cached[1]
        import yaml

        with open(onto_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "terms" not in data:
            return {}
        # Build expansion map: every member -> all members (lowercased keys)
        expansion: Dict[str, List[str]] = {}
        for canonical, info in data["terms"].items():
            aliases = []
            if isinstance(info, dict):
                raw = info.get("aliases", [])
                if isinstance(raw, list):
                    aliases = [str(a) for a in raw]
                elif isinstance(raw, str):
                    aliases = [raw]
            members = [str(canonical)] + aliases
            for m in members:
                expansion[m.lower()] = members
        _ontology_cache[str(onto_path)] = (mtime, expansion)
        return expansion
    except Exception as e:
        logger.warning("Failed to load ontology.yaml: %s", e)
        return {}


def _expand_with_ontology(tokens: List[str], ontology: Dict[str, List[str]]) -> List[str]:
    """Expand token list using ontology synonym map. Preserves order, no duplicates."""
    if not ontology:
        return tokens
    seen = set(tokens)
    result = list(tokens)
    for tok in tokens:
        synonyms = ontology.get(tok.lower())
        if synonyms:
            for s in synonyms:
                s_lower = s.lower()
                if s_lower not in seen:
                    seen.add(s_lower)
                    result.append(s)
    return result


def _build_indexable_text(content: str, page_type: Optional[str] = None) -> str:
    """Build indexable text from content with frontmatter field boosting.

    Extracts tags (3x boost), description (2x), title (2x), aliases (3x),
    severity (2x), and related_modules (2x) from YAML frontmatter, then
    prepends them to the body text (without frontmatter delimiters). This
    ensures these semantic fields participate in BM25 search with higher weight.

    Args:
        content: Markdown content with optional YAML frontmatter.
        page_type: Optional page type for type-aware boosting.

    Returns the combined text string ready for _tokenize().
    """
    fm = _parse_frontmatter_dict(content)
    if not fm:
        return content

    parts = []

    # Tags: repeat 3x for strong boost
    tags = fm.get("tags", [])
    if isinstance(tags, list):
        tags_text = " ".join(str(t) for t in tags)
    elif isinstance(tags, str):
        tags_text = tags
    else:
        tags_text = ""
    if tags_text:
        parts.append(tags_text)
        parts.append(tags_text)
        parts.append(tags_text)

    # Description: repeat 2x for moderate boost
    desc = fm.get("description", "")
    if isinstance(desc, str) and desc:
        parts.append(desc)
        parts.append(desc)

    # Title: repeat 2x for moderate boost
    title = fm.get("title", "")
    if isinstance(title, str) and title:
        parts.append(title)
        parts.append(title)

    # LLM Wiki: aliases 3x boost (alternate names for search discoverability)
    aliases = fm.get("aliases", [])
    if isinstance(aliases, list):
        aliases_text = " ".join(str(a) for a in aliases)
    elif isinstance(aliases, str):
        aliases_text = aliases
    else:
        aliases_text = ""
    if aliases_text:
        parts.append(aliases_text)
        parts.append(aliases_text)
        parts.append(aliases_text)

    # LLM Wiki: severity boost (for pitfall/known_issue notes) — may be folded
    # under metadata: (OKF §4/§5)
    _meta = fm.get("metadata") or {}
    severity = fm.get("severity", "") or _meta.get("severity", "")
    if isinstance(severity, str) and severity:
        parts.append(severity)
        parts.append(severity)

    # LLM Wiki: related_modules 2x boost (module names for cross-reference discovery)
    related = fm.get("related_modules", []) or _meta.get("related_modules", [])
    if isinstance(related, list):
        related_text = " ".join(str(r) for r in related)
    elif isinstance(related, str):
        related_text = related
    else:
        related_text = ""
    if related_text:
        parts.append(related_text)
        parts.append(related_text)

    # Body text (frontmatter stripped by _tokenize regex, but we need it here
    # without the delimiters so it doesn't get stripped)
    body = _FRONTMATTER_RE.sub("", content)
    parts.append(body)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Authority-aware ranking (P0, borrowed from ai-memory PageAuthority).
#
# A deterministic multiplicative factor applied to the BM25 score AFTER
# scoring (not via token duplication), so reviewed/authoritative knowledge
# outranks ephemeral evidence without distorting term-frequency semantics.
# Computed at index time from frontmatter + path; clamped to keep ordering
# sane. Notes: note_type boost + status gate; wiki docs: L2 scenario / L3
# doctrine boost; raw/sources: penalised (unreviewed third-party material).
# ---------------------------------------------------------------------------

_NOTE_TYPE_AUTHORITY: Dict[str, float] = {
    "decision": 0.15,
    "pitfall": 0.12,
    "lesson": 0.10,
    "architecture": 0.10,
    "workaround": 0.05,
}
_STATUS_AUTHORITY: Dict[str, float] = {
    "draft": -0.25,  # unreviewed knowledge sinks below verified content
    "stable": 0.05,
    "deprecated": -0.35,
}
_SCENARIO_AUTHORITY = 0.15  # L2 scenario blocks (wiki/scenarios/)
_DOCTRINE_AUTHORITY = 0.20  # L3 project doctrine (doctrine.md)
_SOURCE_AUTHORITY = -0.20  # raw/sources/ third-party material
_AUTHORITY_MIN, _AUTHORITY_MAX = 0.7, 1.3


def _doc_authority(doc_key: str, source: str, content: str = "") -> float:
    """Return the authority multiplier for a document (clamped 0.7-1.3).

    Pure rules, no IO beyond the already-loaded *content*:
    - notes: ``type``/``note_type`` boost (decision > pitfall >
      lesson/architecture > workaround) combined with the OKF ``status``
      gate (draft -0.25, stable +0.05, deprecated -0.35);
    - wiki docs: doctrine.md +0.20, scenarios/ pages +0.15;
    - raw/sources: -0.20 regardless of frontmatter.
    """
    offset = 0.0
    dk = doc_key.replace("\\", "/").lower()
    if source == "source" or dk.startswith("raw/sources/"):
        offset += _SOURCE_AUTHORITY
    elif source == "note" or dk.startswith("notes/"):
        fm = _parse_frontmatter_dict(content) if content else {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        note_type = (
            str(
                fm.get("type")
                or fm.get("note_type")
                or meta.get("type")
                or meta.get("note_type")
                or ""
            )
            .strip()
            .lower()
        )
        status = str(fm.get("status") or meta.get("status") or "").strip().lower()
        offset += _NOTE_TYPE_AUTHORITY.get(note_type, 0.0)
        offset += _STATUS_AUTHORITY.get(status, 0.0)
    else:
        if dk.endswith("doctrine.md"):
            offset += _DOCTRINE_AUTHORITY
        elif "/scenarios/" in f"/{dk}":
            offset += _SCENARIO_AUTHORITY
    return max(_AUTHORITY_MIN, min(_AUTHORITY_MAX, 1.0 + offset))


# ---------------------------------------------------------------------------
# Usage-signal heat ranking (U1, docs/知识飞轮增强设计方案-P0三项.md §3).
#
# telemetry jsonl events (written by query_wiki after every search, T2:
# docs/团队知识库支持优化设计方案.md §4.2) feed a
# conservative multiplicative heat factor applied exactly where authority is:
# AFTER the BM25 score, BEFORE the note title floor:
#
#   heat = 1 + min(boost_cap, 0.03 * ln(1 + hit_count))     # log-saturating
#          - cold_penalty    (only when hit_count >= cold_min_hits AND
#                             last_hit older than cold_days), floored at 0.8
#   final = BM25 * authority * heat
#
# Docs with no retrieval record stay neutral at 1.0 (new docs are never
# punished — avoids the rank-low → never-hit → rank-lower Matthew loop).
# These helpers live in cache.py (the low-level module both BM25 paths
# import from) for the same reason _doc_authority does; wiki_search.py
# reuses them for the legacy JSON path so the two paths cannot drift.
# ---------------------------------------------------------------------------

USAGE_RANKING_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "boost_cap": 0.15,
    "cold_penalty": 0.2,
    "cold_days": 180,
    "cold_min_hits": 3,
    # P1 A-line: adoption (actually-used) weighs 2x recall (merely-retrieved).
    # Set 0 to disable adoption influence on ranking.
    "adopted_weight": 0.06,
}
_USAGE_HEAT_FLOOR = 0.8


def load_usage_ranking_config(schema: Optional[dict]) -> Dict[str, Any]:
    """Resolve ``conventions.usage_ranking`` from a loaded schema.yaml.

    Fallback chain: schema ``conventions.usage_ranking`` → hardcoded
    defaults (``USAGE_RANKING_DEFAULTS``).  Bundles without the block get
    the defaults, so search behaviour only changes when the schema opts in
    or overrides parameters.  Malformed values fall back per-key.
    """
    cfg = dict(USAGE_RANKING_DEFAULTS)
    conv = (schema or {}).get("conventions") or {}
    block = conv.get("usage_ranking") or {}
    if not isinstance(block, dict):
        return cfg
    for key in ("boost_cap", "cold_penalty", "adopted_weight"):
        try:
            cfg[key] = float(block.get(key, cfg[key]))
        except (TypeError, ValueError):
            pass
    for key in ("cold_days", "cold_min_hits"):
        try:
            cfg[key] = int(block.get(key, cfg[key]))
        except (TypeError, ValueError):
            pass
    enabled = block.get("enabled")
    if isinstance(enabled, bool):
        cfg["enabled"] = enabled
    return cfg


def compute_usage_heat(
    hit_count: Any,
    last_hit: Any,
    cfg: Optional[Dict[str, Any]] = None,
    today: Optional[date] = None,
    adopted_count: Any = None,
) -> float:
    """heat(doc) per the usage-ranking model. Pure function, no IO.

    - no retrieval record (hit_count falsy/<=0) → 1.0 (neutral);
    - boost: ``1 + min(boost_cap, 0.03·ln(1+hits) + adopted_weight·ln(1+adopted))``
      — adoption (actually-used) weighs 2× recall (merely-retrieved) by
      default (``adopted_weight`` = 0.06 vs 0.03), still capped by
      ``boost_cap`` so popularity never overrides relevance;
    - cold penalty: only for docs that were hot before (hit_count >=
      cold_min_hits) whose last_hit is more than cold_days ago — subtract
      cold_penalty, floored at 0.8.  Unparseable last_hit counts as not
      cold (fail-safe: never punish on bad data).
    """
    cfg = cfg or USAGE_RANKING_DEFAULTS
    try:
        hits = int(hit_count or 0)
    except (TypeError, ValueError):
        hits = 0
    if hits <= 0:
        return 1.0
    try:
        adopted = int(adopted_count or 0)
    except (TypeError, ValueError):
        adopted = 0
    boost = 0.03 * math.log(1 + hits)
    if adopted > 0:
        boost += float(cfg.get("adopted_weight", 0.06)) * math.log(1 + adopted)
    heat = 1.0 + min(float(cfg.get("boost_cap", 0.15)), boost)
    if hits >= int(cfg.get("cold_min_hits", 3)) and last_hit:
        try:
            last = datetime.strptime(str(last_hit).strip()[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            last = None
        if last is not None:
            if today is None:
                today = date.today()
            if (today - last).days > int(cfg.get("cold_days", 180)):
                heat = max(
                    _USAGE_HEAT_FLOOR,
                    heat - float(cfg.get("cold_penalty", 0.2)),
                )
    return heat


# file_path -> (hit_count, last_hit, adopted_count), aggregated from the
# per-user telemetry event streams (T2, docs/团队知识库支持优化设计方案.md
# §4.2) written by query_wiki / capture adoption recording. The mtime
# snapshot cache lives inside telemetry.aggregate_usage — any event file
# changing forces a rescan, so no separate caching is needed here.


def _load_retrieval_usage_map(
    output_dir: Optional[Path],
) -> Dict[str, Tuple[int, Optional[str], int]]:
    """Load ``file_path → (hit_count, last_hit, adopted_count)``.

    All three numbers are team-wide aggregates over every user's
    ``.meta/telemetry/*.jsonl`` (plus the gitignored telemetry-local
    fallback directory): hit/last_hit from ``hit`` events, adopted_count
    from distinct-key ``adopted`` events. No telemetry data or read
    failures degrade silently to an empty mapping (usage signals must
    never break search).
    """
    if output_dir is None:
        return {}
    try:
        from codewiki.mcp.tools import telemetry

        usage = telemetry.aggregate_usage(Path(output_dir))
    except Exception as e:
        logger.debug("Failed to load telemetry usage: %s", e)
        return {}
    out: Dict[str, Tuple[int, Optional[str], int]] = {}
    for fp, entry in usage.items():
        try:
            out[str(fp)] = (
                int(entry.get("hits", 0) or 0),
                entry.get("last_hit"),
                int(entry.get("adopted", 0) or 0),
            )
        except (TypeError, ValueError):
            continue
    return out


# Bundle schema.yaml as needed by usage ranking, cached by file mtime.
_usage_schema_cache: Dict[str, Tuple[Optional[float], dict]] = {}


def _load_usage_schema(output_dir: Optional[Path]) -> dict:
    """Load the bundle schema.yaml dict for usage-ranking config (mtime-cached)."""
    if output_dir is None:
        return {}
    try:
        from codewiki.src.config import SCHEMA_FILENAME

        name = SCHEMA_FILENAME
    except Exception:
        name = "schema.yaml"
    p = Path(output_dir) / name
    key = str(p)
    try:
        mtime: Optional[float] = p.stat().st_mtime if p.exists() else None
    except OSError:
        mtime = None
    cached = _usage_schema_cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    data: dict = {}
    if mtime is not None:
        try:
            import yaml

            with open(p, "r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                data = loaded
        except Exception as e:
            logger.debug("Failed to load schema for usage ranking: %s", e)
    _usage_schema_cache[key] = (mtime, data)
    return data


def _usage_context(
    output_dir: Optional[Path], apply_usage: bool
) -> Tuple[Dict[str, Any], Dict[str, Tuple[int, Optional[str]]], bool]:
    """(config, usage map, heat_enabled) for one search call.

    The usage map is ALWAYS loaded — result entries carry a ``usage`` field
    even when heat weighting is disabled or exempted — but heat only
    multiplies the score when *apply_usage* is True AND the schema enables
    it (``conventions.usage_ranking.enabled``, default true).
    """
    usage_map = _load_retrieval_usage_map(output_dir)
    cfg = load_usage_ranking_config(_load_usage_schema(output_dir))
    return cfg, usage_map, bool(apply_usage and cfg.get("enabled", True))



# ---------------------------------------------------------------------------
# Public interface of the retrieval kernel. The implementation above keeps
# its historical underscore names (moved verbatim from cache.py); these
# aliases are the interface new consumers should import.

STOPWORDS = _STOPWORDS
tokenize = _tokenize
extract_snippet = _extract_snippet
parse_frontmatter_dict = _parse_frontmatter_dict
load_ontology = _load_ontology
expand_with_ontology = _expand_with_ontology
build_indexable_text = _build_indexable_text
doc_authority = _doc_authority
usage_context = _usage_context

__all__ = [
    "B", "K1", "STOPWORDS",
    "USAGE_RANKING_DEFAULTS",
    "build_indexable_text", "compute_usage_heat", "doc_authority",
    "expand_with_ontology", "extract_snippet", "load_ontology",
    "load_usage_ranking_config", "parse_frontmatter_dict",
    "tokenize", "usage_context",
]
