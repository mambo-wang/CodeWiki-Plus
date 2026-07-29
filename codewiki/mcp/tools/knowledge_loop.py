"""MCP tools: ingest_note + query_wiki — knowledge loop for LLM Wiki.

ingest_note: File structured notes (decisions, lessons, architecture rationale)
into the repowiki/notes/ directory with an index for fast retrieval.

query_wiki: Search across generated docs + ingested notes, returning relevant
context for new development tasks.  Uses BM25 inverted index (jieba tokenisation)
with automatic index building and keyword-matching fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.cache import _STOPWORDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  ingest_note
# ---------------------------------------------------------------------------

def _slugify(title: str) -> str:
    """Create a URL-safe slug from a title. Falls back to hash for CJK-heavy titles."""
    # Remove non-alphanumeric characters (except hyphens and spaces)
    slug = re.sub(r"[^\w\s-]", "", title.lower().strip())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    if len(slug) < 3:
        # CJK-heavy title — use hash
        slug = hashlib.sha1(title.encode()).hexdigest()[:8]
    elif len(slug) > 60:
        slug = slug[:60].rstrip("-")
    return slug


def _auto_match_modules(
    content: str,
    module_tree: Dict[str, Any],
) -> List[str]:
    """Match content keywords against module names for auto-tagging."""
    if not module_tree:
        return []

    module_names: List[str] = []

    def _collect(tree: dict):
        for name in tree.keys():
            module_names.append(name)
            children = tree[name].get("children", {})
            if isinstance(children, dict):
                _collect(children)

    _collect(module_tree)

    matched: List[str] = []
    content_lower = content.lower()
    for name in module_names:
        # Match if module name (lowered) appears in content
        if name.lower() in content_lower:
            matched.append(name)
            continue
        # Match individual words from module name
        words = re.split(r"[\s_-]+", name.lower())
        if len(words) > 1 and sum(1 for w in words if w in content_lower) >= len(words) // 2:
            matched.append(name)

    return matched[:5]  # cap at 5


def _extract_tags(title: str, content: str, note_type: str) -> List[str]:
    """Extract searchable tags from note content."""
    tags: Set[str] = {note_type}
    # Extract #hashtags
    for match in re.finditer(r"#(\w+)", title + " " + content):
        tags.add(match.group(1).lower())
    # Extract code-like identifiers (CamelCase, snake_case)
    for match in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", content[:500]):
        tags.add(match.group(1).lower())
    return sorted(tags)[:15]


# ---------------------------------------------------------------------------
#  Symbol linking: auto-link CamelCase names to source files
# ---------------------------------------------------------------------------

# Matches PascalCase identifiers: starts with uppercase, has at least one
# lowercase letter, and contains at least one uppercase→lowercase transition.
_CAMEL_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]*)*)\b")


def _load_symbol_map(output_dir: Path, session=None) -> Dict[str, List[str]]:
    """Load symbol map. Prefers SQLite (via session cache or standalone DB), falls back to JSON."""
    # Fast path: SQLite symbols table (active session)
    if session is not None and getattr(session, "cache", None) is not None:
        try:
            data = session.cache.load_symbol_map()
            if data:
                return data
        except Exception:
            pass

    # Standalone SQLite (no active session)
    if session is None:
        try:
            from codewiki.mcp.tools.wiki_search import _resolve_db_path
            from codewiki.mcp.cache import AnalysisCache
            db_path = _resolve_db_path(output_dir)
            if db_path is not None:
                cache = AnalysisCache(db_path.parent.parent, db_path=db_path)
                data = cache.load_symbol_map()
                cache.close()
                if data:
                    return data
        except Exception:
            pass

    # Fallback: JSON file
    from codewiki.src.config import SYMBOL_MAP_FILENAME, meta_resolve

    sm_path = Path(meta_resolve(output_dir, SYMBOL_MAP_FILENAME))
    if not sm_path.exists():
        return {}
    try:
        data = json.loads(sm_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _inject_symbol_links(content: str, output_dir: Path, depth: int = 2, session=None) -> str:
    """Replace CamelCase identifiers with source-file links.

    Args:
        content: Markdown content to process.
        output_dir: The repowiki root directory (contains symbol_map).
        depth: Directory depth from the file to repo root.
               2 for notes/ (../../), 1 for root-level docs (../).
        session: Optional session with SQLite cache for fast symbol lookup.

    Skips identifiers inside:
      - YAML frontmatter (between opening and closing ``---``)
      - fenced code blocks (``` ... ```)
      - inline code (`` ` ... ` ``)
      - existing markdown links (`` [text](url) ``)
      - HTML comments
    """
    symbol_map = _load_symbol_map(output_dir, session=session)
    if not symbol_map:
        return content

    # --- protect regions that should not be modified ---
    protected: List[str] = []
    _PLACEHOLDER = "\x00PROT{:04d}\x00"

    def _protect(match: re.Match) -> str:
        idx = len(protected)
        protected.append(match.group(0))
        return _PLACEHOLDER.format(idx)

    text = content

    # 1. YAML frontmatter
    text = re.sub(r"^---\n.*?\n---\n", _protect, text, count=1, flags=re.DOTALL)
    # 2. Fenced code blocks
    text = re.sub(r"```.*?```", _protect, text, flags=re.DOTALL)
    # 3. Inline code
    text = re.sub(r"`[^`]+`", _protect, text)
    # 4. Existing markdown links  [text](url)
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", _protect, text)
    # 5. HTML comments
    text = re.sub(r"<!--.*?-->", _protect, text, flags=re.DOTALL)

    # --- compute relative path prefix based on depth ---
    prefix = "../" * depth

    # --- replace CamelCase identifiers with links ---
    def _replace_symbol(match: re.Match) -> str:
        name = match.group(1)
        paths = symbol_map.get(name)
        if not paths:
            return name  # not in symbol map, leave as-is
        target = paths[0].replace("\\", "/")  # normalise Windows paths
        return f"[{name}]({prefix}{target})"

    text = _CAMEL_RE.sub(_replace_symbol, text)

    # --- restore protected regions ---
    for i, original in enumerate(protected):
        text = text.replace(_PLACEHOLDER.format(i), original)

    return text


def handle_ingest_note(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Ingest a structured note into the knowledge base."""
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)

    # Resolve output directory
    od = arguments.get("output_dir")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir)
    else:
        return json.dumps({"error": "output_dir is required."})

    from codewiki.src.config import NOTES_DIR

    notes_dir = output_dir / NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)
    # Ensure .meta/ exists for search index persistence
    (output_dir / ".meta").mkdir(parents=True, exist_ok=True)

    note_type = arguments.get("note_type", "general")
    title = arguments.get("title", "Untitled")
    content = arguments.get("content", "")
    related_modules = arguments.get("related_modules", [])
    related_components = arguments.get("related_components", [])

    # LLM Wiki: new fields for pitfall/known_issue/workaround notes
    severity = arguments.get("severity")
    root_cause = arguments.get("root_cause")
    source_ref = arguments.get("source_ref")
    aliases = arguments.get("aliases", [])
    # Roadmap 2.2: knowledge flywheel status
    note_status = arguments.get("status", "candidate")  # candidate | confirmed | rejected

    # Auto-match modules if not provided
    auto_matched: List[str] = []
    if not related_modules and session and session.module_tree:
        auto_matched = _auto_match_modules(content + " " + title, session.module_tree)
        related_modules = auto_matched

    # Generate filename
    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(title)
    filename = f"{today}-{slug}.md"
    note_path = notes_dir / filename

    # Duplicate check
    if note_path.exists():
        # Try with a hash suffix
        hash_suffix = hashlib.sha1(
            (title + content[:100]).encode()
        ).hexdigest()[:6]
        filename = f"{today}-{slug}-{hash_suffix}.md"
        note_path = notes_dir / filename

    # Build note content with YAML frontmatter
    tags = _extract_tags(title, content, note_type)
    frontmatter_lines = [
        "---",
        f"type: {note_type}",
        f"title: \"{title}\"",
        f"date: {today}",
        f"related_modules: {json.dumps(related_modules, ensure_ascii=False)}",
        f"related_components: {json.dumps(related_components, ensure_ascii=False)}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
    ]
    # LLM Wiki: add optional fields
    if aliases:
        frontmatter_lines.append(f"aliases: {json.dumps(aliases, ensure_ascii=False)}")
    if severity:
        frontmatter_lines.append(f"severity: {severity}")
    if root_cause:
        frontmatter_lines.append(f"root_cause: \"{root_cause}\"")
    if source_ref:
        frontmatter_lines.append(f"source_ref: \"{source_ref}\"")
    frontmatter_lines.append(f"status: {note_status}")
    frontmatter_lines.append("---")
    note_content = "\n".join(frontmatter_lines) + "\n\n" + content + "\n"

    # Inject source-file links for CamelCase symbols found in symbol_map.json
    try:
        from codewiki.mcp.tools.page_router import compute_depth
        depth = compute_depth(note_path, output_dir)
        # symbol_map paths are relative to repo root; add extra levels to
        # escape output_dir up to the repository root.
        if session and hasattr(session, "repo_path"):
            try:
                extra = len(output_dir.resolve().relative_to(
                    Path(session.repo_path).resolve()).parts)
                depth += extra
            except ValueError:
                pass
        linked_content = _inject_symbol_links(note_content, output_dir, depth=depth, session=session)
        if linked_content != note_content:
            note_content = linked_content
    except Exception as e:
        logger.debug("Symbol linking skipped: %s", e)

    note_path.write_text(note_content, encoding="utf-8")

    # LLM Wiki: update index.md and log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(str(output_dir), "ingest_note",
                   f"添加笔记: {title}")
        rebuild_index(str(output_dir))
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)

    # Update BM25 search index for the new note (SQLite-backed when session available)
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(output_dir, note_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)

    result: Dict[str, Any] = {
        "status": "ingested",
        "note_status": note_status,
        "note_path": str(note_path),
        "note_type": note_type,
        "auto_matched_modules": auto_matched,
        "related_modules": related_modules,
        "tags": tags,
    }
    if note_status == "candidate":
        result["hint"] = (
            "Note saved with status=candidate; query_wiki will show it with an "
            "[unconfirmed] prefix. Call confirm_note(note_file=...) after review "
            "to promote it to verified knowledge."
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
#  confirm_note / reject_note (Roadmap 2.2 — knowledge flywheel)
# ---------------------------------------------------------------------------

def _resolve_within(output_dir: Path, relative: str) -> Optional[Path]:
    """Resolve *relative* against *output_dir*, rejecting path traversal.

    Returns the resolved path, or ``None`` if it escapes *output_dir*.
    """
    base = output_dir.resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _update_note_status(output_dir: Path, note_file: str, new_status: str,
                        reason: str = "") -> str:
    """Update the status field in a note's YAML frontmatter."""
    from codewiki.src.config import NOTES_DIR

    note_path = _resolve_within(output_dir, f"{NOTES_DIR}/{note_file}")
    if note_path is None:
        return json.dumps({"error": f"Invalid note_file path: {note_file}"})
    if not note_path.exists():
        # Try direct path
        note_path = _resolve_within(output_dir, note_file)
        if note_path is None:
            return json.dumps({"error": f"Invalid note_file path: {note_file}"})
    if not note_path.exists():
        return json.dumps({"error": f"Note not found: {note_file}"})

    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError as e:
        return json.dumps({"error": f"Cannot read note: {e}"})

    if not text.startswith("---"):
        return json.dumps({"error": "Note has no YAML frontmatter."})

    end = text.find("---", 3)
    if end < 0:
        return json.dumps({"error": "Malformed frontmatter."})

    fm_text = text[3:end]
    body = text[end + 3:]

    # Replace or insert status line
    import re as _re
    if _re.search(r"^status:", fm_text, _re.MULTILINE):
        fm_text = _re.sub(r"^status:.*$", f"status: {new_status}", fm_text, flags=_re.MULTILINE)
    else:
        fm_text = fm_text.rstrip("\n") + f"\nstatus: {new_status}\n"

    # Add rejection reason if provided
    if reason and new_status == "rejected":
        if _re.search(r"^reject_reason:", fm_text, _re.MULTILINE):
            fm_text = _re.sub(r"^reject_reason:.*$", f'reject_reason: "{reason}"', fm_text, flags=_re.MULTILINE)
        else:
            fm_text = fm_text.rstrip("\n") + f'\nreject_reason: "{reason}"\n'

    new_text = f"---{fm_text}---{body}"
    note_path.write_text(new_text, encoding="utf-8")

    # Update search index
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(output_dir, note_path)
    except Exception:
        pass

    return json.dumps({
        "status": new_status,
        "note_file": str(note_path.relative_to(output_dir)),
        "message": f"Note marked as {new_status}." + (f" Reason: {reason}" if reason else ""),
    }, indent=2, ensure_ascii=False)


def handle_confirm_note(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Confirm a candidate note, promoting it to verified domain knowledge."""
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)
    od = arguments.get("output_dir")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir)
    else:
        return json.dumps({"error": "output_dir is required."})

    note_file = arguments.get("note_file", "")
    if not note_file:
        return json.dumps({"error": "note_file is required (relative path within notes/)."})

    return _update_note_status(output_dir, note_file, "confirmed")


def handle_reject_note(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Reject a candidate note, excluding it from future query results."""
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)
    od = arguments.get("output_dir")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir)
    else:
        return json.dumps({"error": "output_dir is required."})

    note_file = arguments.get("note_file", "")
    if not note_file:
        return json.dumps({"error": "note_file is required (relative path within notes/)."})
    reason = arguments.get("reason", "")

    return _update_note_status(output_dir, note_file, "rejected", reason)


