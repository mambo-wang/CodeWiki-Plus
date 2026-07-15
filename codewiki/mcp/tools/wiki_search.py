"""BM25 search engine for CodeWiki docs + notes (SQLite-backed, optimised).

Uses a SQLite database with a proper inverted index for efficient
token-level lookups.  Persists as ``search_index.db`` in the wiki
output directory.

Key performance optimisations over the initial SQLite port:

1. **SQL-level BM25 scoring** — a single JOIN + GROUP BY query replaces
   the Python-level per-candidate × per-token iteration.  This turns
   O(candidates × query_tokens) individual SQL queries into one
   aggregated result set.

2. **Module-level connection cache** — avoids re-opening the database
   and re-running PRAGMA/executescript on every call.

3. **Deferred stats** — ``_upsert_doc(batch=True)`` skips the expensive
   ``_recompute_stats()`` aggregate queries; callers invoke
   ``_recompute_stats()`` once after all inserts (e.g. ``build_full_index``).

Tokenisation uses ``jieba`` for Chinese word segmentation with a regex
fallback.  BM25 parameters: k1=1.5, b=0.75.

Public API
----------
- ``build_full_index(output_dir)``     — (re)build the entire index
- ``update_file(output_dir, filepath)`` — upsert one document
- ``remove_file(output_dir, filepath)`` — delete one document
- ``search(output_dir, query, ...)``   — BM25 query with scope/filter
"""

from __future__ import annotations

import logging
import math
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.cache import _STOPWORDS, _K1, _B, _build_indexable_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SEARCH_DB_FILENAME = "search_index.db"
_NOTES_DIR = "notes"
_SYSTEM_FILES = {"index.md", "log.md", "overview.md"}

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKUP_RE = re.compile(r"[#*`\[\]|>_~]")
_TOKEN_SPLIT_RE = re.compile(
    r"[\s,;:!?。？！，；：\u201c\u201d\u2018\u2019（）(){}<>\[\]/\\]+"
)

# Thread safety
_build_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Tokeniser (lazy-loaded jieba with regex fallback)
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


def _tokenize(text: str) -> List[str]:
    """Tokenize text using jieba (preferred) or regex fallback."""
    text = _HTML_COMMENT_RE.sub("", text)
    text = _FRONTMATTER_RE.sub("", text)
    text = _MARKUP_RE.sub(" ", text)

    if _check_jieba():
        import jieba

        raw_tokens = jieba.lcut(text)
    else:
        raw_tokens = _TOKEN_SPLIT_RE.split(text.lower())

    tokens: List[str] = []
    for t in raw_tokens:
        t = t.strip().lower()
        if not t or len(t) < 2:
            continue
        if t in _STOPWORDS:
            continue
        if t.isdigit():
            continue
        tokens.append(t)
    return tokens


