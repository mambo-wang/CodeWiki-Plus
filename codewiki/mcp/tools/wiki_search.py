"""BM25 inverted-index search engine for CodeWiki docs + notes.

Uses ``jieba`` for Chinese word segmentation and a BM25 scoring model
(k1=1.5, b=0.75) for relevance ranking.  The index is persisted as a
single JSON file (``search_index.json``) and supports incremental
single-file updates so that ``write_doc_file`` / ``ingest_note`` /
``edit_doc_file`` can keep it fresh without a full rebuild.

Public API
----------
- ``build_full_index(output_dir)``   — (re)build the entire index
- ``update_file(output_dir, filepath)`` — upsert one document
- ``remove_file(output_dir, filepath)`` — delete one document
- ``search(output_dir, query, ...)`` — BM25 query with optional scope/filter
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SEARCH_INDEX_FILENAME = "search_index.json"
_NOTES_DIR = "notes"

# BM25 parameters (standard defaults)
_K1 = 1.5
_B = 0.75

# Skip files that are system-generated
_SYSTEM_FILES = {"index.md", "log.md", "overview.md"}

# Regex for stripping markdown / YAML frontmatter / HTML comments
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKUP_RE = re.compile(r"[#*`\[\]|>_~]")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;:!?。？！，；：\u201c\u201d\u2018\u2019（）(){}<>\[\]/\\]+")

# Thread safety
_build_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Tokenizer (lazy-loaded jieba with regex fallback)
# ---------------------------------------------------------------------------
_JIEBA_AVAILABLE: Optional[bool] = None


def _check_jieba() -> bool:
    global _JIEBA_AVAILABLE
    if _JIEBA_AVAILABLE is None:
        try:
            import jieba  # noqa: F401
            jieba.setLogLevel(logging.WARNING)
            _JIEBA_AVAILABLE = True
        except ImportError:
            _JIEBA_AVAILABLE = False
            logger.info(
                "jieba not installed — falling back to regex tokeniser. "
                "Install with: pip install jieba"
            )
    return _JIEBA_AVAILABLE


# Chinese + English stopwords (reused from knowledge_loop.py)
_STOPWORDS: Set[str] = {
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must", "it", "its",
    "this", "that", "these", "those", "i", "you", "he", "she", "we", "they",
    "me", "him", "her", "us", "them", "my", "your", "his", "our", "their",
    "what", "which", "who", "whom", "where", "when", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "about", "with",
    "of", "at", "by", "for", "in", "on", "to", "from", "as", "into",
    "also", "then", "when", "where", "while", "which", "with", "without",
    # Chinese
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些", "什么",
    "怎么", "如何", "可以", "能", "吗", "呢", "吧", "啊", "哦", "嗯",
    "这个", "那个", "已经", "还是", "因为", "所以", "但是", "而且", "或者",
    "通过", "使用", "进行", "以及", "其中", "该", "其", "等", "被", "把",
    "对", "从", "与", "而", "并", "但", "来", "去", "做", "为",
}


def _tokenize(text: str) -> List[str]:
    """Tokenize text using jieba (preferred) or regex fallback.

    Returns lowercased tokens with stopwords and short tokens removed.
    """
    # Strip markdown syntax
    text = _HTML_COMMENT_RE.sub("", text)
    text = _FRONTMATTER_RE.sub("", text)
    text = _MARKUP_RE.sub(" ", text)

    if _check_jieba():
        import jieba
        raw_tokens = jieba.lcut(text)
    else:
        # Regex fallback: split on whitespace and punctuation (incl. CJK)
        raw_tokens = _TOKEN_SPLIT_RE.split(text.lower())

    tokens: List[str] = []
    for t in raw_tokens:
        t = t.strip().lower()
        if not t or len(t) < 2:
            continue
        if t in _STOPWORDS:
            continue
        # Skip pure-number tokens
        if t.isdigit():
            continue
        tokens.append(t)
    return tokens


# ---------------------------------------------------------------------------
# Content readers
# ---------------------------------------------------------------------------


def _read_doc_content(filepath: Path) -> str:
    """Read a doc file, stripping crosslink sections."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Strip auto-generated crosslink sections
    crosslink_marker = "<!-- crosslinks"
    if crosslink_marker in content:
        content = content.split(crosslink_marker)[0]
    return content


