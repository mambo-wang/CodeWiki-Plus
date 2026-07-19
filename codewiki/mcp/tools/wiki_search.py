"""BM25 search engine for CodeWiki docs + notes.

When an active session with a SQLite cache is available, search uses the
SQLite token index for efficient token-level pre-filtering.  Falls back to
the legacy JSON file index otherwise.
"""

from __future__ import annotations

import json, logging, math, os, re, threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.cache import _STOPWORDS, _K1, _B, _build_indexable_text

logger = logging.getLogger(__name__)

_SEARCH_INDEX_FILENAME = "search_index.json"
_NOTES_DIR = "notes"
_SYSTEM_FILES = {"index.md", "log.md", "overview.md"}
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKUP_RE = re.compile(r"[#*`\[\]|>_~]")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;:!?。？！，；：（）(){}<>\[\]/\\]+")
_build_lock = threading.Lock()

_JIEBA_AVAILABLE: Optional[bool] = None

def _check_jieba() -> bool:
    global _JIEBA_AVAILABLE
    if _JIEBA_AVAILABLE is None:
        try: import jieba; jieba.setLogLevel(logging.WARNING); _JIEBA_AVAILABLE = True
        except ImportError: _JIEBA_AVAILABLE = False; logger.info("jieba not installed — regex fallback")
    return _JIEBA_AVAILABLE

def _tokenize(text: str) -> List[str]:
    text = _HTML_COMMENT_RE.sub("", text); text = _FRONTMATTER_RE.sub("", text)
    text = _MARKUP_RE.sub(" ", text)
    if _check_jieba(): import jieba; raw = jieba.lcut(text)
    else: raw = _TOKEN_SPLIT_RE.split(text.lower())
    return [t.strip().lower() for t in raw if t.strip() and len(t.strip()) >= 2
            and not t.strip().isdigit() and t.strip().lower() not in _STOPWORDS]

# ---- Legacy JSON index ----

class _IndexData:
    def __init__(self):
        self.version = 1; self.total_docs = 0; self.avg_doc_len = 0.0
        self.doc_freq: Dict[str, int] = {}; self.docs: Dict[str, Dict] = {}
    def to_dict(self):
        return {"version": self.version, "total_docs": self.total_docs,
                "avg_doc_len": round(self.avg_doc_len,2), "doc_freq": self.doc_freq, "docs": self.docs}
    @classmethod
    def from_dict(cls, d):
        i = cls(); i.version = d.get("version",1); i.total_docs = d.get("total_docs",0)
        i.avg_doc_len = d.get("avg_doc_len",0.0); i.doc_freq = d.get("doc_freq",{})
        i.docs = d.get("docs",{}); return i
    def _recompute(self):
        self.total_docs = len(self.docs)
        tl = sum(d.get("doc_len",0) for d in self.docs.values())
        self.avg_doc_len = tl / self.total_docs if self.total_docs else 0.0
        df = {}
        for di in self.docs.values():
            for t in di.get("term_freq",{}): df[t] = df.get(t,0) + 1
        self.doc_freq = df
    def upsert(self, fk, title, source, content, *, batch=False):
        tokens = _tokenize(_build_indexable_text(content))
        if not tokens: return
        tf = {}
        for t in tokens: tf[t] = tf.get(t,0) + 1
        self.docs[fk] = {"title": title, "source": source, "doc_len": len(tokens), "term_freq": tf}
        if not batch: self._recompute()
    def finalize(self): self._recompute()
    def remove(self, fk):
        if fk in self.docs: del self.docs[fk]; self._recompute(); return True
        return False

def _index_path(od): return Path(od) / _SEARCH_INDEX_FILENAME
def _load_index(od):
    p = _index_path(od)
    if not p.exists(): return _IndexData()
    try: return _IndexData.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception: logger.warning("Failed to load search index"); return _IndexData()