# ---------------------------------------------------------------------------
#  query_wiki
# ---------------------------------------------------------------------------

def _extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords from a query string."""
    # Basic tokenization: replace brackets then split on whitespace and punctuation
    cleaned = query.replace("[", " ").replace("]", " ")
    tokens = re.split(r"[\s,;:!?。？！，；：""''（）(){}<>]+", cleaned.lower())
    # Filter stopwords and short tokens
    keywords = [
        t for t in tokens
        if t and t not in _STOPWORDS and len(t) >= 2
    ]
    return keywords


def _score_document(
    content: str,
    keywords: List[str],
) -> Tuple[float, str]:
    """Score a document against keywords. Returns (score, snippet)."""
    if not keywords:
        return 0.0, ""

    content_lower = content.lower()
    lines = content.splitlines()

    total_hits = 0
    keyword_hits: Dict[str, int] = {}
    hit_lines: List[int] = []

    for kw in keywords:
        count = content_lower.count(kw)
        if count > 0:
            keyword_hits[kw] = count
            total_hits += count
            # Find lines containing this keyword
            for i, line in enumerate(lines):
                if kw in line.lower():
                    hit_lines.append(i)

    if total_hits == 0:
        return 0.0, ""

    # TF-IDF style scoring
    unique_keywords_hit = len(keyword_hits)
    coverage = unique_keywords_hit / len(keywords) if keywords else 0
    # Normalize by document length (prevent long docs from dominating)
    length_factor = min(1.0, 50 / max(len(lines), 1))

    score = coverage * 0.6 + min(total_hits / 10, 1.0) * 0.3 + length_factor * 0.1

    # Extract snippet: 3 lines around the first hit
    if hit_lines:
        center = hit_lines[0]
        start = max(0, center - 1)
        end = min(len(lines), center + 3)
        snippet = "\n".join(lines[start:end]).strip()
    else:
        snippet = lines[0][:200] if lines else ""

    return round(score, 4), snippet


def _get_module_doc_name(module_name: str) -> str:
    """Convert module name to expected doc filename."""
    return module_name.lower().replace(" ", "_") + ".md"


# ---------------------------------------------------------------------------
#  Progressive reading modes (1.3 Roadmap)
# ---------------------------------------------------------------------------

def _extract_frontmatter_block(text: str) -> Dict[str, Any]:
    """Parse YAML frontmatter into a dict. Returns {} on failure."""
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
        fm_text = text[3:end]
    except ValueError:
        return {}
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def _extract_section(text: str, section_title: str) -> Optional[str]:
    """Extract a markdown section by heading title (## or ###).

    Returns the section content (including sub-headings) up to the next
    heading of the same or higher level, or None if not found.
    """
    lines = text.splitlines()
    start_idx = None
    start_level = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            if section_title.lower() in title.lower():
                start_idx = i
                start_level = level
                break

    if start_idx is None:
        return None

    # Collect until next heading of same or higher level
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level <= start_level:
                end_idx = j
                break

    return "\n".join(lines[start_idx:end_idx]).strip()


def _query_mode_overview(
    output_dir: Path,
    query: str,
    scope: Optional[str],
    type_filter: Optional[str],
    max_results: int,
    session,
) -> str:
    """Mode=overview: lightweight orientation — overview.md + page frontmatter list."""
    from codewiki.src.config import WIKI_DIR, OVERVIEW_FILENAME, WIKI_SYSTEM_FILES

    result: Dict[str, Any] = {"mode": "overview", "query": query}

    # 1. Include overview.md content (truncated)
    overview_path = output_dir / OVERVIEW_FILENAME
    if not overview_path.exists():
        overview_path = output_dir / WIKI_DIR / OVERVIEW_FILENAME
    if overview_path.exists():
        try:
            ov_text = overview_path.read_text(encoding="utf-8", errors="replace")
            # Strip frontmatter
            if ov_text.startswith("---"):
                end = ov_text.find("---", 3)
                if end > 0:
                    ov_text = ov_text[end + 3:]
            result["overview"] = ov_text[:1500].strip()
        except OSError:
            result["overview"] = ""

    # 2. List matching pages with frontmatter only
    pages: List[Dict[str, Any]] = []
    wiki_dir = output_dir / WIKI_DIR
    scan_dir = wiki_dir if wiki_dir.is_dir() else output_dir

    for md_file in scan_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel = str(md_file.relative_to(output_dir))
        if scope and not rel.startswith(scope) and scope.lower() not in rel.lower():
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _extract_frontmatter_block(text)
        page_type = fm.get("type", "")
        if type_filter and page_type != type_filter:
            continue
        pages.append({
            "file": rel,
            "title": fm.get("title", md_file.stem),
            "type": page_type,
            "tags": fm.get("tags", []),
            "description": fm.get("description", "")[:120],
        })

    # Sort by relevance to query (simple keyword overlap)
    if query:
        q_tokens = set(query.lower().split())
        for p in pages:
            text_blob = f"{p['title']} {p['description']} {' '.join(p['tags'])}".lower()
            p["_score"] = sum(1 for t in q_tokens if t in text_blob)
        pages.sort(key=lambda x: x["_score"], reverse=True)
        for p in pages:
            del p["_score"]

    result["pages"] = pages[:max_results]
    result["total_pages"] = len(pages)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _query_mode_directory(
    output_dir: Path,
    query: str,
    scope: Optional[str],
    type_filter: Optional[str],
    max_results: int,
    session,
) -> str:
    """Mode=directory: return Component Constraint Index sections from matching pages."""
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    result: Dict[str, Any] = {"mode": "directory", "query": query}
    directories: List[Dict[str, Any]] = []

    wiki_dir = output_dir / WIKI_DIR
    scan_dir = wiki_dir if wiki_dir.is_dir() else output_dir

    # First pass: find relevant pages via keyword matching
    candidates: List[tuple] = []  # (score, md_file, text)
    q_tokens = set(query.lower().split()) if query else set()

    for md_file in scan_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel = str(md_file.relative_to(output_dir))
        if scope and not rel.startswith(scope) and scope.lower() not in rel.lower():
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _extract_frontmatter_block(text)
        if type_filter and fm.get("type", "") != type_filter:
            continue
        # Score by keyword overlap
        score = sum(1 for t in q_tokens if t in text.lower()[:3000])
        if score > 0 or not q_tokens:
            candidates.append((score, md_file, text))

    candidates.sort(key=lambda x: x[0], reverse=True)

    for score, md_file, text in candidates[:max_results]:
        rel = str(md_file.relative_to(output_dir))
        # Try to extract "Component Constraint Index" section
        index_section = _extract_section(text, "Component Constraint Index")
        if not index_section:
            # Fallback: try "Constraint" or "Business Constraints"
            index_section = _extract_section(text, "Constraint")
        if index_section:
            directories.append({
                "file": rel,
                "title": _extract_frontmatter_block(text).get("title", md_file.stem),
                "index": index_section[:2000],
            })

    result["directories"] = directories
    result["hint"] = (
        "Use mode=detail with page=<file> and section=<heading> to read full details "
        "for a specific component."
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


def _query_mode_detail(
    output_dir: Path,
    page: str,
    section: Optional[str],
) -> str:
    """Mode=detail: return full content of a page or a specific section."""
    if not page:
        return json.dumps({"error": "mode=detail requires 'page' parameter (relative path)."})

    file_path = _resolve_within(output_dir, page)
    if file_path is None:
        return json.dumps({"error": f"Invalid page path: {page}"})
    if not file_path.exists():
        # Try with wiki/ prefix
        from codewiki.src.config import WIKI_DIR
        alt_path = _resolve_within(output_dir, f"{WIKI_DIR}/{page}")
        if alt_path is not None and alt_path.exists():
            file_path = alt_path
        else:
            return json.dumps({"error": f"Page not found: {page}"})

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return json.dumps({"error": f"Cannot read page: {e}"})

    # Strip frontmatter for cleaner output
    fm = _extract_frontmatter_block(text)
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            body = text[end + 3:].strip()

    result: Dict[str, Any] = {
        "mode": "detail",
        "page": page,
        "frontmatter": fm,
    }

    if section:
        section_content = _extract_section(body, section)
        if section_content:
            result["section"] = section
            result["content"] = section_content[:5000]
        else:
            result["error"] = f"Section '{section}' not found in {page}"
            # List available sections as hint
            headings = [
                line.strip().lstrip("#").strip()
                for line in body.splitlines()
                if line.strip().startswith("##")
            ]
            result["available_sections"] = headings[:20]
    else:
        result["content"] = body[:5000]
        if len(body) > 5000:
            result["content_truncated"] = True

    return json.dumps(result, indent=2, ensure_ascii=False)


def handle_query_wiki(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Search across docs and notes using BM25 inverted index.

    Falls back to legacy keyword matching if the BM25 index is unavailable
    and cannot be built (e.g. jieba not installed).
    """
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)

    # Resolve output directory
    od = arguments.get("output_dir")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir)
    else:
        return json.dumps({"error": "output_dir is required."})

    query = arguments.get("query", "")
    if not query:
        return json.dumps({"error": "query is required."})

    scope = arguments.get("scope")  # optional module name or directory prefix
    include_notes = arguments.get("include_notes", True)
    include_sources = arguments.get("include_sources", True)
    include_code_refs = arguments.get("include_code_refs", True)
    max_results = min(20, max(1, arguments.get("max_results", 10)))
    expand_terms = arguments.get("expand_terms")  # optional synonym list
    type_filter = arguments.get("type_filter")  # optional page type filter
    hop = min(3, max(0, arguments.get("hop", 0)))  # graph expansion hops (0-3)
    expand = arguments.get("expand", False)  # return full content instead of snippet
    mode = arguments.get("mode")  # progressive reading: overview | directory | detail

    # --- Progressive reading modes (early return) ---
    if mode == "overview":
        return _query_mode_overview(output_dir, query, scope, type_filter, max_results, session)
    if mode == "directory":
        return _query_mode_directory(output_dir, query, scope, type_filter, max_results, session)
    if mode == "detail":
        page = arguments.get("page", "")
        section = arguments.get("section")
        return _query_mode_detail(output_dir, page, section)

    # Load module tree for component mapping
    module_tree = None
    if session and session.module_tree:
        module_tree = session.module_tree
    else:
        from codewiki.src.config import meta_resolve
        mt_path = Path(meta_resolve(output_dir, "module_tree.json"))
        if mt_path.exists():
            try:
                module_tree = json.loads(mt_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    # --- BM25 search (preferred) ---
    results: List[Dict[str, Any]] = []
    search_method = "bm25"
    try:
        from codewiki.mcp.tools.wiki_search import (
            search as bm25_search,
            build_full_index,
        )
        from codewiki.src.config import SEARCH_INDEX_FILENAME, META_DIR

        # Auto-build index if it doesn't exist yet (SQLite-backed when session available)
        meta_idx = output_dir / META_DIR / SEARCH_INDEX_FILENAME
        root_idx = output_dir / SEARCH_INDEX_FILENAME
        idx_path = meta_idx if meta_idx.exists() else root_idx
        if not idx_path.exists() or session is not None:
            build_full_index(output_dir, session=session)

        raw_results = bm25_search(
            output_dir,
            query,
            scope=scope,
            include_notes=include_notes,
            max_results=max_results,
            expand_terms=expand_terms,
            session=session,
            type_filter=type_filter,
            hop=hop,
        )

        for r in raw_results:
            # Filter by include_sources: skip raw/sources/ entries when disabled
            if not include_sources and r["file"].startswith("raw/sources/"):
                continue

            entry: Dict[str, Any] = {
                "source": r["source"],
                "file": r["file"],
                "title": r["title"],
                "snippet": r["snippet"],
                "relevance_score": r["relevance_score"],
            }
            # Source type annotation (Roadmap 1.4)
            _fpath = r["file"]
            if _fpath.startswith("notes/"):
                entry["source_type"] = "developer_note"
            elif _fpath.startswith("raw/sources/"):
                entry["source_type"] = "ingested_source"
            else:
                entry["source_type"] = "auto_generated"
            # Pass through graph expansion metadata
            if "hop" in r:
                entry["hop"] = r["hop"]
                entry["via"] = r.get("via", "")
            # Pass through related pages from link graph
            if "related" in r:
                entry["related"] = r["related"]
            # Expand mode: return full page content for deeper reading
            if expand:
                file_path = output_dir / r["file"]
                if file_path.exists():
                    try:
                        full_text = file_path.read_text(encoding="utf-8", errors="replace")
                        if "<!-- crosslinks" in full_text:
                            full_text = full_text.split("<!-- crosslinks")[0]
                        entry["content"] = full_text[:3000].strip()
                        if len(full_text) > 3000:
                            entry["content_truncated"] = True
                    except OSError:
                        pass
            if r["source"] == "note":
                # Extract date and status from note frontmatter
                note_path = output_dir / r["file"]
                if note_path.exists():
                    try:
                        nc = note_path.read_text(encoding="utf-8", errors="replace")
                        entry["date"] = _extract_frontmatter(nc, "date") or ""
                        # Roadmap 2.2: knowledge flywheel status filtering
                        note_st = _extract_frontmatter(nc, "status") or "confirmed"
                        if note_st == "rejected":
                            continue  # skip rejected notes entirely
                        if note_st == "candidate":
                            entry["note_status"] = "candidate"
                            entry["title"] = f"[unconfirmed] {entry['title']}"
                        else:
                            entry["note_status"] = "confirmed"
                    except OSError:
                        entry["date"] = ""

            # Map to components
            if include_code_refs and module_tree and r["source"] == "doc":
                mod_comps = _get_module_components(
                    module_tree, Path(r["file"]).stem
                )
                if mod_comps:
                    entry["related_components"] = mod_comps[:10]

            # Lifecycle: downweight superseded pages
            file_path = output_dir / r["file"]
            if file_path.exists():
                try:
                    fc = file_path.read_text(encoding="utf-8", errors="replace")
                    if fc.startswith("---") and "superseded" in fc[:500]:
                        fm_end = fc.find("---", 3)
                        if fm_end > 0 and "status: superseded" in fc[3:fm_end]:
                            entry["superseded"] = True
                            entry["relevance_score"] = round(
                                entry["relevance_score"] * 0.5, 4
                            )
                            # Extract superseded_by if present
                            import re as _re
                            m = _re.search(
                                r"superseded_by:\s*[\"']?(.+?)[\"']?\s*$",
                                fc[3:fm_end], _re.MULTILINE,
                            )
                            if m:
                                entry["superseded_by"] = m.group(1)
                except OSError:
                    pass

            results.append(entry)

    except Exception as e:
        logger.warning("BM25 search failed, falling back to keyword: %s", e)
        search_method = "keyword_fallback"
        results = _legacy_keyword_search(
            output_dir, query, scope, include_notes,
            include_code_refs, max_results, module_tree,
            type_filter=type_filter, include_sources=include_sources,
        )

    # Build context_package summary
    doc_count = sum(1 for r in results if r["source"] == "doc")
    note_count = sum(1 for r in results if r["source"] == "note")
    source_count = sum(1 for r in results if r["source"] == "source")

    parts = []
    if scope:
        parts.append(f"Within scope '{scope}':")
    if type_filter:
        parts.append(f"Type: {type_filter}")
    if doc_count:
        parts.append(f"{doc_count} doc(s)")
    if note_count:
        parts.append(f"{note_count} note(s)")
    if source_count:
        parts.append(f"{source_count} source(s)")
    context_package = " ".join(parts) if parts else "No relevant results found."

    if results:
        top_snippets = [
            f"- [{r['source']}] {r['title']}: {r['snippet'][:100]}"
            for r in results[:5]
        ]
        context_package += "\n" + "\n".join(top_snippets)

    # Extract keywords for the response (informational)
    keywords = _extract_keywords(query)

    return json.dumps({
        "query": query,
        "keywords": keywords,
        "search_method": search_method,
        "results": results,
        "context_package": context_package,
    }, indent=2, ensure_ascii=False)


def _legacy_keyword_search(
    output_dir: Path,
    query: str,
    scope: Optional[str],
    include_notes: bool,
    include_code_refs: bool,
    max_results: int,
    module_tree: Optional[dict],
    type_filter: Optional[str] = None,
    include_sources: bool = True,
) -> List[Dict[str, Any]]:
    """Fallback keyword-based search (original implementation).

    Used when BM25 index is unavailable.
    """
    from codewiki.src.config import NOTES_DIR, RAW_SOURCES_DIR

    keywords = _extract_keywords(query)
    if not keywords:
        return []

    results: List[Dict[str, Any]] = []

    # Determine which source types to include
    allowed_sources: set = set()
    if type_filter:
        if type_filter == "doc":
            allowed_sources = {"doc"}
        elif type_filter == "note":
            allowed_sources = {"note"}
        elif type_filter == "source":
            allowed_sources = {"source"}
        else:
            # page_type filter: map to directory name for doc source matching
            from codewiki.src.config import PAGE_TYPE_DIRS
            dir_name = PAGE_TYPE_DIRS.get(type_filter, type_filter + "s")
            allowed_sources = {"doc"}  # will filter by path prefix below
    else:
        allowed_sources = {"doc"}
        if include_notes:
            allowed_sources.add("note")
        if include_sources:
            allowed_sources.add("source")

    # --- Search docs (recursive: wiki/ subdirs + root level) ---
    from codewiki.src.config import WIKI_SYSTEM_FILES
    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file():
            continue
        if md_file.name in WIKI_SYSTEM_FILES:
            continue
        # Skip notes/ and raw/ directories (handled separately)
        rel_path = str(md_file.relative_to(output_dir))
        if rel_path.startswith("notes/") or rel_path.startswith("raw/"):
            continue
        file_stem = md_file.stem
        # Type filter: if type_filter is a page_type, filter by directory
        if type_filter and type_filter not in ("doc", "note", "source"):
            from codewiki.src.config import PAGE_TYPE_DIRS
            dir_name = PAGE_TYPE_DIRS.get(type_filter, type_filter + "s")
            if f"wiki/{dir_name}/" not in rel_path:
                continue
        if scope:
            # Match by: filename stem, path prefix, or path component (e.g. "modules", "notes")
            scope_norm = scope.lower().replace(" ", "_").rstrip("/")
            path_lower = rel_path.lower().replace("\\", "/")
            if (file_stem.lower() != scope_norm
                    and not path_lower.startswith(scope_norm + "/")
                    and f"/{scope_norm}/" not in f"/{path_lower}"):
                continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if "<!-- crosslinks" in content:
            content = content.split("<!-- crosslinks")[0]

        score, snippet = _score_document(content, keywords)
        if score > 0.05:
            title = _extract_frontmatter(content, "title") or file_stem.replace("_", " ").title()
            entry: Dict[str, Any] = {
                "source": "doc",
                "file": rel_path,
                "title": title,
                "snippet": snippet[:300],
                "relevance_score": score,
            }
            if include_code_refs and module_tree:
                mod_comps = _get_module_components(module_tree, file_stem)
                if mod_comps:
                    entry["related_components"] = mod_comps[:10]
            results.append(entry)

    # --- Search notes ---
    if include_notes and (not type_filter or type_filter == "note"):
        notes_dir = output_dir / NOTES_DIR
        if notes_dir.is_dir():
            for note_file in notes_dir.glob("*.md"):
                if scope:
                    try:
                        note_content = note_file.read_text(encoding="utf-8")
                        if scope.lower() not in note_content.lower():
                            continue
                    except OSError:
                        continue
                try:
                    note_content = note_file.read_text(encoding="utf-8")
                except OSError:
                    continue
                score, snippet = _score_document(note_content, keywords)
                if score > 0.05:
                    note_title = _extract_frontmatter(note_content, "title") or note_file.stem
                    note_date = _extract_frontmatter(note_content, "date") or ""
                    entry = {
                        "source": "note",
                        "file": f"{NOTES_DIR}/{note_file.name}",
                        "title": note_title,
                        "snippet": snippet[:300],
                        "date": note_date,
                        "relevance_score": score,
                    }
                    results.append(entry)

    # --- Search source documents (raw/sources/) ---
    if include_sources and (not type_filter or type_filter == "source"):
        raw_sources_dir = output_dir / RAW_SOURCES_DIR
        if raw_sources_dir.is_dir():
            for src_file in raw_sources_dir.iterdir():
                if not src_file.is_file():
                    continue
                if src_file.suffix not in (".md", ".txt", ".html"):
                    continue
                try:
                    src_content = src_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                score, snippet = _score_document(src_content, keywords)
                if score > 0.05:
                    entry = {
                        "source": "source",
                        "file": f"{RAW_SOURCES_DIR}/{src_file.name}",
                        "title": src_file.stem.replace("_", " ").title(),
                        "snippet": snippet[:300],
                        "relevance_score": score,
                    }
                    results.append(entry)

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:max_results]


def _extract_frontmatter(content: str, key: str) -> Optional[str]:
    """Extract a value from YAML frontmatter."""
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


def _get_module_components(
    module_tree: dict,
    doc_stem: str,
) -> List[str]:
    """Find components for a module by its doc filename stem."""
    target = doc_stem.lower().replace("_", " ")

    def _walk(tree: dict) -> List[str]:
        for name, info in tree.items():
            if name.lower() == target or name.lower().replace(" ", "_") == doc_stem.lower():
                return info.get("components", [])
            children = info.get("children", {})
            if isinstance(children, dict):
                found = _walk(children)
                if found:
                    return found
        return []

    return _walk(module_tree)