def _read_note_content(filepath: Path) -> str:
    """Read a note file (including frontmatter for tag extraction)."""
    try:
        return filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Index data structure
# ---------------------------------------------------------------------------


class _IndexData:
    """In-memory representation of the search index.

    Persisted as JSON with the following schema::

        {
          "version": 1,
          "total_docs": <int>,
          "avg_doc_len": <float>,
          "doc_freq": {"<token>": <int>, ...},
          "docs": {
            "<file_key>": {
              "title": "<str>",
              "source": "doc" | "note",
              "doc_len": <int>,
              "term_freq": {"<token>": <int>, ...}
            }
          }
        }

    ``file_key`` is the relative path from output_dir (e.g. ``auth_module.md``
    or ``notes/2025-01-01-decision.md``).
    """

    def __init__(self) -> None:
        self.version: int = 1
        self.total_docs: int = 0
        self.avg_doc_len: float = 0.0
        self.doc_freq: Dict[str, int] = {}   # token -> number of docs containing it
        self.docs: Dict[str, Dict[str, Any]] = {}

    # -- persistence --

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "total_docs": self.total_docs,
            "avg_doc_len": round(self.avg_doc_len, 2),
            "doc_freq": self.doc_freq,
            "docs": self.docs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_IndexData":
        idx = cls()
        idx.version = data.get("version", 1)
        idx.total_docs = data.get("total_docs", 0)
        idx.avg_doc_len = data.get("avg_doc_len", 0.0)
        idx.doc_freq = data.get("doc_freq", {})
        idx.docs = data.get("docs", {})
        return idx

    # -- mutation --

    def _recompute_stats(self) -> None:
        """Recompute total_docs, avg_doc_len, and doc_freq from scratch."""
        self.total_docs = len(self.docs)
        total_len = sum(d.get("doc_len", 0) for d in self.docs.values())
        self.avg_doc_len = total_len / self.total_docs if self.total_docs else 0.0

        # Rebuild doc_freq
        df: Dict[str, int] = {}
        for doc_info in self.docs.values():
            for token in doc_info.get("term_freq", {}):
                df[token] = df.get(token, 0) + 1
        self.doc_freq = df

    def upsert(self, file_key: str, title: str, source: str,
               content: str, *, batch: bool = False) -> None:
        """Add or update a single document in the index.

        When *batch* is True, defer _recompute_stats() so callers can
        insert many documents and call finalize() once at the end,
        reducing O(D²·T) full-index rebuilds to O(D·T).
        """
        tokens = _tokenize(content)
        if not tokens:
            return

        # Build term frequency for this doc
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1

        self.docs[file_key] = {
            "title": title,
            "source": source,
            "doc_len": len(tokens),
            "term_freq": tf,
        }
        if not batch:
            self._recompute_stats()

    def finalize(self) -> None:
        """Recompute BM25 stats after a batch of upsert() calls."""
        self._recompute_stats()

    def remove(self, file_key: str) -> bool:
        """Remove a document. Returns True if it existed."""
        if file_key in self.docs:
            del self.docs[file_key]
            self._recompute_stats()
            return True
        return False


# ---------------------------------------------------------------------------
# Index I/O
# ---------------------------------------------------------------------------


def _index_path(output_dir: Path) -> Path:
    return output_dir / _SEARCH_INDEX_FILENAME


def _load_index(output_dir: Path) -> _IndexData:
    """Load index from disk, returning an empty index on failure."""
    p = _index_path(output_dir)
    if not p.exists():
        return _IndexData()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return _IndexData.from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning("Failed to load search index, rebuilding: %s", e)
        return _IndexData()