def _save_index(od, idx):
    p = _index_path(od); tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(idx.to_dict(), ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(p))
    except Exception as e:
        logger.warning("Failed to save search index: %s", e)
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass

def _read_doc(fp: Path):
    try:
        ct = fp.read_text(encoding="utf-8", errors="replace")
        if "<!-- crosslinks" in ct: ct = ct.split("<!-- crosslinks")[0]
        return ct
    except OSError: return ""

def _read_note(fp: Path):
    try: return fp.read_text(encoding="utf-8", errors="replace")
    except OSError: return ""

def _extract_title(ct):
    for l in ct.splitlines()[:30]:
        s = l.strip()
        if s.startswith("# "): return s[2:].strip()
    return None

def _extract_fm(ct, key):
    if not ct.startswith("---"): return None
    try:
        end = ct.index("---", 3)
        for l in ct[3:end].splitlines():
            if l.startswith(f"{key}:"): return l[len(key)+1:].strip().strip('"').strip("'")
    except ValueError: pass
    return None

def _extract_snippet(content, qts):
    lines = content.splitlines()
    if not lines: return ""
    bi, bc = 0, 0
    for i, l in enumerate(lines):
        c = sum(1 for qt in qts if qt in l.lower())
        if c > bc: bc, bi = c, i
    s, e = max(0, bi - 1), min(len(lines), bi + 3)
    return "\n".join(lines[s:e]).strip()

# ---- Public API ----

def build_full_index(output_dir, session=None):
    """Build BM25 search index. Uses SQLite cache if session is available."""
    od = Path(output_dir)
    if not od.is_dir(): return {"docs_indexed": 0, "notes_indexed": 0, "total_tokens": 0}

    # Try SQLite cache first
    if session is not None and getattr(session, "cache", None) is not None:
        try: return session.cache.build_search_index(od)
        except Exception as e: logger.warning("SQLite search index failed: %s", e)

    # Legacy JSON fallback
    with _build_lock:
        idx = _IndexData(); dc = nc = sc = 0

        # Scan wiki/ subdirectories recursively
        from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES
        wiki_dir = od / WIKI_DIR
        if wiki_dir.is_dir():
            for md in sorted(wiki_dir.rglob("*.md")):
                if not md.is_file(): continue
                if md.name in WIKI_SYSTEM_FILES: continue
                ct = _read_doc(md)
                if not ct.strip(): continue
                title = _extract_title(ct) or md.stem.replace("_"," ").title()
                try: fk = str(md.relative_to(od)).replace("\\", "/")
                except ValueError: fk = md.name
                idx.upsert(fk, title, "doc", ct, batch=True); dc += 1

        # Also scan root-level .md files (for repos without wiki/ dir)
        for md in sorted(od.iterdir()):
            if not md.is_file() or md.suffix != ".md": continue
            if md.name in _SYSTEM_FILES: continue
            ct = _read_doc(md)
            if not ct.strip(): continue
            title = _extract_title(ct) or md.stem.replace("_"," ").title()
            idx.upsert(md.name, title, "doc", ct, batch=True); dc += 1

        # Scan notes/
        nd = od / _NOTES_DIR
        if nd.is_dir():
            for nf in sorted(nd.iterdir()):
                if not nf.is_file() or nf.suffix != ".md": continue
                ct = _read_note(nf)
                if not ct.strip(): continue
                title = _extract_fm(ct, "title") or nf.stem
                idx.upsert(f"{_NOTES_DIR}/{nf.name}", title, "note", ct, batch=True); nc += 1

        # Scan raw/sources/
        raw_dir = od / "raw" / "sources"
        if raw_dir.is_dir():
            for sf in sorted(raw_dir.iterdir()):
                if not sf.is_file(): continue
                if sf.suffix not in (".md", ".txt", ".rst"): continue
                try: ct = sf.read_text(encoding="utf-8", errors="replace")
                except OSError: continue
                if not ct.strip(): continue
                title = sf.stem.replace("_", " ").replace("-", " ").title()
                idx.upsert(f"raw/sources/{sf.name}", title, "source", ct, batch=True); sc += 1

        idx.finalize(); _save_index(od, idx)
    return {"docs_indexed": dc, "notes_indexed": nc, "sources_indexed": sc,
            "total_docs": idx.total_docs,
            "avg_doc_len": round(idx.avg_doc_len,1), "vocabulary_size": len(idx.doc_freq)}

