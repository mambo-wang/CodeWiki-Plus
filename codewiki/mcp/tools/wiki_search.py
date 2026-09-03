"""BM25 search engine for CodeWiki docs + notes.

When an active session with a SQLite cache is available, search uses the
SQLite token index for efficient token-level pre-filtering.  Falls back to
the legacy JSON file index otherwise.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from codewiki.mcp.cache import (
    _K1,
    _B,
    _build_indexable_text,
    _tokenize,
    _extract_snippet,
    _load_ontology,
    _expand_with_ontology,
    _doc_authority,
    compute_usage_heat,
    _usage_context,
)
from codewiki.mcp.tools.injection_budget import estimate_tokens

logger = logging.getLogger(__name__)

_SEARCH_INDEX_FILENAME = "search_index.json"
_NOTES_DIR = "notes"
_SYSTEM_FILES = {"index.md", "log.md", "overview.md"}
_build_lock = threading.Lock()


def _resolve_db_path(output_dir: Path) -> Optional[Path]:
    """Resolve analysis_cache.db path from project.json or standard layout.

    project.json entries may be relative (T1b: portable across machines —
    cache_db is repo-root-relative, output_dir is repo-relative) or absolute
    (legacy). Relative cache_db resolves against the output_dir's parent
    (i.e. the repo root for the standard <repo>/repowiki layout). A missing
    absolute path falls through to the standard layout, never errors.
    """
    from codewiki.mcp.cache import _CACHE_DIR, _DB_FILENAME
    from codewiki.src.config import meta_resolve, PROJECT_FILENAME

    od = Path(output_dir).resolve()
    # 1. project.json (authoritative)
    try:
        pj = Path(meta_resolve(od, PROJECT_FILENAME))
        if pj.exists():
            info = json.loads(pj.read_text(encoding="utf-8"))
            candidate = info.get("cache_db")
            if candidate:
                cand = Path(candidate)
                if not cand.is_absolute():
                    # relative → resolve against the repo root (= output_dir.parent
                    # for the standard layout; falls back to output_dir itself)
                    cand = od.parent / cand
                if cand.exists():
                    return cand
    except Exception:
        pass
    # 2. Standard layout fallback
    candidate = od.parent / _CACHE_DIR / _DB_FILENAME
    return candidate if candidate.exists() else None


def _open_standalone_cache(output_dir: Path, *, readonly: bool = False):
    """Try to open analysis_cache.db without an active session.

    Uses _resolve_db_path to find the DB, verifies search tables have data.
    Returns an AnalysisCache instance or None.
    """
    from codewiki.mcp.cache import AnalysisCache

    db_path = _resolve_db_path(output_dir)
    if db_path is None:
        return None
    try:
        repo_path = db_path.parent.parent  # .codewiki/analysis_cache.db → repo root
        cache = AnalysisCache(repo_path, db_path=db_path)
        # Verify search tables have data
        r = cache.conn.execute("SELECT value FROM search_stats WHERE key='total_docs'").fetchone()
        if not r or int(r["value"]) == 0:
            cache.close()
            return None
        return cache
    except Exception:
        return None


# ---- Legacy JSON index ----


class _IndexData:
    def __init__(self):
        self.version = 1
        self.total_docs = 0
        self.avg_doc_len = 0.0
        self.doc_freq: Dict[str, int] = {}
        self.docs: Dict[str, Dict] = {}
        self.built_at: float = 0.0  # T1a: build timestamp for mtime-sampling freshness

    def to_dict(self):
        return {
            "version": self.version,
            "total_docs": self.total_docs,
            "avg_doc_len": round(self.avg_doc_len, 2),
            "doc_freq": self.doc_freq,
            "docs": self.docs,
            "built_at": self.built_at or time.time(),
        }

    @classmethod
    def from_dict(cls, d):
        i = cls()
        i.version = d.get("version", 1)
        i.total_docs = d.get("total_docs", 0)
        i.avg_doc_len = d.get("avg_doc_len", 0.0)
        i.doc_freq = d.get("doc_freq", {})
        i.docs = d.get("docs", {})
        i.built_at = float(d.get("built_at") or 0.0)
        return i

    def _recompute(self):
        self.total_docs = len(self.docs)
        tl = sum(d.get("doc_len", 0) for d in self.docs.values())
        self.avg_doc_len = tl / self.total_docs if self.total_docs else 0.0
        df = {}
        for di in self.docs.values():
            for t in di.get("term_freq", {}):
                df[t] = df.get(t, 0) + 1
        self.doc_freq = df

    def upsert(self, fk, title, source, content, *, batch=False):
        tokens = _tokenize(_build_indexable_text(content))
        if not tokens:
            return
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        self.docs[fk] = {
            "title": title,
            "source": source,
            "doc_len": len(tokens),
            "term_freq": tf,
            "authority": _doc_authority(fk, source, content),
        }
        if not batch:
            self._recompute()

    def finalize(self):
        self._recompute()

    def remove(self, fk):
        if fk in self.docs:
            del self.docs[fk]
            self._recompute()
            return True
        return False


def _index_path(od):
    """Search index lives in .meta/ to keep output_dir root clean."""
    from codewiki.src.config import META_DIR

    meta_path = Path(od) / META_DIR / _SEARCH_INDEX_FILENAME
    root_path = Path(od) / _SEARCH_INDEX_FILENAME
    # Prefer .meta/, fallback to root for backward compat (read-only)
    if meta_path.exists() or not root_path.exists():
        return meta_path
    return root_path


def _load_index(od):
    p = _index_path(od)
    if not p.exists():
        return _IndexData()
    try:
        return _IndexData.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        logger.warning("Failed to load search index")
        return _IndexData()


def _save_index(od, idx):
    p = _index_path(od)
    tmp = p.with_suffix(".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(idx.to_dict(), ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(p))
    except Exception as e:
        logger.warning("Failed to save search index: %s", e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _read_doc(fp: Path):
    try:
        ct = fp.read_text(encoding="utf-8", errors="replace")
        if "<!-- crosslinks" in ct:
            ct = ct.split("<!-- crosslinks")[0]
        return ct
    except OSError:
        return ""


def _read_note(fp: Path):
    try:
        return fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_fm(ct, key):
    if not ct.startswith("---"):
        return None
    try:
        end = ct.index("---", 3)
        for line in ct[3:end].splitlines():
            if line.startswith(f"{key}:"):
                return line[len(key) + 1 :].strip().strip('"').strip("'")
    except ValueError:
        pass
    return None


# Strip markdown links from H1 titles: "[JwtUtil](../src/JwtUtil.java)" -> "JwtUtil"
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _extract_title(ct):
    for line in ct.splitlines()[:30]:
        s = line.strip()
        if s.startswith("# "):
            title = _MD_LINK_RE.sub(lambda m: m.group(1), s[2:]).strip()
            return title or None
    return None


# ---- Public API ----


def build_full_index(output_dir, session=None):
    """Build BM25 search index. Uses SQLite cache if session is available.

    The SQLite build is guarded by ``_build_lock`` so concurrent callers (e.g.
    parallel evidence collectors) cannot race on the same db file — one full
    rebuild wins, the rest see the fresh index on their next freshness check.
    """
    od = Path(output_dir)
    if not od.is_dir():
        return {"docs_indexed": 0, "notes_indexed": 0, "total_tokens": 0}

    with _build_lock:
        # Try SQLite cache first (active session)
        if session is not None and getattr(session, "cache", None) is not None:
            try:
                return session.cache.build_search_index(od)
            except Exception as e:
                logger.warning("SQLite search index failed: %s", e)

        # Try standalone SQLite (no active session, DB exists on disk)
        if session is None:
            db_path = _resolve_db_path(od)
            if db_path is not None:
                try:
                    from codewiki.mcp.cache import AnalysisCache

                    cache = AnalysisCache(db_path.parent.parent, db_path=db_path)
                    result = cache.build_search_index(od)
                    cache.close()
                    return result
                except Exception as e:
                    logger.warning("Standalone SQLite index build failed: %s", e)

    # Legacy JSON fallback
    with _build_lock:
        idx = _IndexData()
        dc = nc = sc = 0

        # Scan wiki/ subdirectories recursively
        from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

        wiki_dir = od / WIKI_DIR
        if wiki_dir.is_dir():
            for md in sorted(wiki_dir.rglob("*.md")):
                if not md.is_file():
                    continue
                if md.name in WIKI_SYSTEM_FILES:
                    continue
                ct = _read_doc(md)
                if not ct.strip():
                    continue
                title = _extract_title(ct) or md.stem.replace("_", " ").title()
                try:
                    fk = str(md.relative_to(od)).replace("\\", "/")
                except ValueError:
                    fk = md.name
                idx.upsert(fk, title, "doc", ct, batch=True)
                dc += 1

        # Also scan root-level .md files (for repos without wiki/ dir)
        for md in sorted(od.iterdir()):
            if not md.is_file() or md.suffix != ".md":
                continue
            if md.name in _SYSTEM_FILES:
                continue
            ct = _read_doc(md)
            if not ct.strip():
                continue
            title = _extract_title(ct) or md.stem.replace("_", " ").title()
            idx.upsert(md.name, title, "doc", ct, batch=True)
            dc += 1

        # Scan notes/
        nd = od / _NOTES_DIR
        if nd.is_dir():
            for nf in sorted(nd.iterdir()):
                if not nf.is_file() or nf.suffix != ".md":
                    continue
                ct = _read_note(nf)
                if not ct.strip():
                    continue
                title = _extract_fm(ct, "title") or nf.stem
                idx.upsert(f"{_NOTES_DIR}/{nf.name}", title, "note", ct, batch=True)
                nc += 1

        # Scan raw/sources/
        raw_dir = od / "raw" / "sources"
        if raw_dir.is_dir():
            for sf in sorted(raw_dir.iterdir()):
                if not sf.is_file():
                    continue
                if sf.suffix not in (".md", ".txt", ".rst"):
                    continue
                try:
                    ct = sf.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if not ct.strip():
                    continue
                title = sf.stem.replace("_", " ").replace("-", " ").title()
                idx.upsert(f"raw/sources/{sf.name}", title, "source", ct, batch=True)
                sc += 1

        idx.finalize()
        idx.built_at = time.time()  # T1a: freshness mtime baseline
        _save_index(od, idx)
    return {
        "docs_indexed": dc,
        "notes_indexed": nc,
        "sources_indexed": sc,
        "total_docs": idx.total_docs,
        "avg_doc_len": round(idx.avg_doc_len, 1),
        "vocabulary_size": len(idx.doc_freq),
    }


def update_file(output_dir, filepath, session=None):
    """Incrementally update search index for a single file."""
    od = Path(output_dir)
    fp = Path(filepath)
    if session is not None and getattr(session, "cache", None) is not None:
        try:
            session.cache.update_search_doc(od, fp)
            return
        except Exception as e:
            logger.warning("SQLite search update failed: %s", e)
    # Try standalone SQLite
    if session is None:
        db_path = _resolve_db_path(od)
        if db_path is not None:
            try:
                from codewiki.mcp.cache import AnalysisCache

                cache = AnalysisCache(db_path.parent.parent, db_path=db_path)
                cache.update_search_doc(od, fp)
                cache.close()
                return
            except Exception as e:
                logger.warning("Standalone SQLite update failed: %s", e)
    # Legacy fallback
    try:
        fk = str(fp.resolve().relative_to(od.resolve()))
    except ValueError:
        fk = fp.name
    fk = fk.replace("\\", "/")  # doc_key must match build_full_index's forward-slash shape
    with _build_lock:
        idx = _load_index(od)
        ap = od / fk
        if not ap.exists():
            idx.remove(fk)
            _save_index(od, idx)
            return
        if fk.startswith(f"{_NOTES_DIR}/"):
            ct = _read_note(ap)
            title = _extract_fm(ct, "title") or ap.stem
            src = "note"
        else:
            ct = _read_doc(ap)
            title = _extract_title(ct) or ap.stem.replace("_", " ").title()
            src = "doc"
        if ct.strip():
            idx.upsert(fk, title, src, ct)
        else:
            idx.remove(fk)
        # Tool-side update: align the freshness baseline (mirror of
        # AnalysisCache.update_search_doc) so tier-3 mtime sampling in
        # ensure_fresh doesn't flag this file as stale on the next query.
        # Deletes above (ap not exists) intentionally skip this.
        idx.built_at = time.time()
        _save_index(od, idx)


def remove_file(output_dir, filepath):
    od = Path(output_dir)
    fp = Path(filepath)
    try:
        fk = str(fp.resolve().relative_to(od.resolve()))
    except ValueError:
        fk = fp.name
    fk = fk.replace("\\", "/")  # doc_key must match build_full_index's forward-slash shape
    # SQLite standalone first (mirror of update_file); a delete is not a
    # content update so search_stats.index_built_at is intentionally NOT
    # refreshed — an external pull that added files moments earlier must not
    # be masked.
    try:
        db_path = _resolve_db_path(od)
        if db_path is not None:
            from codewiki.mcp.cache import AnalysisCache

            c = AnalysisCache(db_path.parent.parent, db_path=db_path)
            try:
                c.conn.execute("DELETE FROM search_index WHERE doc_key=?", (fk,))
                c.conn.execute("DELETE FROM search_token_index WHERE doc_key=?", (fk,))
                c.conn.commit()
            finally:
                c.close()
            return
    except Exception as e:
        logger.debug("SQLite search doc removal failed: %s", e)
    # Legacy fallback
    with _build_lock:
        idx = _load_index(od)
        if idx.remove(fk):
            _save_index(od, idx)


def _resolve_retrieval_cost(output_dir) -> Optional[int]:
    """P0-1: resolve chars_per_token for est_tokens, or None when disabled.

    Loaded once per search() call; the divisor is threaded down to the
    SQLite paths and used directly in the JSON fallback path.
    """
    try:
        from codewiki.mcp.tools.page_router import load_schema
        from codewiki.mcp.tools.injection_budget import load_retrieval_cost

        rc = load_retrieval_cost(load_schema(str(output_dir)))
        if rc.get("enabled"):
            return int(rc.get("chars_per_token") or 4)
    except Exception as e:  # config unavailable — feature silently off
        logger.debug("retrieval_cost config skipped: %s", e)
    return None


def search(
    output_dir,
    query,
    *,
    scope=None,
    include_notes=True,
    max_results=10,
    score_threshold=0.1,
    expand_terms=None,
    session=None,
    type_filter=None,
    hop=0,
    decay=0.5,
    apply_authority=True,
    apply_usage=True,
    chars_per_token=None,
):
    """BM25 search. Uses SQLite cache if session available.

    ``apply_authority=False`` / ``apply_usage=False`` exempt a call from the
    respective weighting — used by similarity-oriented consumers (e.g.
    distill dedup recall) where review status or retrieval popularity must
    not influence duplicate detection.  Result entries still carry the
    ``authority`` / ``usage`` fields for transparency.

    ``chars_per_token`` (P0-1): when an int, every entry gains
    ``est_tokens`` = ceil(len(full_text) / chars_per_token) — the estimated
    cost of expanding that result in full. None (default) resolves the
    ``conventions.retrieval_cost`` config once; disabled → None → legacy
    entries without the field.
    """
    od = Path(output_dir)
    max_results = min(20, max(1, max_results))
    if chars_per_token is None:
        chars_per_token = _resolve_retrieval_cost(od)
    elif int(chars_per_token) <= 0:
        chars_per_token = None  # explicit 0 = force off (legacy, no est_tokens)

    # T1a: freshness self-heal (sessionless path only — an active session
    # holds its own cache and close_session rebuilds it). Throttled to one
    # inventory scan per minute; a stale index triggers a transparent rebuild.
    if session is None:
        try:
            from codewiki.mcp.tools.index_freshness import ensure_fresh

            ensure_fresh(od)
        except Exception as e:
            logger.debug("freshness check skipped: %s", e)

    # Try SQLite cache first (active session)
    if session is not None and getattr(session, "cache", None) is not None:
        try:
            return session.cache.search(
                query,
                scope=scope or "",
                include_notes=include_notes,
                max_results=max_results,
                score_threshold=score_threshold,
                output_dir=od,
                type_filter=type_filter,
                hop=hop,
                decay=decay,
                expand_terms=expand_terms,
                apply_authority=apply_authority,
                apply_usage=apply_usage,
                chars_per_token=chars_per_token,
            )
        except Exception as e:
            logger.warning("SQLite search failed: %s", e)

    # Try standalone SQLite (no active session, DB persisted on disk)
    _standalone = None
    if session is None:
        _standalone = _open_standalone_cache(od, readonly=True)
        if _standalone is not None:
            try:
                results = _standalone.search(
                    query,
                    scope=scope or "",
                    include_notes=include_notes,
                    max_results=max_results,
                    score_threshold=score_threshold,
                    output_dir=od,
                    type_filter=type_filter,
                    hop=hop,
                    decay=decay,
                    expand_terms=expand_terms,
                    apply_authority=apply_authority,
                    apply_usage=apply_usage,
                    chars_per_token=chars_per_token,
                )
                _standalone.close()
                return results
            except Exception as e:
                logger.warning("Standalone SQLite search failed: %s", e)
                _standalone.close()

    # Legacy JSON fallback
    qts = _tokenize(query)
    if expand_terms:
        for t in expand_terms:
            for tt in _tokenize(t):
                if tt not in qts:
                    qts.append(tt)
    ontology = _load_ontology(od)
    if ontology:
        qts = _expand_with_ontology(qts, ontology)
    if not qts:
        return []
    idx = _load_index(od)
    if idx.total_docs == 0:
        return []
    # Usage-signal context (U1): shared helpers from cache.py so the JSON and
    # SQLite paths apply identical heat semantics.  Always loaded (results
    # expose a `usage` field); heat only multiplies when enabled + not exempt.
    usage_cfg, usage_map, heat_on = _usage_context(od, apply_usage)
    scored = []
    n = idx.total_docs
    avg_dl = idx.avg_doc_len or 1.0
    for fk, di in idx.docs.items():
        if scope:
            scope_norm = scope.lower().replace(" ", "_").rstrip("/")
            path_lower = fk.lower().replace("\\", "/")
            stem = Path(fk).stem.lower().replace("_", " ")
            if (
                stem != scope_norm.replace("_", " ")
                and not path_lower.startswith(scope_norm + "/")
                and f"/{scope_norm}/" not in f"/{path_lower}"
            ):
                continue
        if not include_notes and di.get("source") == "note":
            continue
        s = 0.0
        tfm = di.get("term_freq", {})
        dl = di.get("doc_len", 1)
        for qt in qts:
            if qt not in tfm:
                continue
            tf = tfm[qt]
            df = idx.doc_freq.get(qt, 1)
            idf = max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))
            s += idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avg_dl))
        # Authority weighting: multiply AFTER BM25, BEFORE the title floor.
        auth = float(di.get("authority") or 1.0) if apply_authority else 1.0
        s *= auth
        # Usage-signal heat (U1): multiply exactly where authority does —
        # AFTER BM25, BEFORE the title floor.
        u_hits, u_last, u_adopted = usage_map.get(fk, (0, None, 0))
        heat = (
            compute_usage_heat(u_hits, u_last, usage_cfg, adopted_count=u_adopted)
            if heat_on
            else 1.0
        )
        s *= heat
        # Developer notes are short; BM25 scores are naturally low and would be
        # filtered out by the generic threshold even when the title matches the
        # query. Treat any title-token match on a note as relevant so distilled
        # notes stay discoverable via query_wiki.
        if di.get("source") == "note":
            title_tokens = set(_tokenize(di.get("title", "")))
            if title_tokens & set(qts) and s > 0:
                s = max(s, score_threshold)
        if s >= score_threshold:
            scored.append((s, fk, auth))
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:max_results]
    out = []
    for s, fk, auth in scored:
        u_hits, u_last, u_adopted = usage_map.get(fk, (0, None, 0))
        # P0-1: est_tokens — the full text is already read for the snippet,
        # so the length costs nothing extra. Only when the feature is on.
        _est_tokens = None
        if chars_per_token and (od / fk).exists():
            try:
                _est_tokens = estimate_tokens(
                    len((od / fk).read_text(encoding="utf-8", errors="replace")),
                    chars_per_token,
                )
            except OSError:
                _est_tokens = None
        entry = {
                "file": fk,
                "title": idx.docs.get(fk, {}).get("title", fk),
                "source": idx.docs.get(fk, {}).get("source", "doc"),
                "snippet": (
                    _extract_snippet((od / fk).read_text(encoding="utf-8", errors="replace"), qts)
                    if (od / fk).exists()
                    else ""
                )[:300],
                "relevance_score": round(s, 4),
                "authority": round(auth, 2),
                "matched_tokens": _matched_for_doc(idx.docs.get(fk, {}).get("term_freq", {}), qts),
                "usage": {"hit_count": u_hits, "last_hit": u_last, "adopted_count": u_adopted},
        }
        if _est_tokens is not None:
            entry["est_tokens"] = _est_tokens
        out.append(entry)
    return out


def _matched_for_doc(tfm, qts):
    """T1 (检索透明化): tokens from the query that actually occur in this doc."""
    return [qt for qt in qts if qt in tfm]


def query_coverage(output_dir, query, expand_terms=None, session=None):
    """T1 (检索透明化): corpus-level coverage of the query tokens.

    Returns {"tokens": [...], "matched": [...], "missing": [...]} where
    ``missing`` lists query tokens that do NOT occur in ANY indexed document
    (df == 0). Expanded terms (expand_terms / ontology) are annotated with a
    trailing "(expanded)" marker in ``tokens``. Consumers should treat a
    result whose key distinguishing terms are all in ``missing`` as
    topically-adjacent rather than an answer.
    """
    od = Path(output_dir)
    base_qts = _tokenize(query)
    expanded = []
    if expand_terms:
        for t in expand_terms:
            for tt in _tokenize(t):
                if tt not in base_qts:
                    expanded.append(tt)
    ontology = _load_ontology(od)
    onto_extra = []
    if ontology:
        for qt in list(base_qts) + expanded:
            for tt in _expand_with_ontology([qt], ontology):
                if tt not in base_qts and tt not in expanded and tt not in onto_extra:
                    onto_extra.append(tt)

    def _df_json(tok):
        idx = _load_index(od)
        return idx.doc_freq.get(tok, 0)

    def _df_sqlite(tok, conn):
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM search_token_index WHERE token=?", (tok,)
        ).fetchone()
        return int(row["c"]) if row else 0

    conn = None
    _standalone = None
    if session is not None and getattr(session, "cache", None) is not None:
        try:
            conn = session.cache.conn
        except Exception:
            conn = None
    if conn is None:
        # _open_standalone_cache returns an AnalysisCache wrapper, not a raw
        # connection — unwrap .conn for the df queries below.
        _standalone = _open_standalone_cache(od, readonly=True)
        if _standalone is not None:
            try:
                conn = _standalone.conn
            except Exception:
                conn = None

    matched, missing = [], []
    try:
        for tok in base_qts:
            df = _df_sqlite(tok, conn) if conn is not None else _df_json(tok)
            (matched if df > 0 else missing).append(tok)
        for tok in expanded + onto_extra:
            df = _df_sqlite(tok, conn) if conn is not None else _df_json(tok)
            (matched if df > 0 else missing).append(tok + " (expanded)")
    finally:
        if _standalone is not None:
            try:
                _standalone.close()
            except Exception:
                pass
    return {"tokens": base_qts, "matched": matched, "missing": missing}