def _save_index(output_dir: Path, index: _IndexData) -> None:
    """Atomically write index to disk."""
    p = _index_path(output_dir)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(index.to_dict(), ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(p))
    except Exception as e:
        logger.warning("Failed to save search index: %s", e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Public API: index building
# ---------------------------------------------------------------------------


def build_full_index(output_dir: str | Path) -> Dict[str, Any]:
    """Scan *output_dir* and (re)build the BM25 search index.

    Returns a stats dict: ``{"docs_indexed": int, "notes_indexed": int,
    "total_tokens": int}``.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return {"docs_indexed": 0, "notes_indexed": 0, "total_tokens": 0}

    with _build_lock:
        index = _IndexData()
        docs_count = 0
        notes_count = 0

        # --- Module docs (root-level *.md) ---
        for md_file in sorted(output_dir.iterdir()):
            if not md_file.is_file() or md_file.suffix != ".md":
                continue
            if md_file.name in _SYSTEM_FILES:
                continue
            content = _read_doc_content(md_file)
            if not content.strip():
                continue
            title = _extract_title(content) or md_file.stem.replace("_", " ").title()
            index.upsert(md_file.name, title, "doc", content, batch=True)
            docs_count += 1

        # --- Notes ---
        notes_dir = output_dir / _NOTES_DIR
        if notes_dir.is_dir():
            for note_file in sorted(notes_dir.iterdir()):
                if not note_file.is_file() or note_file.suffix != ".md":
                    continue
                content = _read_note_content(note_file)
                if not content.strip():
                    continue
                title = _extract_frontmatter_value(content, "title") or note_file.stem
                file_key = f"{_NOTES_DIR}/{note_file.name}"
                index.upsert(file_key, title, "note", content, batch=True)
                notes_count += 1

        # Recompute BM25 stats once after all documents are inserted
        index.finalize()
        _save_index(output_dir, index)

    stats = {
        "docs_indexed": docs_count,
        "notes_indexed": notes_count,
        "total_docs": index.total_docs,
        "avg_doc_len": round(index.avg_doc_len, 1),
        "vocabulary_size": len(index.doc_freq),
    }
    logger.info("Search index built: %s", stats)
    return stats


def update_file(output_dir: str | Path, filepath: str | Path) -> None:
    """Incrementally update the index for a single file.

    *filepath* should be an absolute path or relative to *output_dir*.
    If the file does not exist on disk (e.g. was deleted), the entry
    is removed from the index.
    """
    output_dir = Path(output_dir)
    filepath = Path(filepath)

    # Normalise to a file_key relative to output_dir
    try:
        file_key = str(filepath.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        file_key = filepath.name

    with _build_lock:
        index = _load_index(output_dir)

        abs_path = output_dir / file_key
        if not abs_path.exists():
            index.remove(file_key)
            _save_index(output_dir, index)
            return

        if file_key.startswith(f"{_NOTES_DIR}/"):
            content = _read_note_content(abs_path)
            title = _extract_frontmatter_value(content, "title") or abs_path.stem
            source = "note"
        else:
            content = _read_doc_content(abs_path)
            title = _extract_title(content) or abs_path.stem.replace("_", " ").title()
            source = "doc"

        if content.strip():
            index.upsert(file_key, title, source, content)
        else:
            index.remove(file_key)

        _save_index(output_dir, index)


def remove_file(output_dir: str | Path, filepath: str | Path) -> None:
    """Remove a document from the search index."""
    output_dir = Path(output_dir)
    filepath = Path(filepath)
    try:
        file_key = str(filepath.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        file_key = filepath.name

    with _build_lock:
        index = _load_index(output_dir)
        if index.remove(file_key):
            _save_index(output_dir, index)


# ---------------------------------------------------------------------------
# Public API: search
# ---------------------------------------------------------------------------


def search(
    output_dir: str | Path,
    query: str,
    *,
    scope: Optional[str] = None,
    include_notes: bool = True,
    max_results: int = 10,
    score_threshold: float = 0.1,
    expand_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Search the BM25 index and return ranked results.

    Parameters
    ----------
    output_dir : path to the repowiki output directory
    query : natural-language search query
    scope : if set, only return results whose file_key matches this module
    include_notes : whether to include notes in results
    max_results : cap on number of results (default 10, max 20)
    score_threshold : minimum BM25 score to include
    expand_terms : optional synonym/expansion terms added to the query

    Returns
    -------
    List of dicts with keys: file, title, source, snippet, relevance_score
    """
    output_dir = Path(output_dir)
    max_results = min(20, max(1, max_results))

    index = _load_index(output_dir)
    if index.total_docs == 0:
        return []

    # Tokenise query
    query_tokens = _tokenize(query)
    if expand_terms:
        for term in expand_terms:
            for t in _tokenize(term):
                if t not in query_tokens:
                    query_tokens.append(t)

    if not query_tokens:
        return []

    # Score every document
    scored: List[Tuple[float, str]] = []
    n = index.total_docs
    avg_dl = index.avg_doc_len or 1.0

    for file_key, doc_info in index.docs.items():
        # Scope filter
        if scope:
            stem = Path(file_key).stem.lower().replace("_", " ")
            if stem != scope.lower().replace("_", " "):
                continue
        # Notes filter
        if not include_notes and doc_info.get("source") == "note":
            continue

        score = 0.0
        tf_map = doc_info.get("term_freq", {})
        dl = doc_info.get("doc_len", 1)

        for qt in query_tokens:
            if qt not in tf_map:
                continue
            tf = tf_map[qt]
            df = index.doc_freq.get(qt, 1)
            # BM25 IDF (with floor to avoid negatives)
            idf = max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))
            # BM25 TF component
            tf_norm = (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avg_dl))
            score += idf * tf_norm

        if score >= score_threshold:
            scored.append((score, file_key))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:max_results]

    # Build result dicts with snippets
    results: List[Dict[str, Any]] = []
    for score, file_key in scored:
        doc_info = index.docs.get(file_key, {})
        abs_path = output_dir / file_key

        snippet = ""
        try:
            raw = abs_path.read_text(encoding="utf-8", errors="replace")
            snippet = _extract_snippet(raw, query_tokens)
        except OSError:
            pass

        results.append({
            "file": file_key,
            "title": doc_info.get("title", file_key),
            "source": doc_info.get("source", "doc"),
            "snippet": snippet[:300],
            "relevance_score": round(score, 4),
        })

    return results


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------


