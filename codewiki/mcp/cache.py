"""SQLite analysis cache: components, fingerprints, deps, search."""
from __future__ import annotations

import hashlib, json, logging, math, os, re, sqlite3, time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.src.be.dependency_analyzer.models.core import Node

logger = logging.getLogger(__name__)
_DB_FILENAME = "analysis_cache.db"
_CACHE_DIR = ".codewiki"
_DEFAULT_LRU_SIZE = 500
_K1, _B = 1.5, 0.75

# SQLite bound-variable limit is 999 on older builds; stay well below it.
_SQL_CHUNK_SIZE = 500


def _sql_chunks(items: List[Any], size: int = _SQL_CHUNK_SIZE) -> List[List[Any]]:
    """Split *items* into chunks small enough for SQL IN(...) placeholders."""
    return [items[i:i + size] for i in range(0, len(items), size)]

# ------------------------------------------------------------------ Shared BM25 tokeniser

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKUP_RE = re.compile(r"[#*`\[\]|>_~]")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;:!?。？！，；：（）(){}<>\[\]/\\]+")

_STOPWORDS: Set[str] = {
    # English function words
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
    # Chinese function words
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些", "什么",
    "怎么", "如何", "可以", "能", "吗", "呢", "吧", "啊", "哦", "嗯",
    "这个", "那个", "已经", "还是", "因为", "所以", "但是", "而且", "或者",
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
        if t.strip() and len(t.strip()) >= 2
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
    """Parse YAML frontmatter into a dict. Returns {} if no frontmatter or parse fails."""
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
        fm_text = text[3:end]
    except ValueError:
        return {}
    try:
        import yaml
        result = yaml.safe_load(fm_text)
        return result if isinstance(result, dict) else {}
    except Exception:
        # Fallback: simple key: value parsing
        result = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
                if key:
                    result[key] = val
        return result


# ------------------------------------------------------------------ Ontology term expansion

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

    # LLM Wiki: severity boost (for pitfall/known_issue notes)
    severity = fm.get("severity", "")
    if isinstance(severity, str) and severity:
        parts.append(severity)
        parts.append(severity)

    # LLM Wiki: related_modules 2x boost (module names for cross-reference discovery)
    related = fm.get("related_modules", [])
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


# ------------------------------------------------------------------ ComponentMeta / LazyStore

@dataclass
class ComponentMeta:
    id: str; name: str; component_type: str; file_path: str; relative_path: str
    start_line: int = 0; end_line: int = 0; language: str = ""
    depends_on: Set[str] = field(default_factory=set)
    node_type: Optional[str] = None; base_classes: Optional[List[str]] = None
    class_name: Optional[str] = None; display_name: Optional[str] = None
    qualified_name: Optional[str] = None; has_docstring: bool = False
    parameters: Optional[List[str]] = None

    def to_node(self, source_code: str = "", docstring: str = "") -> Node:
        return Node(
            id=self.id, name=self.name, component_type=self.component_type,
            file_path=self.file_path, relative_path=self.relative_path,
            start_line=self.start_line, end_line=self.end_line,
            language=self.language, depends_on=self.depends_on,
            node_type=self.node_type, base_classes=self.base_classes,
            class_name=self.class_name, display_name=self.display_name,
            qualified_name=self.qualified_name, has_docstring=self.has_docstring,
            parameters=self.parameters, source_code=source_code, docstring=docstring)


class LazyComponentStore:
    def __init__(self, cache, metas: Dict[str, ComponentMeta], lru_size=_DEFAULT_LRU_SIZE):
        self._cache = cache; self._metas = metas
        self._lru: OrderedDict[str, Node] = OrderedDict(); self._lru_size = lru_size

    def __getitem__(self, k: str) -> Node:
        if k in self._lru: n = self._lru.pop(k); self._lru[k] = n; return n
        n = self._cache.get_component(k)
        if n is None: raise KeyError(k)
        self._lru[k] = n
        if len(self._lru) > self._lru_size: self._lru.popitem(last=False)
        return n
    def __contains__(self, k): return k in self._metas
    def __len__(self): return len(self._metas)
    def __iter__(self): return iter(self._metas)
    def get(self, k, d=None):
        try: return self[k]
        except KeyError: return d
    def items(self): return self._metas.items()
    def keys(self): return self._metas.keys()
    def values(self): return self._metas.values()
    def meta(self, k) -> Optional[ComponentMeta]: return self._metas.get(k)
    def invalidate(self, k): self._lru.pop(k, None)

# ------------------------------------------------------------------ AnalysisCache

class AnalysisCache:
    def __init__(self, repo_path: Path, db_path: Optional[Path] = None):
        self.repo_path = Path(repo_path).resolve()
        self.db_path = (Path(db_path) if db_path else self.repo_path / _CACHE_DIR / _DB_FILENAME)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        return self._conn

    def close(self):
        if self._conn:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._conn.close()
            self._conn = None

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS repo_meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS components (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, component_type TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL DEFAULT '', relative_path TEXT NOT NULL DEFAULT '',
                start_line INTEGER DEFAULT 0, end_line INTEGER DEFAULT 0,
                language TEXT DEFAULT '', node_type TEXT, base_classes TEXT,
                class_name TEXT, display_name TEXT, qualified_name TEXT,
                has_docstring INTEGER DEFAULT 0, docstring TEXT DEFAULT '',
                parameters TEXT, depends_on TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                content_hash TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS ix_comp_type ON components(component_type);
            CREATE INDEX IF NOT EXISTS ix_comp_file ON components(relative_path);
            CREATE TABLE IF NOT EXISTS file_fingerprints (
                file_path TEXT PRIMARY KEY, mtime REAL DEFAULT 0.0,
                size INTEGER DEFAULT 0, content_hash TEXT DEFAULT '', commit_id TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS dependencies (
                source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                PRIMARY KEY(source_id, target_id));
            CREATE INDEX IF NOT EXISTS ix_deps_target ON dependencies(target_id);
            CREATE TABLE IF NOT EXISTS search_index (
                doc_key TEXT PRIMARY KEY, title TEXT DEFAULT '',
                source TEXT DEFAULT 'doc', doc_len INTEGER DEFAULT 0, term_freq TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS search_token_index (
                token TEXT NOT NULL, doc_key TEXT NOT NULL, tf INTEGER DEFAULT 1,
                PRIMARY KEY(token, doc_key));
            CREATE TABLE IF NOT EXISTS search_stats (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS symbols (
                name TEXT NOT NULL, file_path TEXT NOT NULL,
                PRIMARY KEY(name, file_path));
            CREATE INDEX IF NOT EXISTS ix_symbols_name ON symbols(name);
            CREATE TABLE IF NOT EXISTS wiki_links (
                source_doc TEXT NOT NULL, target_doc TEXT NOT NULL,
                link_type TEXT DEFAULT 'wikilink',
                PRIMARY KEY(source_doc, target_doc));
            CREATE INDEX IF NOT EXISTS ix_wiki_links_target ON wiki_links(target_doc);
            CREATE TABLE IF NOT EXISTS routes (
                route_key TEXT NOT NULL,
                protocol TEXT NOT NULL DEFAULT 'http',
                method TEXT,
                path TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                component_id TEXT NOT NULL,
                repo_name TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL DEFAULT '',
                line_number INTEGER DEFAULT 0,
                framework TEXT,
                extra_json TEXT DEFAULT '{}',
                PRIMARY KEY(route_key, component_id, role));
            CREATE INDEX IF NOT EXISTS ix_routes_key ON routes(route_key);
            CREATE INDEX IF NOT EXISTS ix_routes_role ON routes(role);
            CREATE INDEX IF NOT EXISTS ix_routes_protocol ON routes(protocol);
        """)
        # Migration: add content_hash column for existing databases (Roadmap 2.4)
        try:
            self.conn.execute("ALTER TABLE components ADD COLUMN content_hash TEXT DEFAULT ''")
            self.conn.commit()
        except Exception:
            pass  # Column already exists

    # -- meta --

    def _mget(self, k: str, d: str = "") -> str:
        r = self.conn.execute("SELECT value FROM repo_meta WHERE key=?", (k,)).fetchone()
        return r["value"] if r else d
    def _mset(self, k: str, v: str):
        self.conn.execute("INSERT OR REPLACE INTO repo_meta VALUES(?,?)", (k, v)); self.conn.commit()

    def get_last_commit_id(self) -> Optional[str]:
        cid = self._mget("last_commit_id"); return cid if cid else None
    def set_last_commit_id(self, cid: str): self._mset("last_commit_id", cid)
    def get_output_dir(self) -> Optional[str]:
        """Return the output_dir recorded by the last analyze_repo, if any."""
        od = self._mget("output_dir"); return od if od else None
    def set_output_dir(self, od: str): self._mset("output_dir", od)
    def get_component_count(self) -> int:
        r = self.conn.execute("SELECT COUNT(*) as c FROM components").fetchone(); return r["c"] if r else 0
    def is_fresh(self) -> bool: return self.get_component_count() > 0

    # -- symbol map --

    def save_symbol_map(self, symbol_map: Dict[str, List[str]]):
        """Persist symbol_map (name → [file_paths]) to the symbols table."""
        conn = self.conn
        conn.execute("DELETE FROM symbols")
        rows = [(name, fp) for name, paths in symbol_map.items() for fp in paths]
        conn.executemany("INSERT OR IGNORE INTO symbols(name, file_path) VALUES(?,?)", rows)
        conn.commit()

    def load_symbol_map(self) -> Dict[str, List[str]]:
        """Load symbol_map from SQLite. Returns {} if table is empty."""
        rows = self.conn.execute("SELECT name, file_path FROM symbols").fetchall()
        if not rows:
            return {}
        result: Dict[str, List[str]] = {}
        for r in rows:
            result.setdefault(r["name"], []).append(r["file_path"])
        return result

    # -- routes (cross-service analysis) --

    def batch_insert_routes(self, routes: List[Dict], incremental: bool = False):
        """Persist route nodes to the routes table.

        Args:
            routes: List of route dicts (from RouteNode.model_dump())
            incremental: If True, upsert; if False, replace all.
        """
        if not routes:
            return
        c = self.conn
        if not incremental:
            c.execute("DELETE FROM routes")
        rows = [
            (
                r.get("route_key", ""),
                r.get("protocol", "http"),
                r.get("method"),
                r.get("path", ""),
                r.get("role", "server"),
                r.get("component_id", ""),
                r.get("repo_name", ""),
                r.get("file_path", ""),
                r.get("line_number", 0),
                r.get("framework"),
                json.dumps(r.get("extra", {})),
            )
            for r in routes
        ]
        c.executemany(
            "INSERT OR REPLACE INTO routes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        c.commit()
        logger.info("Cached %d routes (%s)", len(routes), "incremental" if incremental else "full")

    def get_all_routes(self) -> List[Dict]:
        """Load all route nodes from SQLite."""
        rows = self.conn.execute(
            "SELECT route_key, protocol, method, path, role, component_id, "
            "repo_name, file_path, line_number, framework, extra_json FROM routes"
        ).fetchall()
        result: List[Dict] = []
        for r in rows:
            extra = {}
            try:
                extra = json.loads(r["extra_json"]) if r["extra_json"] else {}
            except Exception:
                pass
            result.append({
                "route_key": r["route_key"],
                "protocol": r["protocol"],
                "method": r["method"],
                "path": r["path"],
                "role": r["role"],
                "component_id": r["component_id"],
                "repo_name": r["repo_name"],
                "file_path": r["file_path"],
                "line_number": r["line_number"],
                "framework": r["framework"],
                "extra": extra,
            })
        return result

    def get_routes_by_role(self, role: str) -> List[Dict]:
        """Load routes filtered by role ('server' or 'client')."""
        rows = self.conn.execute(
            "SELECT route_key, protocol, method, path, role, component_id, "
            "repo_name, file_path, line_number, framework, extra_json "
            "FROM routes WHERE role=?", (role,),
        ).fetchall()
        result: List[Dict] = []
        for r in rows:
            extra = {}
            try:
                extra = json.loads(r["extra_json"]) if r["extra_json"] else {}
            except Exception:
                pass
            result.append({
                "route_key": r["route_key"],
                "protocol": r["protocol"],
                "method": r["method"],
                "path": r["path"],
                "role": r["role"],
                "component_id": r["component_id"],
                "repo_name": r["repo_name"],
                "file_path": r["file_path"],
                "line_number": r["line_number"],
                "framework": r["framework"],
                "extra": extra,
            })
        return result

    def remove_routes_by_file(self, fp: str) -> int:
        """Remove routes for a specific file (for incremental updates)."""
        fp_norm = fp.replace("\\", "/")
        ids = [
            r["rowid"]
            for r in self.conn.execute(
                "SELECT rowid FROM routes WHERE file_path=? OR replace(file_path, '\\', '/')=?",
                (fp, fp_norm),
            ).fetchall()
        ]
        if ids:
            for chunk in _sql_chunks(ids):
                ph = ",".join("?" * len(chunk))
                self.conn.execute(f"DELETE FROM routes WHERE rowid IN ({ph})", chunk)
            self.conn.commit()
        return len(ids)

    # -- components --

    def get_component(self, cid: str) -> Optional[Node]:
        r = self.conn.execute("SELECT * FROM components WHERE id=?", (cid,)).fetchone()
        if not r: return None
        extra = _parse_row(r)
        return Node(id=r["id"], name=r["name"], component_type=r["component_type"],
                    file_path=r["file_path"], relative_path=r["relative_path"],
                    start_line=r["start_line"], end_line=r["end_line"],
                    language=r["language"], depends_on=extra[0], node_type=r["node_type"],
                    base_classes=extra[1], class_name=r["class_name"],
                    display_name=r["display_name"], qualified_name=r["qualified_name"],
                    has_docstring=bool(r["has_docstring"]), docstring=r["docstring"] or "",
                    parameters=extra[2], source_code="")

    def batch_insert_components(self, components: Dict[str, Node],
                                leaf_nodes: Optional[List[str]] = None,
                                incremental: bool = False):
        if not components:
            return
        c = self.conn

        # In incremental mode, components restored from cache carry
        # source_code="" — recomputing their hash from the structural
        # signature would overwrite the original source-based SHA256 and
        # make get_stale_components() misreport them as modified.
        # Preserve the stored hash for such components.
        stored_hashes: Dict[str, str] = {}
        if incremental:
            ids = list(components.keys())
            for chunk in _sql_chunks(ids):
                ph = ",".join("?" * len(chunk))
                for r in c.execute(
                    f"SELECT id, content_hash FROM components WHERE id IN ({ph})", chunk
                ).fetchall():
                    if r["content_hash"]:
                        stored_hashes[r["id"]] = r["content_hash"]

        def _comp_hash(n: Node) -> str:
            """Compute content hash from source code or structural metadata."""
            src = getattr(n, "source_code", None) or ""
            if src:
                return hashlib.sha256(src.encode("utf-8", errors="replace")).hexdigest()[:16]
            # Prefer the previously stored (source-based) hash when available
            old = stored_hashes.get(n.id)
            if old:
                return old
            # Fallback: hash structural signature
            sig = f"{n.name}|{n.start_line}|{n.end_line}|{json.dumps(n.parameters or [])}|{json.dumps(sorted(n.depends_on))}"
            return hashlib.sha256(sig.encode()).hexdigest()[:16]

        rows = [
            (
                n.id, n.name, n.component_type, n.file_path, n.relative_path,
                n.start_line, n.end_line,
                (n.language or "").strip() or "unknown",
                n.node_type,
                json.dumps(n.base_classes) if n.base_classes else None,
                n.class_name, n.display_name, n.qualified_name,
                1 if n.has_docstring else 0, n.docstring or "",
                json.dumps(n.parameters) if n.parameters else None,
                json.dumps(sorted(n.depends_on)) if n.depends_on else "[]",
                "{}",
                _comp_hash(n),
            )
            for n in components.values()
        ]
        if incremental:
            # Incremental mode: upsert only the provided components
            c.executemany(
                "INSERT OR REPLACE INTO components VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            # Upsert dependencies for these components only
            comp_ids = list(components.keys())
            # Remove old deps for these components (chunked to stay below
            # SQLite's bound-variable limit on large repos)
            for chunk in _sql_chunks(comp_ids):
                ph = ",".join("?" * len(chunk))
                c.execute(f"DELETE FROM dependencies WHERE source_id IN ({ph})", chunk)
            deps = [(n.id, d) for n in components.values() for d in n.depends_on]
            if deps:
                c.executemany("INSERT OR IGNORE INTO dependencies VALUES(?,?)", deps)
        else:
            c.execute("DELETE FROM components")
            c.executemany(
                "INSERT INTO components VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            c.execute("DELETE FROM dependencies")
            deps = [(n.id, d) for n in components.values() for d in n.depends_on]
            if deps:
                c.executemany("INSERT OR IGNORE INTO dependencies VALUES(?,?)", deps)
        c.execute(
            "DELETE FROM repo_meta WHERE key IN('component_count','analyzed_at','leaf_nodes')"
        )
        c.execute(
            "INSERT INTO repo_meta VALUES('component_count',?)",
            (str(self.get_component_count()),),
        )
        c.execute(
            "INSERT INTO repo_meta VALUES('analyzed_at',?)",
            (str(time.time()),),
        )
        if leaf_nodes is not None:
            c.execute(
                "INSERT INTO repo_meta VALUES('leaf_nodes',?)",
                (json.dumps(leaf_nodes),),
            )
        self.conn.commit()
        logger.info("Cached %d components (%s), %d dep edges",
                     len(components), "incremental" if incremental else "full", len(deps))

    def get_stale_components(self, new_components: Dict[str, "Node"]) -> Dict[str, List[str]]:
        """Compare incoming components against stored content hashes.

        Returns a dict with three lists:
          - "added": component IDs present in new_components but not in cache
          - "modified": component IDs whose content_hash differs
          - "deleted": component IDs in cache but absent from new_components

        Callers can use these lists for cascade wiki-page invalidation.
        """
        import hashlib as _hl

        def _hash_node(n) -> str:
            src = getattr(n, "source_code", None) or ""
            if src:
                return _hl.sha256(src.encode("utf-8", errors="replace")).hexdigest()[:16]
            sig = f"{n.name}|{n.start_line}|{n.end_line}|{json.dumps(n.parameters or [])}|{json.dumps(sorted(n.depends_on))}"
            return _hl.sha256(sig.encode()).hexdigest()[:16]

        # Load stored hashes
        rows = self.conn.execute("SELECT id, content_hash FROM components").fetchall()
        stored: Dict[str, str] = {r["id"]: (r["content_hash"] or "") for r in rows}

        added: List[str] = []
        modified: List[str] = []
        for cid, node in new_components.items():
            new_hash = _hash_node(node)
            if cid not in stored:
                added.append(cid)
            elif stored[cid] != new_hash:
                modified.append(cid)

        new_ids = set(new_components.keys())
        deleted = [cid for cid in stored if cid not in new_ids]

        if added or modified or deleted:
            logger.info("Stale detection: %d added, %d modified, %d deleted",
                        len(added), len(modified), len(deleted))
        return {"added": added, "modified": modified, "deleted": deleted}

    def get_leaf_nodes(self) -> List[str]:
        raw = self._mget("leaf_nodes")
        return json.loads(raw) if raw else []

    def get_all_metas(self) -> Dict[str, ComponentMeta]:
        rows = self.conn.execute(
            "SELECT id,name,component_type,file_path,relative_path,start_line,end_line,"
            "language,node_type,base_classes,class_name,display_name,qualified_name,"
            "has_docstring,parameters,depends_on FROM components").fetchall()
        out: Dict[str, ComponentMeta] = {}
        for r in rows:
            extra = _parse_row(r)
            out[r["id"]] = ComponentMeta(
                id=r["id"], name=r["name"], component_type=r["component_type"],
                file_path=r["file_path"], relative_path=r["relative_path"],
                start_line=r["start_line"], end_line=r["end_line"],
                language=r["language"] or "", depends_on=extra[0], node_type=r["node_type"],
                base_classes=extra[1], class_name=r["class_name"],
                display_name=r["display_name"], qualified_name=r["qualified_name"],
                has_docstring=bool(r["has_docstring"]), parameters=extra[2])
        return out

    def remove_by_file(self, fp: str) -> int:
        # Normalise to forward slashes for cross-platform LIKE matching.
        fp_norm = fp.replace("\\", "/")
        # Try exact match first (works when caller passes absolute path).
        ids = [
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM components WHERE file_path=?", (fp,)
            ).fetchall()
        ]
        if not ids:
            # Also try with normalised path.
            ids = [
                r["id"]
                for r in self.conn.execute(
                    "SELECT id FROM components WHERE replace(file_path, '\\', '/')=?",
                    (fp_norm,),
                ).fetchall()
            ]
        if not ids and "/" in fp_norm:
            # Fallback: suffix match — covers relative paths from detect_changes
            # and monorepo subpath cases.  Normalise backslashes in the DB value.
            # Only enabled when the path has at least one directory component,
            # otherwise "%/main.py" would wipe same-named files everywhere.
            ids = [
                r["id"]
                for r in self.conn.execute(
                    "SELECT id FROM components WHERE replace(file_path, '\\', '/') LIKE ?",
                    ("%/" + fp_norm,),
                ).fetchall()
            ]
        if ids:
            for chunk in _sql_chunks(ids):
                ph = ",".join("?" * len(chunk))
                self.conn.execute(
                    f"DELETE FROM components WHERE id IN ({ph})", chunk
                )
                self.conn.execute(
                    f"DELETE FROM dependencies WHERE source_id IN ({ph}) OR target_id IN ({ph})",
                    chunk + chunk,
                )
            self.conn.commit()
        return len(ids)

    # -- dependencies --

    def get_depends_on(self, cid: str) -> List[str]:
        r = self.conn.execute("SELECT depends_on FROM components WHERE id=?", (cid,)).fetchone()
        if not r: return []
        try: return json.loads(r["depends_on"]) or []
        except Exception: return []

    def get_depended_by(self, cid: str) -> List[str]:
        return [r["source_id"] for r in self.conn.execute(
            "SELECT source_id FROM dependencies WHERE target_id=?", (cid,)).fetchall()]

    def get_all_deps(self, direction="both") -> List[Dict[str, str]]:
        res = []
        if direction in ("depends_on", "both"):
            for r in self.conn.execute("SELECT source_id,target_id FROM dependencies ORDER BY source_id"):
                res.append({"source": r["source_id"], "target": r["target_id"], "direction": "depends_on"})
        if direction in ("depended_by", "both"):
            for r in self.conn.execute("SELECT target_id,source_id FROM dependencies ORDER BY target_id"):
                res.append({"source": r["target_id"], "target": r["source_id"], "direction": "depended_by"})
        return res

    # -- file fingerprints --

    def _hash_file(self, rel: str) -> Optional[Tuple[float, int, str]]:
        try:
            p = self.repo_path / rel
            s = p.stat()
            # Stream only the first 64KB instead of reading the whole file
            with open(p, "rb") as f:
                head = f.read(65536)
            h = hashlib.sha256(head).hexdigest()
            return s.st_mtime, s.st_size, h
        except OSError: return None

    def update_file_fingerprints(self, paths: List[str], commit_id=""):
        rows = [(p, *f, commit_id) for p in paths if (f := self._hash_file(p))]
        if rows: self.conn.executemany(
            "INSERT OR REPLACE INTO file_fingerprints VALUES(?,?,?,?,?)", rows); self.conn.commit()

    def get_all_fingerprints(self) -> Dict[str, Dict[str, Any]]:
        return {r["file_path"]: dict(mtime=r["mtime"], size=r["size"],
                content_hash=r["content_hash"], commit_id=r["commit_id"])
                for r in self.conn.execute("SELECT * FROM file_fingerprints").fetchall()}

    def get_cached_file_paths(self) -> Set[str]:
        """Return set of all file paths that have cached components."""
        rows = self.conn.execute(
            "SELECT DISTINCT relative_path FROM components"
        ).fetchall()
        return {r["relative_path"] for r in rows}

    def get_components_by_files(self, file_paths: Set[str]) -> Dict[str, Node]:
        """Load cached components for the given relative file paths."""
        if not file_paths:
            return {}
        rows = []
        norm_paths = [fp.replace("\\", "/") for fp in file_paths]
        for chunk in _sql_chunks(norm_paths):
            ph = ",".join("?" * len(chunk))
            rows.extend(self.conn.execute(
                f"SELECT * FROM components WHERE replace(relative_path, '\\', '/') IN ({ph})",
                chunk,
            ).fetchall())
        result: Dict[str, Node] = {}
        for r in rows:
            extra = _parse_row(r)
            result[r["id"]] = Node(
                id=r["id"], name=r["name"], component_type=r["component_type"],
                file_path=r["file_path"], relative_path=r["relative_path"],
                start_line=r["start_line"], end_line=r["end_line"],
                language=r["language"], depends_on=extra[0], node_type=r["node_type"],
                base_classes=extra[1], class_name=r["class_name"],
                display_name=r["display_name"], qualified_name=r["qualified_name"],
                has_docstring=bool(r["has_docstring"]), docstring=r["docstring"] or "",
                parameters=extra[2], source_code="",
            )
        return result

    # -- git change detection --

    _SRC_EXTS = {".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".c", ".h",
                 ".cpp", ".hpp", ".cc", ".hh", ".cs", ".kt", ".kts"}

    def detect_changes(self) -> Optional[Dict[str, Any]]:
        ch = self._git_detect(); return ch if ch is not None else self._fp_detect()

    def _git_detect(self) -> Optional[Dict[str, Any]]:
        try: import git; repo = git.Repo(self.repo_path, search_parent_directories=True)
        except Exception: return None
        prev = self.get_last_commit_id()
        if not prev: return None
        try: cur = repo.head.commit.hexsha
        except Exception: return None
        git_root = Path(repo.working_dir).resolve()
        try: sp = self.repo_path.resolve().relative_to(git_root).as_posix()
        except ValueError: sp = ""
        if sp == ".": sp = ""

        def _n(p: str) -> Optional[str]:
            if sp and not p.startswith(sp + "/"): return None
            p = p[len(sp)+1:] if sp else p
            return None if p.startswith(".codewiki/") else p

        ch, seen = [], set()
        def add(r): 
            if r and (p := _n(r)) and p not in seen: ch.append(p); seen.add(p)
        if prev != cur:
            try:
                for d in repo.commit(prev).diff(cur):
                    add(d.a_path); add(d.b_path)
            except Exception:
                logger.warning("Commit %s unreachable", prev); return None
        try:
            for d in list(repo.index.diff("HEAD")) + list(repo.index.diff(None)):
                add(d.a_path); add(d.b_path)
            for item in repo.untracked_files: add(item)
        except Exception: pass
        return {"changed_files": ch, "method": "git", "current_commit": cur}

    def _fp_detect(self) -> Optional[Dict[str, Any]]:
        cached = self.get_all_fingerprints()
        if not cached: return None
        ch, existing = [], set()
        for dp, dns, fns in os.walk(str(self.repo_path)):
            dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules","__pycache__","venv",".venv")]
            rd = Path(dp).relative_to(self.repo_path)
            for fn in fns:
                if Path(fn).suffix.lower() not in self._SRC_EXTS: continue
                rp = (rd / fn).as_posix() if rd != Path(".") else fn; existing.add(rp)
                cfp = self._hash_file(rp); prev = cached.get(rp)
                if cfp is None:
                    if prev is not None: ch.append(rp); continue
                if prev is None: ch.append(rp); continue
                if abs(cfp[0] - prev["mtime"]) > 1.0 or cfp[1] != prev["size"] or cfp[2] != prev["content_hash"]:
                    ch.append(rp)
        for cp in cached:
            if cp not in existing: ch.append(cp)
        return {"changed_files": ch, "method": "fingerprint",
                "no_changes": True} if not ch else {"changed_files": ch, "method": "fingerprint"}

    # -- BM25 search --
    # (tokeniser, stopwords and snippet extractor are now module-level;
    #  see _tokenize, _STOPWORDS, _extract_snippet above)

    def build_search_index(self, output_dir: Path) -> Dict[str, Any]:
        od = Path(output_dir); c = self.conn
        c.execute("DELETE FROM search_index"); c.execute("DELETE FROM search_token_index")
        c.execute("DELETE FROM search_stats")
        from codewiki.src.config import WIKI_SYSTEM_FILES, WIKI_DIR
        dc = nc = sc = 0

        # Scan wiki/ subdirectories recursively for doc pages
        wiki_dir = od / WIKI_DIR
        if wiki_dir.is_dir():
            for md in sorted(wiki_dir.rglob("*.md")):
                if not md.is_file(): continue
                if md.name in WIKI_SYSTEM_FILES: continue
                try: ct = md.read_text(encoding="utf-8", errors="replace")
                except OSError: continue
                if "<!-- crosslinks" in ct: ct = ct.split("<!-- crosslinks")[0]
                if not ct.strip(): continue
                title = _extract_title(ct) or md.stem.replace("_"," ").title()
                tokens = _tokenize(_build_indexable_text(ct))
                if not tokens: continue
                tf = {}; [tf.update({t: tf.get(t,0)+1}) for t in tokens]
                try: fk = str(md.relative_to(od)).replace("\\", "/")
                except ValueError: fk = md.name
                c.execute("INSERT OR REPLACE INTO search_index VALUES(?,?,?,?,?)",
                          (fk, title, "doc", len(tokens), json.dumps(tf)))
                for t, f in tf.items(): c.execute("INSERT OR IGNORE INTO search_token_index VALUES(?,?,?)", (t, fk, f))
                dc += 1

        # Also scan root-level .md files (for repos without wiki/ dir)
        for md in sorted(od.iterdir()):
            if not md.is_file() or md.suffix != ".md": continue
            if md.name in WIKI_SYSTEM_FILES: continue
            try: ct = md.read_text(encoding="utf-8", errors="replace")
            except OSError: continue
            if "<!-- crosslinks" in ct: ct = ct.split("<!-- crosslinks")[0]
            if not ct.strip(): continue
            title = _extract_title(ct) or md.stem.replace("_"," ").title()
            tokens = _tokenize(_build_indexable_text(ct))
            if not tokens: continue
            tf = {}; [tf.update({t: tf.get(t,0)+1}) for t in tokens]
            c.execute("INSERT OR REPLACE INTO search_index VALUES(?,?,?,?,?)",
                      (md.name, title, "doc", len(tokens), json.dumps(tf)))
            for t, f in tf.items(): c.execute("INSERT OR IGNORE INTO search_token_index VALUES(?,?,?)", (t, md.name, f))
            dc += 1

        # Scan notes/ directory
        nd = od / "notes"
        if nd.is_dir():
            for nf in sorted(nd.iterdir()):
                if not nf.is_file() or nf.suffix != ".md": continue
                try: ct = nf.read_text(encoding="utf-8", errors="replace")
                except OSError: continue
                if not ct.strip(): continue
                title = _extract_frontmatter(ct, "title") or nf.stem
                tokens = _tokenize(_build_indexable_text(ct))
                if not tokens: continue
                tf = {}; [tf.update({t: tf.get(t,0)+1}) for t in tokens]
                fk = f"notes/{nf.name}"
                c.execute("INSERT OR REPLACE INTO search_index VALUES(?,?,?,?,?)",
                          (fk, title, "note", len(tokens), json.dumps(tf)))
                for t, f in tf.items(): c.execute("INSERT OR IGNORE INTO search_token_index VALUES(?,?,?)", (t, fk, f))
                nc += 1

        # Scan raw/sources/ for third-party document text
        raw_dir = od / "raw" / "sources"
        if raw_dir.is_dir():
            for sf in sorted(raw_dir.iterdir()):
                if not sf.is_file(): continue
                if sf.suffix not in (".md", ".txt", ".rst"): continue
                try: ct = sf.read_text(encoding="utf-8", errors="replace")
                except OSError: continue
                if not ct.strip(): continue
                title = sf.stem.replace("_", " ").replace("-", " ").title()
                tokens = _tokenize(_build_indexable_text(ct))
                if not tokens: continue
                tf = {}; [tf.update({t: tf.get(t,0)+1}) for t in tokens]
                fk = f"raw/sources/{sf.name}"
                c.execute("INSERT OR REPLACE INTO search_index VALUES(?,?,?,?,?)",
                          (fk, title, "source", len(tokens), json.dumps(tf)))
                for t, f in tf.items(): c.execute("INSERT OR IGNORE INTO search_token_index VALUES(?,?,?)", (t, fk, f))
                sc += 1

        td = dc + nc + sc
        if td:
            avg = (c.execute("SELECT SUM(doc_len) FROM search_index").fetchone()[0] or 0) / td
            c.execute("INSERT INTO search_stats VALUES('total_docs',?)", (str(td),))
            c.execute("INSERT INTO search_stats VALUES('avg_doc_len',?)", (str(avg),))
        self.conn.commit()

        # Build inter-page link graph alongside the search index
        try:
            graph_info = self.build_link_graph(od)
        except Exception as e:
            logger.warning("Link graph build failed (non-fatal): %s", e)
            graph_info = {"edges": 0, "docs_scanned": 0}

        return {"docs_indexed": dc, "notes_indexed": nc, "sources_indexed": sc,
                "total_docs": td, "graph_edges": graph_info.get("edges", 0)}

    def search(self, query: str, *, scope="", include_notes=True,
               max_results=10, score_threshold=0.1,
               output_dir: Optional[Path] = None,
               type_filter: Optional[str] = None,
               hop: int = 0, decay: float = 0.5,
               expand_terms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        c = self.conn
        r = c.execute(
            "SELECT value FROM search_stats WHERE key='total_docs'"
        ).fetchone()
        if not r or int(r["value"]) == 0:
            return []
        n = int(r["value"])
        r = c.execute(
            "SELECT value FROM search_stats WHERE key='avg_doc_len'"
        ).fetchone()
        avg_dl = float(r["value"]) if r else 1.0

        qts = _tokenize(query)
        if expand_terms:
            for t in expand_terms:
                for tt in _tokenize(t):
                    if tt not in qts:
                        qts.append(tt)
        # Ontology-based synonym expansion (automatic, no caller action needed)
        ontology = _load_ontology(output_dir)
        if ontology:
            qts = _expand_with_ontology(qts, ontology)
        if not qts:
            return []
        max_results = min(20, max(1, max_results))

        # Determine allowed source types from type_filter
        allowed_source_types: Optional[Set[str]] = None
        page_type_dir: Optional[str] = None
        if type_filter:
            if type_filter == "doc":
                allowed_source_types = {"doc"}
            elif type_filter == "note":
                allowed_source_types = {"note"}
            elif type_filter == "source":
                allowed_source_types = {"source"}
            else:
                # page_type filter (module, entity, concept, etc.)
                from codewiki.src.config import PAGE_TYPE_DIRS
                page_type_dir = PAGE_TYPE_DIRS.get(type_filter, type_filter + "s")
                allowed_source_types = {"doc"}

        # Candidate docs via token index
        ph = ",".join("?" * len(qts))
        cands = {
            row["doc_key"]
            for row in c.execute(
                f"SELECT DISTINCT doc_key FROM search_token_index WHERE token IN ({ph})",
                qts,
            )
        }
        if not cands:
            return []

        # Pre-cache doc_freq for each query token (avoids N+1 per candidate)
        df_cache: Dict[str, int] = {}
        for qt in qts:
            row = c.execute(
                "SELECT COUNT(*) AS c FROM search_token_index WHERE token=?",
                (qt,),
            ).fetchone()
            df_cache[qt] = row["c"] if row else 1

        scored: List[Tuple[float, str]] = []
        for dk in cands:
            if scope:
                scope_norm = scope.lower().replace(" ", "_").rstrip("/")
                path_lower = dk.lower().replace("\\", "/")
                stem = Path(dk).stem.lower().replace("_", " ")
                # Match by: stem equality, path prefix, or path component
                if (stem != scope_norm.replace("_", " ")
                        and not path_lower.startswith(scope_norm + "/")
                        and f"/{scope_norm}/" not in f"/{path_lower}"):
                    continue
            # Single merged query: title, source, doc_len
            doc_row = c.execute(
                "SELECT title, source, doc_len FROM search_index WHERE doc_key=?",
                (dk,),
            ).fetchone()
            if not doc_row:
                continue
            if not include_notes and doc_row["source"] == "note":
                continue
            # LLM Wiki: type_filter enforcement
            if allowed_source_types and doc_row["source"] not in allowed_source_types:
                continue
            if page_type_dir and f"wiki/{page_type_dir}/" not in dk:
                continue
            dl = doc_row["doc_len"] or 1

            score = 0.0
            for qt in qts:
                tfr = c.execute(
                    "SELECT tf FROM search_token_index WHERE token=? AND doc_key=?",
                    (qt, dk),
                ).fetchone()
                if not tfr:
                    continue
                df = df_cache.get(qt, 1)
                idf = max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))
                score += idf * (tfr["tf"] * (_K1 + 1)) / (
                    tfr["tf"] + _K1 * (1 - _B + _B * dl / avg_dl)
                )
            # Developer notes are short; BM25 scores are naturally low and would
            # be filtered by the generic threshold even when the title matches
            # the query. Treat any title-token match on a note as relevant.
            if doc_row["source"] == "note":
                title_tokens = set(_tokenize(doc_row["title"] or ""))
                if title_tokens & set(qts) and score > 0:
                    score = max(score, score_threshold)
            if score >= score_threshold:
                scored.append((score, dk))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[Dict[str, Any]] = []
        for s, dk in scored[:max_results]:
            doc_row = c.execute(
                "SELECT title, source FROM search_index WHERE doc_key=?", (dk,)
            ).fetchone()
            snippet = ""
            if output_dir is not None:
                fpath = Path(output_dir) / dk
                if fpath.exists():
                    try:
                        raw = fpath.read_text(encoding="utf-8", errors="replace")
                        snippet = _extract_snippet(raw, qts)[:300]
                    except OSError:
                        pass
            entry: Dict[str, Any] = {
                "file": dk,
                "title": doc_row["title"] if doc_row else dk,
                "source": doc_row["source"] if doc_row else "doc",
                "snippet": snippet,
                "relevance_score": round(s, 4),
            }
            # Attach related pages from link graph
            related = self.get_related_pages(dk, limit=5)
            if related:
                entry["related"] = related
            results.append(entry)

        # Graph expansion: discover related docs beyond BM25 hits
        if hop > 0 and scored:
            seed_docs = [(dk, s) for s, dk in scored[:max_results]]
            expanded = self.graph_expand(seed_docs, hop=hop, decay=decay)
            existing_keys = {r["file"] for r in results}
            for ex in expanded:
                if ex["file"] in existing_keys:
                    continue
                doc_row = c.execute(
                    "SELECT title, source FROM search_index WHERE doc_key=?",
                    (ex["file"],),
                ).fetchone()
                if not doc_row:
                    continue
                if not include_notes and doc_row["source"] == "note":
                    continue
                snippet = ""
                if output_dir is not None:
                    fpath = Path(output_dir) / ex["file"]
                    if fpath.exists():
                        try:
                            raw = fpath.read_text(encoding="utf-8", errors="replace")
                            snippet = _extract_snippet(raw, qts)[:300]
                        except OSError:
                            pass
                results.append({
                    "file": ex["file"],
                    "title": doc_row["title"],
                    "source": doc_row["source"],
                    "snippet": snippet,
                    "relevance_score": ex["score"],
                    "hop": ex["hop"],
                    "via": ex["via"],
                })
                existing_keys.add(ex["file"])

        return results

    def update_search_doc(self, output_dir: Path, filepath: Path):
        try: fk = str(filepath.resolve().relative_to(Path(output_dir).resolve()))
        except ValueError: fk = filepath.name
        ap = Path(output_dir) / fk
        if not ap.exists():
            self.conn.execute("DELETE FROM search_index WHERE doc_key=?",(fk,))
            self.conn.execute("DELETE FROM search_token_index WHERE doc_key=?",(fk,)); self.conn.commit(); return
        try: ct = ap.read_text(encoding="utf-8", errors="replace")
        except OSError: return
        if "<!-- crosslinks" in ct: ct = ct.split("<!-- crosslinks")[0]
        src = "note" if fk.startswith("notes/") else "doc"
        tokens = _tokenize(_build_indexable_text(ct))
        self.conn.execute("DELETE FROM search_index WHERE doc_key=?",(fk,))
        self.conn.execute("DELETE FROM search_token_index WHERE doc_key=?",(fk,))
        if tokens:
            tf = {}; [tf.update({t: tf.get(t,0)+1}) for t in tokens]
            self.conn.execute("INSERT OR REPLACE INTO search_index VALUES(?,?,?,?,?)",
                              (fk, filepath.stem, src, len(tokens), json.dumps(tf)))
            for t, f in tf.items(): self.conn.execute("INSERT OR IGNORE INTO search_token_index VALUES(?,?,?)", (t, fk, f))
        self.conn.commit()

    # -- wiki link graph --

    _WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
    _MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")

    def build_link_graph(self, output_dir: Path) -> Dict[str, Any]:
        """Scan wiki pages for inter-page links and rebuild wiki_links table.

        Extracts [[wikilink]] and [text](path.md) patterns, resolves targets
        to doc_keys in the search_index, and stores directed edges.
        """
        od = Path(output_dir)
        c = self.conn
        c.execute("DELETE FROM wiki_links")

        # Build a lookup: stem/slug → doc_key for resolution
        all_docs = {
            row["doc_key"]: row["title"]
            for row in c.execute("SELECT doc_key, title FROM search_index").fetchall()
        }
        # Map various forms to doc_key for target resolution
        stem_to_key: Dict[str, str] = {}
        title_to_key: Dict[str, str] = {}
        for dk, title in all_docs.items():
            stem = Path(dk).stem.lower().replace("_", "-")
            stem_to_key[stem] = dk
            stem_to_key[Path(dk).stem.lower()] = dk
            if title:
                title_to_key[title.lower()] = dk
                title_to_key[title.lower().replace(" ", "-")] = dk

        edges: Set[Tuple[str, str, str]] = set()

        from codewiki.src.config import WIKI_SYSTEM_FILES, WIKI_DIR
        wiki_dir = od / WIKI_DIR
        scan_dirs = [wiki_dir] if wiki_dir.is_dir() else [od]
        # Also scan root-level .md files
        if wiki_dir.is_dir():
            scan_dirs.append(od)

        seen_files: Set[Path] = set()
        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for md in scan_dir.rglob("*.md") if scan_dir == wiki_dir else scan_dir.iterdir():
                if not md.is_file() or md.suffix != ".md":
                    continue
                if md.name in WIKI_SYSTEM_FILES:
                    continue
                if md in seen_files:
                    continue
                seen_files.add(md)
                try:
                    ct = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                try:
                    source_key = str(md.relative_to(od)).replace("\\", "/")
                except ValueError:
                    source_key = md.name
                if source_key not in all_docs:
                    continue

                # Strip crosslinks section for cleaner parsing (it has its own links)
                body = ct.split("<!-- crosslinks")[0] if "<!-- crosslinks" in ct else ct

                # Extract [[wikilink]] targets
                for m in self._WIKILINK_RE.finditer(body):
                    target_raw = m.group(1).strip()
                    resolved = self._resolve_link_target(
                        target_raw, stem_to_key, title_to_key, all_docs)
                    if resolved and resolved != source_key:
                        edges.add((source_key, resolved, "wikilink"))

                # Extract [text](path.md) targets
                for m in self._MDLINK_RE.finditer(body):
                    href = m.group(2).strip()
                    if href.startswith("http"):
                        continue
                    # Resolve relative path to doc_key
                    resolved = self._resolve_md_href(href, source_key, all_docs)
                    if resolved and resolved != source_key:
                        edges.add((source_key, resolved, "mdlink"))

        if edges:
            c.executemany(
                "INSERT OR IGNORE INTO wiki_links(source_doc, target_doc, link_type) VALUES(?,?,?)",
                list(edges),
            )
        c.commit()
        logger.info("Link graph built: %d edges from %d docs", len(edges), len(all_docs))
        return {"edges": len(edges), "docs_scanned": len(all_docs)}

    def _resolve_link_target(
        self, target: str, stem_to_key: Dict[str, str],
        title_to_key: Dict[str, str], all_docs: Dict[str, str],
    ) -> Optional[str]:
        """Resolve a [[wikilink]] target to a doc_key."""
        t = target.strip().lower().replace(".md", "")
        # Direct stem match
        if t in stem_to_key:
            return stem_to_key[t]
        # Title match
        if t in title_to_key:
            return title_to_key[t]
        # Slugified match
        slug = re.sub(r"[\s_]+", "-", t).strip("-")
        if slug in stem_to_key:
            return stem_to_key[slug]
        return None

    def _resolve_md_href(
        self, href: str, source_key: str, all_docs: Dict[str, str],
    ) -> Optional[str]:
        """Resolve a markdown [text](path.md) href to a doc_key."""
        # Join href relative to source's directory, then normalize ../ segments
        source_dir = str(Path(source_key).parent).replace("\\", "/")
        href = href.replace("\\", "/")
        if source_dir == ".":
            candidate = href
        else:
            candidate = f"{source_dir}/{href}"
        # Normalize ../ and ./ segments
        parts = candidate.split("/")
        resolved_parts: List[str] = []
        for p in parts:
            if p == "..":
                if resolved_parts:
                    resolved_parts.pop()
            elif p not in (".", ""):
                resolved_parts.append(p)
        candidate = "/".join(resolved_parts)
        if candidate in all_docs:
            return candidate
        # Try without wiki/ prefix variations
        if candidate.startswith("wiki/") and candidate[5:] in all_docs:
            return candidate[5:]
        return None

    def graph_expand(
        self, seed_docs: List[Tuple[str, float]], *,
        hop: int = 1, decay: float = 0.5, min_score: float = 0.05,
        max_expand: int = 30,
    ) -> List[Dict[str, Any]]:
        """BFS expansion from seed docs along wiki_links edges.

        Args:
            seed_docs: List of (doc_key, bm25_score) from initial search.
            hop: Number of hops to expand (0 = no expansion).
            decay: Score multiplier per hop.
            min_score: Minimum score threshold for expanded nodes.
            max_expand: Maximum number of expanded nodes to return.

        Returns:
            List of {file, score, hop, via} for expanded docs (excludes seeds).
        """
        if hop <= 0:
            return []

        seed_keys = {dk for dk, _ in seed_docs}
        # score_map tracks best score for each discovered node
        discovered: Dict[str, Dict[str, Any]] = {}
        # BFS frontier: (doc_key, current_score, current_hop, via_doc)
        frontier: List[Tuple[str, float, int, str]] = [
            (dk, score, 0, "") for dk, score in seed_docs
        ]

        c = self.conn
        for _ in range(hop):
            next_frontier: List[Tuple[str, float, int, str]] = []
            for doc_key, score, cur_hop, via in frontier:
                if cur_hop >= hop:
                    continue
                next_score = score * decay
                if next_score < min_score:
                    continue
                # Get neighbors (both directions for undirected traversal)
                neighbors = set()
                for row in c.execute(
                    "SELECT target_doc FROM wiki_links WHERE source_doc=?", (doc_key,)
                ):
                    neighbors.add(row["target_doc"])
                for row in c.execute(
                    "SELECT source_doc FROM wiki_links WHERE target_doc=?", (doc_key,)
                ):
                    neighbors.add(row["source_doc"])

                for nb in neighbors:
                    if nb in seed_keys:
                        continue
                    if nb in discovered and discovered[nb]["score"] >= next_score:
                        continue
                    discovered[nb] = {
                        "file": nb, "score": round(next_score, 4),
                        "hop": cur_hop + 1, "via": doc_key,
                    }
                    next_frontier.append((nb, next_score, cur_hop + 1, doc_key))
            frontier = next_frontier
            if not frontier:
                break

        # Sort by score descending, cap at max_expand
        result = sorted(discovered.values(), key=lambda x: x["score"], reverse=True)
        return result[:max_expand]

    def get_related_pages(self, doc_key: str, limit: int = 8) -> List[Dict[str, str]]:
        """Get pages linked to/from a given doc (for 'related' field in results)."""
        c = self.conn
        related: Dict[str, str] = {}  # doc_key → direction
        for row in c.execute(
            "SELECT target_doc FROM wiki_links WHERE source_doc=?", (doc_key,)
        ):
            related[row["target_doc"]] = "out"
        for row in c.execute(
            "SELECT source_doc FROM wiki_links WHERE target_doc=?", (doc_key,)
        ):
            if row["source_doc"] in related:
                related[row["source_doc"]] = "both"
            else:
                related[row["source_doc"]] = "in"

        # Get titles for related pages
        result = []
        for dk, direction in list(related.items())[:limit]:
            row = c.execute(
                "SELECT title FROM search_index WHERE doc_key=?", (dk,)
            ).fetchone()
            result.append({
                "file": dk,
                "title": row["title"] if row else Path(dk).stem,
                "direction": direction,
            })
        return result

# ------------------------------------------------------------------ helpers

def _parse_row(r: sqlite3.Row) -> Tuple[Set[str], Optional[List], Optional[List]]:
    deps = set()
    try:
        raw = r["depends_on"]
        if raw and raw != "[]": deps = set(json.loads(raw))
    except Exception: pass
    bc = None
    try:
        raw = r["base_classes"]
        if raw: bc = json.loads(raw)
    except Exception: pass
    params = None
    try:
        raw = r["parameters"]
        if raw: params = json.loads(raw)
    except Exception: pass
    return deps, bc, params

def _extract_title(content: str) -> Optional[str]:
    for l in content.splitlines()[:30]:
        s = l.strip()
        if s.startswith("# "): return s[2:].strip()
    return None

def _extract_frontmatter(content: str, key: str) -> Optional[str]:
    if not content.startswith("---"): return None
    try:
        end = content.index("---", 3)
        for l in content[3:end].splitlines():
            if l.startswith(f"{key}:"): return l[len(key)+1:].strip().strip('"').strip("'")
    except ValueError: pass
    return None