def update_file(output_dir, filepath, session=None):
    """Incrementally update search index for a single file."""
    od = Path(output_dir); fp = Path(filepath)
    if session is not None and getattr(session, "cache", None) is not None:
        try: session.cache.update_search_doc(od, fp); return
        except Exception as e: logger.warning("SQLite search update failed: %s", e)
    # Legacy fallback
    try: fk = str(fp.resolve().relative_to(od.resolve()))
    except ValueError: fk = fp.name
    with _build_lock:
        idx = _load_index(od); ap = od / fk
        if not ap.exists(): idx.remove(fk); _save_index(od, idx); return
        if fk.startswith(f"{_NOTES_DIR}/"):
            ct = _read_note(ap); title = _extract_fm(ct,"title") or ap.stem; src = "note"
        else: ct = _read_doc(ap); title = _extract_title(ct) or ap.stem.replace("_"," ").title(); src = "doc"
        if ct.strip(): idx.upsert(fk, title, src, ct)
        else: idx.remove(fk)
        _save_index(od, idx)

def remove_file(output_dir, filepath):
    od = Path(output_dir); fp = Path(filepath)
    try: fk = str(fp.resolve().relative_to(od.resolve()))
    except ValueError: fk = fp.name
    with _build_lock:
        idx = _load_index(od)
        if idx.remove(fk): _save_index(od, idx)

def search(output_dir, query, *, scope=None, include_notes=True, max_results=10,
           score_threshold=0.1, expand_terms=None, session=None, type_filter=None):
    """BM25 search. Uses SQLite cache if session available."""
    od = Path(output_dir); max_results = min(20, max(1, max_results))

    # Try SQLite cache first
    if session is not None and getattr(session, "cache", None) is not None:
        try: return session.cache.search(query, scope=scope or "", include_notes=include_notes,
                                          max_results=max_results, score_threshold=score_threshold,
                                          output_dir=od, type_filter=type_filter)
        except Exception as e: logger.warning("SQLite search failed: %s", e)

    # Legacy JSON fallback
    qts = _tokenize(query)
    if expand_terms:
        for t in expand_terms:
            for tt in _tokenize(t):
                if tt not in qts: qts.append(tt)
    if not qts: return []
    idx = _load_index(od)
    if idx.total_docs == 0: return []
    scored = []; n = idx.total_docs; avg_dl = idx.avg_doc_len or 1.0
    for fk, di in idx.docs.items():
        if scope:
            stem = Path(fk).stem.lower().replace("_"," ")
            if stem != scope.lower().replace("_"," "): continue
        if not include_notes and di.get("source") == "note": continue
        s = 0.0; tfm = di.get("term_freq",{}); dl = di.get("doc_len",1)
        for qt in qts:
            if qt not in tfm: continue
            tf = tfm[qt]; df = idx.doc_freq.get(qt,1)
            idf = max(0.0, math.log((n - df + 0.5)/(df + 0.5) + 1.0))
            s += idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avg_dl))
        if s >= score_threshold: scored.append((s, fk))
    scored.sort(key=lambda x: x[0], reverse=True); scored = scored[:max_results]
    return [{"file": fk, "title": idx.docs.get(fk,{}).get("title",fk),
             "source": idx.docs.get(fk,{}).get("source","doc"),
             "snippet": (_extract_snippet((od/fk).read_text(encoding="utf-8",errors="replace"), qts)
                         if (od/fk).exists() else "")[:300],
             "relevance_score": round(s,4)} for s, fk in scored]