def _extract_snippet(content: str, query_tokens: List[str]) -> str:
    """Extract a ~3-line snippet around the best keyword match."""
    lines = content.splitlines()
    if not lines:
        return ""

    best_line_idx = 0
    best_count = 0

    content_lower_lines = [l.lower() for l in lines]
    for i, line_lower in enumerate(content_lower_lines):
        count = sum(1 for qt in query_tokens if qt in line_lower)
        if count > best_count:
            best_count = count
            best_line_idx = i

    start = max(0, best_line_idx - 1)
    end = min(len(lines), best_line_idx + 3)
    return "\n".join(lines[start:end]).strip()


# ---------------------------------------------------------------------------
# Title / frontmatter helpers
# ---------------------------------------------------------------------------


def _extract_title(content: str) -> Optional[str]:
    """Extract the first H1 heading from markdown content."""
    for line in content.splitlines()[:30]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _extract_frontmatter_value(content: str, key: str) -> Optional[str]:
    """Extract a single value from YAML frontmatter."""
    if not content.startswith("---"):
        return None
    try:
        end = content.index("---", 3)
        fm = content[3:end]
        for line in fm.splitlines():
            if line.startswith(f"{key}:"):
                val = line[len(key) + 1:].strip().strip('"').strip("'")
                return val
    except (ValueError, IndexError):
        pass
    return None