# ---------------------------------------------------------------------------
# SQLite — connection cache
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS docs (
    doc_key   TEXT PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT '',
    source    TEXT NOT NULL DEFAULT 'doc',
    doc_len   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS postings (
    token   TEXT NOT NULL,
    doc_key TEXT NOT NULL,
    tf      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (token, doc_key)
);
CREATE INDEX IF NOT EXISTS ix_post_doc ON postings(doc_key);
CREATE TABLE IF NOT EXISTS stats (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '0'
);
"""

# Module-level connection cache: output_dir_str -> sqlite3.Connection
_conn_cache: Dict[str, sqlite3.Connection] = {}
_cache_lock = threading.Lock()


def _db_path(output_dir: Path) -> Path:
    return output_dir / _SEARCH_DB_FILENAME


def _get_conn(output_dir: Path) -> sqlite3.Connection:
    """Return a cached SQLite connection, creating it if needed."""
    key = str(Path(output_dir).resolve())
    with _cache_lock:
        conn = _conn_cache.get(key)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except Exception:
                # Connection was closed or corrupted — recreate
                _conn_cache.pop(key, None)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path(output_dir)),
                               check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        _conn_cache[key] = conn
        return conn


def close_all() -> None:
    """Close all cached connections. Call on shutdown."""
    with _cache_lock:
        for conn in _conn_cache.values():
            try:
                conn.close()
            except Exception:
                pass
        _conn_cache.clear()


# ---------------------------------------------------------------------------
# SQLite — stats helpers
# ---------------------------------------------------------------------------


def _get_stat(conn: sqlite3.Connection, key: str, default: float = 0.0) -> float:
    row = conn.execute("SELECT value FROM stats WHERE key=?", (key,)).fetchone()
    return float(row["value"]) if row else default


def _set_stat(conn: sqlite3.Connection, key: str, value: float) -> None:
    conn.execute("INSERT OR REPLACE INTO stats VALUES(?, ?)", (key, str(value)))


def _recompute_stats(conn: sqlite3.Connection) -> None:
    """Recompute total_docs, avg_doc_len, vocabulary_size from live data."""
    total_docs: int = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    if total_docs == 0:
        _set_stat(conn, "total_docs", 0)
        _set_stat(conn, "avg_doc_len", 0)
        _set_stat(conn, "vocabulary_size", 0)
        return
    total_len: int = (
        conn.execute("SELECT COALESCE(SUM(doc_len), 0) FROM docs").fetchone()[0]
    )
    avg_doc_len = total_len / total_docs
    vocab_size: int = (
        conn.execute("SELECT COUNT(DISTINCT token) FROM postings").fetchone()[0]
    )
    _set_stat(conn, "total_docs", total_docs)
    _set_stat(conn, "avg_doc_len", round(avg_doc_len, 2))
    _set_stat(conn, "vocabulary_size", vocab_size)


# ---------------------------------------------------------------------------
# SQLite — document operations
# ---------------------------------------------------------------------------


def _upsert_doc(
    conn: sqlite3.Connection,
    doc_key: str,
    title: str,
    source: str,
    tokens: List[str],
    *,
    batch: bool = False,
) -> None:
    """Insert or replace a document and its posting entries.

    When *batch* is True, skip ``_recompute_stats()`` so callers can
    insert many documents and call it once at the end.
    """
    # Remove old postings (if updating an existing doc)
    conn.execute("DELETE FROM postings WHERE doc_key=?", (doc_key,))

    # Build term-frequency map
    tf_map: Dict[str, int] = {}
    for t in tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    # Upsert doc row
    conn.execute(
        "INSERT OR REPLACE INTO docs VALUES(?, ?, ?, ?)",
        (doc_key, title, source, len(tokens)),
    )

    # Insert new postings
    for token, tf in tf_map.items():
        conn.execute(
            "INSERT OR REPLACE INTO postings VALUES(?, ?, ?)",
            (token, doc_key, tf),
        )

    if not batch:
        _recompute_stats(conn)


def _remove_doc(conn: sqlite3.Connection, doc_key: str) -> bool:
    """Remove a document and its postings. Returns True if it existed."""
    cur = conn.execute("DELETE FROM docs WHERE doc_key=?", (doc_key,))
    if cur.rowcount == 0:
        return False
    conn.execute("DELETE FROM postings WHERE doc_key=?", (doc_key,))
    _recompute_stats(conn)
    return True


# ---------------------------------------------------------------------------
# Content readers
# ---------------------------------------------------------------------------


def _read_doc_content(filepath: Path) -> str:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if "<!-- crosslinks" in content:
        content = content.split("<!-- crosslinks")[0]
    return content


def _read_note_content(filepath: Path) -> str:
    try:
        return filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Title / frontmatter / snippet helpers
# ---------------------------------------------------------------------------


def _extract_title(content: str) -> Optional[str]:
    for line in content.splitlines()[:30]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _extract_frontmatter_value(content: str, key: str) -> Optional[str]:
    if not content.startswith("---"):
        return None
    try:
        end = content.index("---", 3)
        fm = content[3:end]
        for line in fm.splitlines():
            if line.startswith(f"{key}:"):
                val = line[len(key) + 1 :].strip().strip('"').strip("'")
                return val
    except (ValueError, IndexError):
        pass
    return None


def _extract_snippet(content: str, query_tokens: List[str]) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    best_line_idx = 0
    best_count = 0
    for i, line in enumerate(lines):
        count = sum(1 for qt in query_tokens if qt in line.lower())
        if count > best_count:
            best_count = count
            best_line_idx = i
    start = max(0, best_line_idx - 1)
    end = min(len(lines), best_line_idx + 3)
    return "\n".join(lines[start:end]).strip()


# ---------------------------------------------------------------------------
# Public API: index building
# ---------------------------------------------------------------------------


def build_full_index(
    output_dir: str | Path, session: Any = None
) -> Dict[str, Any]:
    """Scan *output_dir* and (re)build the BM25 search index.

    Uses batch mode: ``_recompute_stats()`` is called once after all
    documents are inserted, avoiding O(D) redundant aggregate queries.
    """
    od = Path(output_dir)
    if not od.is_dir():
        return {"docs_indexed": 0, "notes_indexed": 0, "total_docs": 0}

    with _build_lock:
        conn = _get_conn(od)
        try:
            conn.execute("DELETE FROM postings")
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM stats")

            docs_count = 0
            notes_count = 0

            # --- Module docs ---
            for md_file in sorted(od.iterdir()):
                if not md_file.is_file() or md_file.suffix != ".md":
                    continue
                if md_file.name in _SYSTEM_FILES:
                    continue
                content = _read_doc_content(md_file)
                if not content.strip():
                    continue
                title = (
                    _extract_title(content)
                    or md_file.stem.replace("_", " ").title()
                )
                indexable = _build_indexable_text(content)
                tokens = _tokenize(indexable)
                if not tokens:
                    continue
                _upsert_doc(conn, md_file.name, title, "doc", tokens, batch=True)
                docs_count += 1

            # --- Notes ---
            notes_dir = od / _NOTES_DIR
            if notes_dir.is_dir():
                for note_file in sorted(notes_dir.iterdir()):
                    if not note_file.is_file() or note_file.suffix != ".md":
                        continue
                    content = _read_note_content(note_file)
                    if not content.strip():
                        continue
                    title = (
                        _extract_frontmatter_value(content, "title")
                        or note_file.stem
                    )
                    file_key = f"{_NOTES_DIR}/{note_file.name}"
                    indexable = _build_indexable_text(content)
                    tokens = _tokenize(indexable)
                    if not tokens:
                        continue
                    _upsert_doc(conn, file_key, title, "note", tokens, batch=True)
                    notes_count += 1

            # Recompute stats once after all inserts
            _recompute_stats(conn)
            conn.commit()

            stats = {
                "docs_indexed": docs_count,
                "notes_indexed": notes_count,
                "total_docs": docs_count + notes_count,
                "avg_doc_len": _get_stat(conn, "avg_doc_len"),
                "vocabulary_size": int(_get_stat(conn, "vocabulary_size")),
            }
            logger.info("Search index built: %s", stats)
            return stats
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Public API: incremental update
# ---------------------------------------------------------------------------


def update_file(
    output_dir: str | Path,
    filepath: str | Path,
    session: Any = None,
) -> None:
    """Incrementally update the index for a single file."""
    od = Path(output_dir)
    fp = Path(filepath)

    try:
        file_key = str(fp.resolve().relative_to(od.resolve()))
    except ValueError:
        file_key = fp.name

    with _build_lock:
        conn = _get_conn(od)
        try:
            abs_path = od / file_key
            if not abs_path.exists():
                _remove_doc(conn, file_key)
                conn.commit()
                return

            if file_key.startswith(f"{_NOTES_DIR}/"):
                content = _read_note_content(abs_path)
                title = (
                    _extract_frontmatter_value(content, "title") or abs_path.stem
                )
                source = "note"
            else:
                content = _read_doc_content(abs_path)
                title = (
                    _extract_title(content)
                    or abs_path.stem.replace("_", " ").title()
                )
                source = "doc"

            if content.strip():
                indexable = _build_indexable_text(content)
                tokens = _tokenize(indexable)
                if tokens:
                    _upsert_doc(conn, file_key, title, source, tokens)
                else:
                    _remove_doc(conn, file_key)
            else:
                _remove_doc(conn, file_key)

            conn.commit()
        except Exception:
            conn.rollback()
            raise


def remove_file(output_dir: str | Path, filepath: str | Path) -> None:
    """Remove a document from the search index."""
    od = Path(output_dir)
    fp = Path(filepath)
    try:
        file_key = str(fp.resolve().relative_to(od.resolve()))
    except ValueError:
        file_key = fp.name

    with _build_lock:
        conn = _get_conn(od)
        try:
            if _remove_doc(conn, file_key):
                conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Public API: search (SQL-level BM25 scoring)
# ---------------------------------------------------------------------------

# Single-query BM25 scoring using SQLite's built-in LN() math function.
# This replaces the Python-level per-candidate iteration with one
# JOIN + GROUP BY query.
_SEARCH_SQL = """\
SELECT
    d.doc_key, d.title, d.source,
    SUM(
        COALESCE(p.tf, 0) * ? /
        (COALESCE(p.tf, 0) + ? * (1 - ? + ? * d.doc_len / ?))
    ) AS score
FROM docs d
INNER JOIN postings p ON p.doc_key = d.doc_key
WHERE p.token IN ({placeholders})
{scope_clause}
{notes_clause}
GROUP BY d.doc_key
HAVING score > ?
ORDER BY score DESC
LIMIT ?
"""


def search(
    output_dir: str | Path,
    query: str,
    *,
    scope: Optional[str] = None,
    include_notes: bool = True,
    max_results: int = 10,
    score_threshold: float = 0.1,
    expand_terms: Optional[List[str]] = None,
    session: Any = None,
) -> List[Dict[str, Any]]:
    """Search the BM25 index and return ranked results.

    Uses a single SQL query with JOIN + GROUP BY for BM25 scoring,
    avoiding per-document Python iteration.
    """
    od = Path(output_dir)
    max_results = min(20, max(1, max_results))

    db = _db_path(od)
    if not db.exists():
        return []

    conn = _get_conn(od)

    # Global stats
    n = int(_get_stat(conn, "total_docs"))
    if n == 0:
        return []
    avg_dl = _get_stat(conn, "avg_doc_len") or 1.0

    # Tokenise query
    query_tokens = _tokenize(query)
    if expand_terms:
        seen: Set[str] = set(query_tokens)
        for term in expand_terms:
            for t in _tokenize(term):
                if t not in seen:
                    query_tokens.append(t)
                    seen.add(t)
    if not query_tokens:
        return []

    # Deduplicate query tokens (important for correct scoring)
    query_tokens = list(dict.fromkeys(query_tokens))

    # Pre-compute IDF for each query token
    idf_values: Dict[str, float] = {}
    for qt in query_tokens:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM postings WHERE token=?", (qt,)
        ).fetchone()
        df = row["c"] if row else 1
        idf_values[qt] = max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))

    # Build the single scoring query.
    # We use a VALUES-based CTE to pass per-token IDF values into SQL,
    # so the scoring is exact (matches the Python reference implementation).
    placeholders = ",".join("?" * len(query_tokens))

    # Build token_idf CTE: (token, idf) pairs
    token_idf_parts = " UNION ALL ".join(
        f"SELECT ? AS token, ? AS idf" for _ in query_tokens
    )
    token_idf_params: list = []
    for qt in query_tokens:
        token_idf_params.extend([qt, idf_values[qt]])

    scope_clause = ""
    scope_params: list = []
    if scope:
        scope_norm = scope.lower().replace("_", " ")
        scope_clause = (
            "AND LOWER(REPLACE(d.doc_key, '_', ' ')) LIKE ?"
        )
        # Match by stem: extract filename without extension
        scope_clause = "AND LOWER(REPLACE(" \
            "CASE WHEN INSTR(d.doc_key, '/') > 0 " \
            "THEN SUBSTR(d.doc_key, INSTR(d.doc_key, '/') + 1) " \
            "ELSE d.doc_key END, '_', ' ')) LIKE ?"
        scope_stem = Path(scope).stem if "/" in scope else scope
        scope_params = [scope_stem.lower().replace("_", " ")]

    notes_clause = ""
    if not include_notes:
        notes_clause = "AND d.source != 'note'"

    scoring_sql = f"""\
    WITH token_idf(token, idf) AS (
        {token_idf_parts}
    )
    SELECT
        d.doc_key, d.title, d.source,
        SUM(
            ti.idf * (p.tf * {_K1 + 1}) /
            (p.tf + {_K1} * (1 - {_B} + {_B} * d.doc_len / ?))
        ) AS score
    FROM docs d
    INNER JOIN postings p ON p.doc_key = d.doc_key
    INNER JOIN token_idf ti ON ti.token = p.token
    WHERE 1=1
    {scope_clause}
    {notes_clause}
    GROUP BY d.doc_key
    HAVING score > ?
    ORDER BY score DESC
    LIMIT ?
    """

    params = token_idf_params + scope_params + [avg_dl, score_threshold, max_results]

    try:
        rows = conn.execute(scoring_sql, params).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("SQL scoring failed, falling back to Python: %s", e)
        return _python_fallback_search(
            conn, od, query_tokens, idf_values, n, avg_dl,
            scope, include_notes, max_results, score_threshold,
        )

    # Build results with snippets
    results: List[Dict[str, Any]] = []
    for row in rows:
        snippet = ""
        abs_path = od / row["doc_key"]
        if abs_path.exists():
            try:
                raw = abs_path.read_text(encoding="utf-8", errors="replace")
                snippet = _extract_snippet(raw, query_tokens)[:300]
            except OSError:
                pass
        results.append(
            {
                "file": row["doc_key"],
                "title": row["title"],
                "source": row["source"],
                "snippet": snippet,
                "relevance_score": round(row["score"], 4),
            }
        )

    return results


def _python_fallback_search(
    conn: sqlite3.Connection,
    od: Path,
    query_tokens: List[str],
    idf_values: Dict[str, float],
    n: int,
    avg_dl: float,
    scope: Optional[str],
    include_notes: bool,
    max_results: int,
    score_threshold: float,
) -> List[Dict[str, Any]]:
    """Python-level scoring fallback if the SQL CTE query fails."""
    placeholders = ",".join("?" * len(query_tokens))
    candidate_keys = {
        row["doc_key"]
        for row in conn.execute(
            f"SELECT DISTINCT doc_key FROM postings WHERE token IN ({placeholders})",
            query_tokens,
        )
    }
    if not candidate_keys:
        return []

    scored: List[Tuple[float, str]] = []
    for dk in candidate_keys:
        doc_row = conn.execute(
            "SELECT title, source, doc_len FROM docs WHERE doc_key=?", (dk,)
        ).fetchone()
        if not doc_row:
            continue
        if scope:
            stem = Path(dk).stem.lower().replace("_", " ")
            if stem != scope.lower().replace("_", " "):
                continue
        if not include_notes and doc_row["source"] == "note":
            continue
        dl = doc_row["doc_len"] or 1
        score = 0.0
        for qt in query_tokens:
            tf_row = conn.execute(
                "SELECT tf FROM postings WHERE token=? AND doc_key=?", (qt, dk)
            ).fetchone()
            if not tf_row:
                continue
            tf = tf_row["tf"]
            idf = idf_values.get(qt, 0.0)
            tf_norm = (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avg_dl))
            score += idf * tf_norm
        if score >= score_threshold:
            scored.append((score, dk))

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:max_results]

    results: List[Dict[str, Any]] = []
    for score, dk in scored:
        doc_row = conn.execute(
            "SELECT title, source FROM docs WHERE doc_key=?", (dk,)
        ).fetchone()
        snippet = ""
        abs_path = od / dk
        if abs_path.exists():
            try:
                raw = abs_path.read_text(encoding="utf-8", errors="replace")
                snippet = _extract_snippet(raw, query_tokens)[:300]
            except OSError:
                pass
        results.append(
            {
                "file": dk,
                "title": doc_row["title"] if doc_row else dk,
                "source": doc_row["source"] if doc_row else "doc",
                "snippet": snippet,
                "relevance_score": round(score, 4),
            }
        )
    return results
