"""ingest_note tool family (split from knowledge_loop.py, 2026-09 #1).

Note creation: module auto-matching, tag extraction, symbol-link
injection, and the handle_ingest_note MCP handler.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.src.frontmatter import parse_frontmatter
from codewiki.src.retrieval import STOPWORDS as _STOPWORDS
from codewiki.mcp.tools.injection_budget import estimate_tokens
from codewiki.mcp.tools.note_freshness import freshness_window_days
from codewiki.mcp.tools.note_writer import _norm_status, _okf_actor, _slugify, refresh_note_indexes
logger = logging.getLogger(__name__)


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
    # 6. Markdown headings (protect entire heading line)
    text = re.sub(r"^(#{1,6}\s+.*)$", _protect, text, flags=re.MULTILINE)

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
    # Reverse order is required: a protected region may be nested inside another
    # (e.g. inline code / link / HTML comment inside a heading, which is protected
    # last). Inner placeholders get a lower index, so restoring them *before* the
    # outer region fails — they are still hidden inside ``protected[outer]`` and
    # won't be present in the text yet. Restoring outer-first puts them back into
    # the text so the next iteration can replace them. Forward order would leave
    # ``\x00PROTxxxx\x00`` NUL residue in the output.
    for i, original in reversed(list(enumerate(protected))):
        text = text.replace(_PLACEHOLDER.format(i), original)

    return text


# ---------------------------------------------------------------------------
#  Freshness windows (新鲜度机制专项 — docs/新鲜度机制设计方案.md)
#
#  Type-aware re-verification windows replace the flat 90-day age check.
#  Fallback chain: conventions.freshness.by_type[type] →
#  freshness.default_window_days → conventions.default_stale_days → 90.
#  Zero new frontmatter fields: only the existing ``stale_after`` is
#  activated (written at ingest/confirm, actually read by lint).
# ---------------------------------------------------------------------------

_FRESHNESS_FALLBACK_WINDOW_DAYS = 90
_FRESHNESS_FALLBACK_RETRIEVAL_DEFER_DAYS = 60



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
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        rp = arguments.get("repo_path")
        if rp:
            from codewiki.mcp.tools.workspace_layout import default_output_dir

            output_dir = default_output_dir(rp)
        else:
            return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    # Layout-aware provenance (ticket 04): notes ingested from a centralized
    # member repo are shared-pool knowledge and carry a repo: source tag.
    from codewiki.mcp.tools.workspace_layout import parse_scope_arg, routing_for_write

    _prov_repo = routing_for_write(
        output_dir, (arguments.get("repo_path") or (session.repo_path if session else None))
    )
    # Explicit scope (ticket 06): omitted → auto-stamp of the writing repo;
    # "global" → product-line note without provenance; list → repos: [...].
    try:
        _scope = parse_scope_arg(arguments.get("scope"))
    except ValueError as e:
        return json.dumps({"error": f"invalid scope: {e}"}, ensure_ascii=False)

    # Silent-global guard: inside a centralized corpus, a note written without
    # a resolvable writing repo is stored as product-line (global) knowledge.
    # routing_for_write() needs repo_path, so "pass only output_dir" silently
    # degrades to global — surface it here instead of leaving lint_wiki's
    # "no repo:/repos: provenance" info as the first signal.
    _prov_warning = None
    if _scope is None and _prov_repo is None:
        from codewiki.mcp.tools.workspace_layout import is_centralized_corpus

        if is_centralized_corpus(output_dir):
            _prov_warning = (
                "No provenance stamped: repo_path is missing, so the writing repo cannot "
                "be determined — this note lands as product-line (global) knowledge. Pass "
                "repo_path (or scope=[<repo>]) to tag it with repo:."
            )

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
    # P1 (team-memory fusion): scene label distilled from conversations — a
    # grouping hint for future L2 consolidation (设计方案 §4.1)。
    scene = str(arguments.get("scene") or "").strip()
    aliases = arguments.get("aliases", [])
    # Roadmap 2.2: knowledge flywheel status
    # OKF v0.2 §5.4: write the spec vocabulary (draft|stable|deprecated);
    # legacy values are accepted and normalized for backward compatibility.
    note_status = _norm_status(arguments.get("status", "draft"))

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

    # Duplicate check — compare body content to avoid knowledge-base noise
    if note_path.exists():
        # Compare body only (frontmatter varies by date/status)
        existing_body = note_path.read_text(encoding="utf-8").split("---\n\n", 1)[-1]
        if existing_body.strip() == content.strip():
            return json.dumps(
                {
                    "status": "already_exists",
                    "path": str(note_path),
                    "message": f"Identical note already exists: {note_path.name}",
                },
                ensure_ascii=False,
            )
        # Different content, same slug — append hash suffix to avoid overwrite
        hash_suffix = hashlib.sha1((title + content[:100]).encode()).hexdigest()[:6]
        filename = f"{today}-{slug}-{hash_suffix}.md"
        note_path = notes_dir / filename

    # Conflict advisory (best-effort, never blocks the write): surface notes
    # that look like the same knowledge so the caller can update/merge instead
    # of silently accumulating a contradictory twin. Without it a corrected
    # conclusion is ingested while the refuted note stays live — and being
    # older and richer in keywords it can out-rank the correction in BM25.
    # Reuses the distillation pipeline's two-stage dedup (single convergence
    # point); that helper does not record retrieval stats, so no usage/heat
    # pollution. Set detect_conflicts=false to skip (e.g. bulk ingest).
    similar_notes: List[Dict[str, Any]] = []
    if arguments.get("detect_conflicts", True):
        try:
            from codewiki.mcp.tools.distill_conversation import _find_conflict_candidates

            similar_notes = _find_conflict_candidates(
                title, content, note_type, output_dir, include_strong=True
            )
        except Exception as e:  # advisory only — never fail an ingest on it
            logger.debug("conflict advisory skipped: %s", e)

    # Build note content with YAML frontmatter
    tags = _extract_tags(title, content, note_type)
    frontmatter_lines = [
        "---",
        f"type: {note_type}",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
    ]
    # LLM Wiki: optional standard fields
    if aliases:
        frontmatter_lines.append(f"aliases: {json.dumps(aliases, ensure_ascii=False)}")
    # OKF §4/§5: producer-private fields fold under ``metadata:`` so the top
    # level only carries OKF-standard keys.  Line-based consumers (wiki_index
    # note date, lint note_clusters) still read them via the indented rows.
    metadata_lines = [f"  date: {today}"]
    # Centralized layout provenance: which member repo produced this note
    # (shared-pool knowledge). "global" omits it; a list writes repos: [...].
    if _scope is None:
        if _prov_repo:
            metadata_lines.append(f"  repo: {json.dumps(_prov_repo, ensure_ascii=False)}")
    elif isinstance(_scope, list):
        metadata_lines.append(f"  repos: {json.dumps(_scope, ensure_ascii=False)}")
    # Task routing: stamp task_id under metadata so query_wiki(task_id=...) and
    # get_task_context can surface task-scoped notes. Omitted for taskless notes.
    task_id = arguments.get("task_id")
    if task_id:
        metadata_lines.append(f"  task_id: {task_id}")
    if related_modules:
        metadata_lines.append(
            f"  related_modules: {json.dumps(related_modules, ensure_ascii=False)}"
        )
    if related_components:
        metadata_lines.append(
            f"  related_components: {json.dumps(related_components, ensure_ascii=False)}"
        )
    if severity:
        metadata_lines.append(f"  severity: {severity}")
    if root_cause:
        metadata_lines.append(f"  root_cause: {json.dumps(root_cause, ensure_ascii=False)}")
    if source_ref:
        metadata_lines.append(f"  source_ref: {json.dumps(source_ref, ensure_ascii=False)}")
    if scene:
        metadata_lines.append(f"  scene: {json.dumps(scene, ensure_ascii=False)}")
    frontmatter_lines.append("metadata:")
    frontmatter_lines.extend(metadata_lines)
    frontmatter_lines.append(f"status: {note_status}")
    # Team-layout Phase 3 (D16): author provenance — data foundation for
    # multi-user governance (adoption stats / promotion later).  Field is
    # written but NEVER gates anyone's edits (write-only, no warning).
    try:
        from codewiki.src.config import user_id

        _author = user_id()
        if _author:
            frontmatter_lines.append(f"author: {_author}")
    except Exception as e:
        logger.debug("author stamp skipped: %s", e)
    # OKF v0.2 §5.2/§5.5: provenance actor + absolute staleness date
    frontmatter_lines.append(
        f"generated: {{ by: {_okf_actor(arguments.get('author'))}, at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} }}"
    )
    # OKF v0.2 §5.5: stale_after from the note's TYPE-AWARE freshness window
    # (新鲜度机制专项: conventions.freshness.by_type → default_window_days →
    # default_stale_days → 90), not the flat default_stale_days.
    try:
        from codewiki.mcp.tools.page_router import load_schema

        _schema = load_schema(str(output_dir))
    except Exception:
        _schema = {}
    _stale_days = freshness_window_days(note_type, _schema)
    frontmatter_lines.append(
        f"stale_after: {(datetime.now() + timedelta(days=_stale_days)).strftime('%Y-%m-%d')}"
    )
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
                extra = len(
                    output_dir.resolve().relative_to(Path(session.repo_path).resolve()).parts
                )
                depth += extra
            except ValueError:
                pass
        linked_content = _inject_symbol_links(
            note_content, output_dir, depth=depth, session=session
        )
        if linked_content != note_content:
            note_content = linked_content
    except Exception as e:
        logger.debug("Symbol linking skipped: %s", e)

    # Team-layout Phase 2 (§5.3): cross-process safe note creation
    from codewiki.src.store import locked_write

    locked_write(note_path, note_content)

    # Post-write refresh through the NoteWriter interface (append_log +
    # rebuild_index + BM25 update_file, best-effort).
    refresh_note_indexes(
        output_dir,
        note_path,
        session=session,
        log_action="ingest_note",
        log_msg=f"添加笔记: {title}",
    )

    result: Dict[str, Any] = {
        "status": "ingested",
        "note_status": note_status,
        "note_path": str(note_path),
        "note_type": note_type,
        "auto_matched_modules": auto_matched,
        "related_modules": related_modules,
        "tags": tags,
    }
    if _prov_warning:
        result["provenance_warning"] = _prov_warning
    # Team-layout Phase 4 first slice (D14): read-only remote-drift advisory,
    # once per process per repo — relayed into the conversation, never blocks.
    try:
        from codewiki.src.git_sync import sync_check

        _sync_advisory = sync_check(output_dir)
        if _sync_advisory:
            result["advisories"] = [_sync_advisory]
    except Exception as e:
        logger.debug("sync_check advisory skipped: %s", e)
    if note_status == "draft":
        result["hint"] = (
            "Note saved with status=draft; query_wiki will show it with an "
            "[unconfirmed] prefix. Call confirm_note(note_file=...) after review "
            "to promote it to verified knowledge."
        )
    if similar_notes:
        result["similar_notes"] = similar_notes
        conflict_hint = (
            f"{len(similar_notes)} existing note(s) look like the same knowledge. "
            "If this note CORRECTS or supersedes one, retire it explicitly — "
            "reject_note(note_file=..., reason=...) or batch_set_status("
            "status='deprecated') with a reason pointing at this note — or merge "
            "them via the 'consolidate' prompt. Leaving both live keeps the "
            "refuted conclusion in the corpus where it can still out-rank this "
            "correction. Only keep both if the knowledge is genuinely distinct."
        )
        result["hint"] = f"{result['hint']} {conflict_hint}" if "hint" in result else conflict_hint
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
#  confirm_note / reject_note (Roadmap 2.2 — knowledge flywheel)
# ---------------------------------------------------------------------------


