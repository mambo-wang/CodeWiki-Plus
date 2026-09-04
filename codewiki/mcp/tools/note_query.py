"""query_wiki tool family (split from knowledge_loop.py, 2026-09 #1).

The read path: five query modes (overview/directory/detail/check/by_file),
BM25 search with progressive disclosure and cost hints, and the legacy
keyword fallback. Sits on the retrieval kernel and the SearchIndex seam.
"""

from __future__ import annotations

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
from codewiki.mcp.tools.note_writer import (
    _norm_status,
    _note_source_ref,
    _resolve_within,
)
logger = logging.getLogger(__name__)


def _trust_tier(verified) -> str:
    """Derive the OKF v0.2 trust tier from a parsed ``verified`` field (§5.3).

    Returns one of: unverified | machine-confirmed | human-reviewed.
    Accepts a bare mapping or a list of mappings.
    """
    if not verified:
        return "unverified"
    entries = verified if isinstance(verified, list) else [verified]
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("by", "")).startswith("human:"):
            return "human-reviewed"
    return "machine-confirmed"


# ---------------------------------------------------------------------------
#  ingest_note
# ---------------------------------------------------------------------------



def _extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords from a query string."""
    # Basic tokenization: replace brackets then split on whitespace and punctuation
    cleaned = query.replace("[", " ").replace("]", " ")
    tokens = re.split(r"[\s,;:!?。？！，；：" "''（）(){}<>]+", cleaned.lower())
    # Filter stopwords and short tokens
    keywords = [t for t in tokens if t and t not in _STOPWORDS and len(t) >= 2]
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
    """Parse YAML frontmatter into a dict. Returns {} on failure.

    Thin delegation to the frontmatter module's reader (architecture review
    2026-09, candidate #3 read-side consolidation) — one parser instead of
    per-module hand-rolled copies.
    """
    try:
        fm, _ = parse_frontmatter(text)
        return fm if isinstance(fm, dict) else {}
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

    # P3 (§4.4): inject the L3 Project Operating Doctrine + scene navigation.
    # The doctrine is the stable, always-on orientation layer: any agent
    # touching the project starts with its principles; scene blocks stay
    # progressive (navigation only, read on demand).
    doctrine_path = output_dir / WIKI_DIR / "doctrine.md"
    if doctrine_path.is_file():
        try:
            doc_text = doctrine_path.read_text(encoding="utf-8", errors="replace")
            if doc_text.startswith("---"):
                end = doc_text.find("---", 3)
                if end > 0:
                    doc_text = doc_text[end + 3 :]
            result["doctrine"] = doc_text[:1300].strip()
        except OSError:
            pass
    try:
        from codewiki.mcp.tools.note_consolidation import _scan_scenarios

        scenes = sorted(_scan_scenarios(output_dir), key=lambda s: -s["heat"])
        if scenes:
            nav_lines = []
            for sc in scenes:
                heat = "🔥" * min(5, max(1, sc["heat"])) if sc["heat"] else ""
                summary = sc["summary"] or ""
                nav_lines.append(f"- {sc['file']} {heat} — {sc['title']}: {summary}".rstrip(" —:"))
            result["scene_navigation"] = (
                "🗺️ Scene Navigation (work-method scene blocks; read on demand "
                "via view_repo_file):\n" + "\n".join(nav_lines)
            )
    except Exception:
        pass  # doctrine injection must never break overview mode

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
                    ov_text = ov_text[end + 3 :]
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
        pages.append(
            {
                "file": rel,
                "title": fm.get("title", md_file.stem),
                "type": page_type,
                "tags": fm.get("tags", []),
                "description": fm.get("description", "")[:120],
            }
        )

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
            directories.append(
                {
                    "file": rel,
                    "title": _extract_frontmatter_block(text).get("title", md_file.stem),
                    "index": index_section[:2000],
                }
            )

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
            body = text[end + 3 :].strip()

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


def _query_mode_check(
    output_dir: Path,
    query: str,
    scope: Optional[str],
    type_filter: Optional[str],
    session,
    include_notes: bool,
    include_sources: bool,
) -> str:
    """Mode=check: lightweight relevance pre-check.

    Runs a capped BM25 search (top 3, no snippets, no graph expansion) and
    returns a relevance verdict with top scores/titles only — enough for an
    agent to decide whether a full search is worth the tokens. Deliberately
    does NOT record retrieval stats: a pre-check is not a consumption event
    and must not pollute the usage/heat signals (U-line feedback loop).
    """
    results: List[Dict[str, Any]] = []
    try:
        from codewiki.mcp.tools.wiki_search import search as bm25_search
        # R-05 freshness gate (build-if-missing / three-tier stale check)
        # now lives inside wiki_search.search — the seam's single owner.
        raw = bm25_search(
            output_dir,
            query,
            scope=scope,
            include_notes=include_notes,
            max_results=3,
            expand_terms=None,
            session=session,
            type_filter=type_filter,
            hop=0,
        )
        for r in raw:
            # Mirror the main path's include_sources semantics.
            if not include_sources and r["file"].startswith("raw/sources/"):
                continue
            results.append(
                {
                    "file": r["file"],
                    "title": r["title"],
                    "relevance_score": r["relevance_score"],
                }
            )
    except Exception as e:
        logger.warning("check-mode search failed: %s", e)

    top_score = results[0]["relevance_score"] if results else 0.0
    verdict = {
        "mode": "check",
        "relevant": bool(results),
        "top_score": top_score,
        "top_results": results,
        "hint": (
            "relevant=true means at least one doc matched above the BM25 "
            "threshold. Judge strength by top_score; if your key distinguishing "
            "terms do not appear in any returned title, a full search is "
            "unlikely to find the answer — consider contributing the knowledge "
            "via ingest_note instead."
        ),
    }
    return json.dumps(verdict, indent=2, ensure_ascii=False)


def _load_file_knowledge_config(output_dir: Path) -> Dict[str, Any]:
    """P0-2: resolve ``conventions.file_knowledge`` (defaults → overrides)."""
    cfg: Dict[str, Any] = {
        "enabled": True,
        "max_results": 15,
        "stale_check": True,
        "min_module_depth": 1,
    }
    try:
        from codewiki.mcp.tools.page_router import load_schema

        conv = (load_schema(str(output_dir)) or {}).get("conventions") or {}
        raw = conv.get("file_knowledge")
    except Exception:
        raw = None
    if isinstance(raw, dict):
        if raw.get("enabled") is not None:
            cfg["enabled"] = bool(raw.get("enabled"))
        if raw.get("stale_check") is not None:
            cfg["stale_check"] = bool(raw.get("stale_check"))
        for k in ("max_results", "min_module_depth"):
            try:
                v = int(raw.get(k))
                if v > 0:
                    cfg[k] = v
            except (TypeError, ValueError):
                continue
    return cfg


def _last_commit_time(target_path: Path, repo_root: Path) -> Optional[datetime]:
    """P1-4 (ADR-0003): last git commit time of *target_path*, or None.

    Uses ``git log -1 --format=%cI`` — NOT mtime: a fresh clone sets every
    file's mtime to clone time, which would false-positive every note as
    stale. Untracked files / missing git → None (honest "don't know").
    """
    import subprocess

    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(target_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return datetime.fromisoformat(r.stdout.strip().replace("Z", "+00:00"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _file_staleness(
    note_date: str,
    target_path: Path,
    repo_root: Path,
    buffer_days: int = 1,
) -> Optional[bool]:
    """True = the target file has commits newer than the note → possibly stale.

    None is not a failure: untracked file, git unavailable, or note without
    a date all return "don't know" rather than a guess (ADR-0003).
    """
    if not note_date:
        return None
    try:
        note_dt = datetime.fromisoformat(str(note_date).strip())
        if note_dt.tzinfo is None:
            note_dt = note_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    commit_dt = _last_commit_time(target_path, repo_root)
    if commit_dt is None:
        return None
    if commit_dt.tzinfo is None:
        commit_dt = commit_dt.replace(tzinfo=timezone.utc)
    return commit_dt > note_dt + timedelta(days=buffer_days)


def _by_file_specificity(note_fm: dict, path_segments: set, target_path: str) -> int:
    """Specificity score (claude-mem file-context.ts:69-86 idea, CodeWiki basis).

    claude-mem scores "file modified +2 / few files covered +2/+1" off its
    ``files_modified`` observation field. CodeWiki notes express attachment
    via ``metadata.related_modules`` / ``related_components`` / ``files`` —
    so the score grades by match granularity instead: exact file > component
    > module. 0 = no attachment (note excluded from the timeline).
    """
    meta = note_fm.get("metadata") or {}
    mods = {str(m) for m in (meta.get("related_modules") or [])}
    comps = {str(c) for c in (meta.get("related_components") or [])}
    files = {str(f).replace("\\", "/") for f in (meta.get("files") or [])}

    score = 0
    if target_path in files:
        score += 3  # exact hit (v1.5 optional field, P1-2)
    if comps & path_segments:
        score += 2  # component-level hit
    elif mods & path_segments:
        score += 1  # module-level hit
    return score


def _query_mode_by_file(
    output_dir: Path,
    by_file: str,
    query: str,
    session,
) -> str:
    """by_file: file-scoped knowledge timeline (P0-2, claude-mem borrowing).

    Answers "what historical knowledge exists for this file" BEFORE the
    agent reads/edits it: titles + est_tokens + status only, no bodies —
    progressive disclosure layer 1, same discipline as mode=check.
    Scope: notes/ only (v1) — generated wiki pages are machine descriptions
    of code already covered by read_code_components/BM25. Includes draft
    notes (status shown as-is, same口径 as default BM25). Records a
    ``by_file`` telemetry event per returned note but NOT a usage-heat hit
    (pre-check discipline).
    """
    cfg = _load_file_knowledge_config(output_dir)
    if not cfg.get("enabled"):
        return json.dumps(
            {"error": "by_file is disabled (conventions.file_knowledge.enabled=false)."},
            ensure_ascii=False,
        )

    # --- Normalise the target path: '/' separators, repo-root-relative. ---
    od = Path(output_dir)
    target = str(by_file).strip().replace("\\", "/")
    p = Path(target)
    if p.is_absolute():
        for base in (od.resolve().parent, od.resolve()):
            try:
                target = p.resolve().relative_to(base).as_posix()
                break
            except ValueError:
                continue

    # --- Path segment set (module-name matching vocabulary). ---
    parts = [seg for seg in target.split("/") if seg]
    depth = int(cfg.get("min_module_depth", 1))
    if depth > 0 and len(parts) > depth:
        parts = parts[depth:]  # top segment(s) are repo/package noise
    segments: set = set(parts)
    for seg in list(segments):
        stem = seg.rsplit(".", 1)[0] if "." in seg else None
        if stem:
            segments.add(stem)

    # --- Query hard-filter tokens (any-token OR semantics). ---
    q_tokens: List[str] = []
    if query:
        try:
            from codewiki.src.retrieval import tokenize as _tokenize

            q_tokens = _tokenize(query) or [query]
        except Exception:
            q_tokens = [query]

    from codewiki.src.config import NOTES_DIR

    notes_dir = od / NOTES_DIR
    repo_root = od.resolve().parent  # colocated layout: <repo>/repowiki
    entries: List[Dict[str, Any]] = []
    matched_modules: set = set()
    if notes_dir.is_dir():
        for note_file in sorted(notes_dir.glob("*.md")):
            try:
                content = note_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm = _extract_frontmatter_block(content)
            if not fm:
                continue  # corrupt frontmatter: skip this note, keep others
            status = _norm_status(str(fm.get("status") or "stable"))
            if status == "deprecated":
                continue  # same skip rule as the default BM25 path
            meta = fm.get("metadata") or {}
            spec = _by_file_specificity(fm, segments, target)
            if spec <= 0:
                continue
            # Hard keyword filter: entries containing NONE of the query
            # tokens are out (title+content, OR semantics — narrow the file's
            # knowledge range, not a global search).
            if q_tokens:
                haystack = (str(fm.get("title") or "") + "\n" + content).lower()
                if not any(t.lower() in haystack for t in q_tokens):
                    continue
            mods = {str(m) for m in (meta.get("related_modules") or [])}
            matched_modules |= mods & segments
            note_date = str(meta.get("date") or fm.get("date") or "")
            if not note_date:
                gen = fm.get("generated") or {}
                if isinstance(gen, dict):
                    note_date = str(gen.get("at") or "")
            entry: Dict[str, Any] = {
                "date": note_date,
                "file": f"{NOTES_DIR}/{note_file.name}",
                "title": str(fm.get("title") or note_file.stem),
                "type": str(fm.get("type") or ""),
                "status": status,
                "est_tokens": estimate_tokens(len(content)),
                "specificity": spec,
            }
            # P1-4: peer freshness (git last-commit vs note date, ADR-0003).
            if cfg.get("stale_check"):
                entry["possibly_stale"] = _file_staleness(note_date, repo_root / target, repo_root)
            entries.append(entry)

    # Sort: (specificity, date) desc — specificity is by_file's raison d'être.
    entries.sort(key=lambda e: (e["specificity"], e["date"] or ""), reverse=True)
    total = len(entries)
    max_results = int(cfg.get("max_results", 15))
    timeline = entries[:max_results]

    # Telemetry only — no usage-heat hit (pre-check discipline, §2.5 Rev.2).
    for e in timeline:
        try:
            from codewiki.mcp.tools import telemetry

            telemetry.record_by_file(od, e["file"])
        except Exception as exc:
            logger.debug("by_file telemetry skipped: %s", exc)

    total_est = sum(e["est_tokens"] for e in timeline)
    if total:
        hint = (
            f"该文件有 {total} 条历史知识（约 {total_est} tokens）。"
            f"已按特异性返回前 {len(timeline)} 条。"
            "够用即可开始；需要细节用 mode=detail 取单篇全文。"
        )
    else:
        hint = (
            "该文件没有关联的历史知识（notes/ 中无 related_modules 命中）。"
            "可能是知识空白：值得在完成任务后用 ingest_note 沉淀。"
        )

    return json.dumps(
        {
            "query": query or "",
            "by_file": target,
            "matched_modules": sorted(matched_modules),
            "file_knowledge": {
                "total": total,
                "returned": len(timeline),
                "total_est_tokens": total_est,
                "timeline": timeline,
            },
            "hint": hint,
        },
        indent=2,
        ensure_ascii=False,
    )


def _repo_scope_match(output_dir: Path, rel_file: str, repo_name: str) -> bool:
    """True when *rel_file* (relative to output_dir) applies to *repo_name*.

    Centralized-layout scope rule (design doc §7.1 / ticket 05):
    * the repo's modules partition (``wiki/modules/<repo>/...``);
    * shared-pool pages whose provenance includes the repo;
    * pages without provenance (product-line global knowledge).

    Other repos' partitions and other repos' tagged pages are excluded.
    Unreadable pages are kept — hiding knowledge on I/O errors is worse.
    """
    rel = rel_file.replace("\\", "/")
    modules_prefix = "wiki/modules/"
    if rel.startswith(modules_prefix):
        return rel[len(modules_prefix) :].startswith(repo_name + "/")
    try:
        from codewiki.mcp.tools.workspace_layout import read_provenance

        page = output_dir / rel_file
        with open(page, encoding="utf-8", errors="replace") as f:
            head = f.read(16384)  # frontmatter lives at the top
        prov = read_provenance(head)
    except OSError:
        return True
    return (not prov) or (repo_name in prov)


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
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        # Fallback: derive from repo_path if available. Layout-aware
        # (ticket 05): a centralized-workspace member queries the workspace
        # knowledge base (one hop); everything else keeps <repo>/repowiki.
        rp = arguments.get("repo_path")
        if rp:
            from codewiki.mcp.tools.workspace_layout import default_output_dir

            output_dir = default_output_dir(rp)
        else:
            return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    query = arguments.get("query", "")
    mode = arguments.get("mode")  # progressive reading: overview | directory | detail
    # P0-2: file-scoped knowledge timeline — a filter dimension alongside
    # scope/type_filter, not a mode (it composes with query as a hard filter).
    by_file = (arguments.get("by_file") or "").strip() or None
    # Progressive reading modes are orientation, not keyword search — query
    # stays optional there (P3: overview mode is the doctrine injection entry).
    # by_file likewise carries its own entry key.
    if not query and not by_file and mode not in ("overview", "directory", "detail"):
        return json.dumps({"error": "query is required (or pass by_file)."})

    scope = arguments.get("scope")  # optional module name or directory prefix
    include_notes = arguments.get("include_notes", True)
    include_sources = arguments.get("include_sources", True)
    include_code_refs = arguments.get("include_code_refs", True)
    max_results = min(20, max(1, arguments.get("max_results", 10)))
    expand_terms = arguments.get("expand_terms")  # optional synonym list
    type_filter = arguments.get("type_filter")  # optional page type filter
    hop = min(3, max(0, arguments.get("hop", 0)))  # graph expansion hops (0-3)
    expand = arguments.get("expand", False)  # return full content instead of snippet
    # Content budget for expand mode (default 3000 keeps legacy behaviour;
    # agents may raise it up to 20000 for full-page deep reading).
    max_chars = min(20000, max(500, int(arguments.get("max_chars", 3000))))
    # T5: team-memory fusion — distinguish distilled notes from LLM-generated ones
    origin_filter = arguments.get("origin_filter")  # optional: "conversation" | "generated" | "any"
    # Task routing: restrict results to notes stamped with a given task_id.
    # Never validates task existence (ghost task_id is allowed post-delete).
    task_id_filter = arguments.get("task_id")
    # Centralized-layout scope filter (ticket 05): repo=<name> narrows results
    # to "knowledge applicable to that repo" = its modules partition +
    # shared-pool pages tagged with it + untagged (global) pages. Combined
    # with an explicit output_dir, the filter applies WITHIN that corpus
    # (output_dir picks the corpus, repo= narrows inside it).
    repo_filter = (arguments.get("repo") or "").strip() or None
    # The repo= scope filter is centralized-layout semantics: inert outside a
    # centralized corpus (registry contract), so single-repo and colocated
    # queries are never disturbed by it.
    repo_filter_active = False
    if repo_filter:
        from codewiki.mcp.tools.workspace_layout import is_centralized_corpus

        repo_filter_active = is_centralized_corpus(output_dir)
    # Over-fetch before filtering so a selective scope can still fill
    # max_results.
    search_budget = min(60, max_results * 3) if repo_filter_active else max_results

    # --- Progressive reading modes (early return) ---
    if mode == "overview":
        return _query_mode_overview(output_dir, query, scope, type_filter, max_results, session)
    if mode == "directory":
        return _query_mode_directory(output_dir, query, scope, type_filter, max_results, session)
    if mode == "detail":
        page = arguments.get("page", "")
        section = arguments.get("section")
        return _query_mode_detail(output_dir, page, section)
    if mode == "check":
        # Lightweight relevance pre-check: top score + titles only, no
        # snippets, no retrieval-stats recording (a pre-check is not a real
        # consumption event and must not pollute usage/heat signals).
        return _query_mode_check(
            output_dir, query, scope, type_filter, session, include_notes, include_sources
        )

    # P0-2: by_file — file-scoped knowledge timeline. Priority: the mode
    # early-return branches above win; by_file serves the default search
    # path only (composes with query as a hard filter, never with modes).
    if by_file:
        return _query_mode_by_file(output_dir, by_file, query, session)

    # P0-1 (claude-mem borrowing): retrieval-cost visibility. _cpt (chars per
    # token) threads est_tokens through every result entry; expand_hint gates
    # the response-level cost_hint. None/False = legacy behaviour.
    _cpt: Optional[int] = None
    _rc_expand_hint = False
    try:
        from codewiki.mcp.tools.injection_budget import load_retrieval_cost
        from codewiki.mcp.tools.page_router import load_schema as _ls_rc

        _rc = load_retrieval_cost(_ls_rc(str(output_dir)))
        if _rc.get("enabled"):
            _cpt = int(_rc.get("chars_per_token") or 4)
            _rc_expand_hint = bool(_rc.get("expand_hint"))
    except Exception as e:
        logger.debug("retrieval_cost config skipped: %s", e)

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
    coverage = None  # T1: corpus-level query-token coverage (BM25 path only)
    try:
        from codewiki.mcp.tools.wiki_search import search as bm25_search
        # R-05 freshness gate (build-if-missing / three-tier stale check)
        # now lives inside wiki_search.search — the seam's single owner.
        raw_results = bm25_search(
            output_dir,
            query,
            scope=scope,
            include_notes=include_notes,
            max_results=search_budget,
            expand_terms=expand_terms,
            session=session,
            type_filter=type_filter,
            hop=hop,
            chars_per_token=_cpt or 0,  # P0-1: single source of truth = handler
        )

        # T1 (检索透明化): corpus-level coverage of the query tokens. If the
        # query's key distinguishing terms are all in `missing`, results are
        # topically adjacent rather than answers — the caller must judge,
        # scores alone cannot express it.
        try:
            from codewiki.mcp.tools.wiki_search import query_coverage

            coverage = query_coverage(output_dir, query, expand_terms=expand_terms, session=session)
        except Exception as e:
            logger.debug("query_coverage unavailable: %s", e)
            coverage = None

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
            # T1: per-doc matched tokens + U1: usage signals — pass through.
            if r.get("matched_tokens"):
                entry["matched_tokens"] = r["matched_tokens"]
            if r.get("usage") is not None:
                entry["usage"] = r["usage"]
            # P0-1: est_tokens pass-through (cost of expanding in full).
            if r.get("est_tokens") is not None:
                entry["est_tokens"] = r["est_tokens"]
            # Source type annotation (Roadmap 1.4)
            _fpath = r["file"]
            if _fpath.startswith("notes/"):
                entry["source_type"] = "developer_note"
                # L0 link-first provenance (团队记忆融合 §9): surface the link to
                # the archived source conversation so agents can trace a note
                # back to the original dialogue on demand (view_repo_file).
                _sref = _note_source_ref(output_dir, _fpath)
                if _sref:
                    entry["source_ref"] = _sref
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
                        entry["content"] = full_text[:max_chars].strip()
                        # P0-1: est_tokens = full-page cost (uniform semantics
                        # across expand/non-expand), content_tokens = what this
                        # response actually returned.
                        try:
                            from codewiki.mcp.tools.injection_budget import (
                                estimate_tokens as _est_tk,
                            )

                            entry["est_tokens"] = _est_tk(len(full_text), _cpt)
                            entry["content_tokens"] = _est_tk(len(entry["content"]), _cpt)
                        except Exception:
                            pass
                        if len(full_text) > max_chars:
                            entry["content_truncated"] = True
                            entry["content_budget"] = max_chars
                    except OSError:
                        pass
            if r["source"] == "note":
                # Extract date and status from note frontmatter
                note_path = output_dir / r["file"]
                if note_path.exists():
                    try:
                        nc = note_path.read_text(encoding="utf-8", errors="replace")
                        entry["date"] = _extract_frontmatter(nc, "date") or ""
                        # OKF v0.2: accept legacy + spec status vocabularies
                        note_st = _norm_status(_extract_frontmatter(nc, "status") or "stable")
                        if note_st == "deprecated":
                            continue  # skip deprecated/rejected notes entirely
                        if note_st == "draft":
                            entry["note_status"] = "draft"
                            entry["title"] = f"[unconfirmed] {entry['title']}"
                        else:
                            entry["note_status"] = "stable"
                        # OKF v0.2 §5.3: derive trust tier from verified
                        try:
                            fm_block = _extract_frontmatter_block(nc)
                            entry["trust_tier"] = _trust_tier(
                                fm_block.get("verified") if fm_block else None
                            )
                        except Exception:
                            pass
                        # T5: tag distilled notes so callers can tell them apart
                        # from LLM-generated notes. Defaults to "generated".
                        entry["origin"] = _extract_frontmatter(nc, "origin") or "generated"
                        # Task routing: surface the bound task_id (empty when none).
                        entry["task_id"] = _extract_frontmatter(nc, "task_id") or ""
                    except OSError:
                        entry["date"] = ""

            # Map to components
            if include_code_refs and module_tree and r["source"] == "doc":
                mod_comps = _get_module_components(module_tree, Path(r["file"]).stem)
                if mod_comps:
                    entry["related_components"] = mod_comps[:10]

            # Lifecycle: downweight superseded pages
            file_path = output_dir / r["file"]
            if file_path.exists():
                try:
                    fc = file_path.read_text(encoding="utf-8", errors="replace")
                    if fc.startswith("---") and (
                        "superseded" in fc[:500] or "deprecated" in fc[:500]
                    ):
                        fm_end = fc.find("---", 3)
                        if fm_end > 0 and (
                            "status: superseded" in fc[3:fm_end]
                            or "status: deprecated" in fc[3:fm_end]
                        ):
                            entry["superseded"] = True
                            entry["relevance_score"] = round(entry["relevance_score"] * 0.5, 4)
                            # Extract superseded_by if present
                            import re as _re

                            m = _re.search(
                                r"superseded_by:\s*[\"']?(.+?)[\"']?\s*$",
                                fc[3:fm_end],
                                _re.MULTILINE,
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
            output_dir,
            query,
            scope,
            include_notes,
            include_code_refs,
            search_budget,
            module_tree,
            type_filter=type_filter,
            include_sources=include_sources,
        )

    # Centralized-layout repo scope filter (ticket 05), applied uniformly to
    # BM25 and legacy-fallback results: keep the repo's modules partition,
    # shared pages tagged with it, and untagged global pages; then trim the
    # over-fetched candidates back to max_results.
    if repo_filter_active:
        results = [
            r for r in results if _repo_scope_match(output_dir, r.get("file", ""), repo_filter)
        ]
        results = results[:max_results]

    # T5: team-memory fusion — ensure every note carries an `origin` so callers
    # can tell distilled notes apart from LLM-generated ones, and optionally
    # restrict results to a single origin.
    for _r in results:
        if _r.get("source") == "note" and "origin" not in _r:
            _np = output_dir / _r.get("file", "")
            if _np.exists():
                try:
                    _nc = _np.read_text(encoding="utf-8", errors="replace")
                    _r["origin"] = _extract_frontmatter(_nc, "origin") or "generated"
                except OSError:
                    _r["origin"] = "generated"
            else:
                _r["origin"] = "generated"
    if origin_filter:
        wanted = origin_filter.lower()
        results = [
            r
            for r in results
            if r.get("source") != "note" or r.get("origin", "generated") == wanted
        ]
    # Task routing filter: only notes with a matching task_id pass. Non-note
    # results (docs/sources) are left intact — task filtering is note-scoped.
    if task_id_filter:
        wanted_task = str(task_id_filter).strip()
        results = [
            r for r in results if r.get("source") != "note" or r.get("task_id", "") == wanted_task
        ]

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
            f"- [{r['source']}] {r['title']}: {r['snippet'][:100]}" for r in results[:5]
        ]
        context_package += "\n" + "\n".join(top_snippets)

    # Extract keywords for the response (informational)
    keywords = _extract_keywords(query)

    # V2 (injection budget): degrade snippets beyond the configured character
    # budget to one-line pointers (file/score/description). 0 = off (legacy
    # behaviour). Failures must never break the search path.
    degraded_count = 0
    try:
        from codewiki.mcp.tools.page_router import load_schema as _ls
        from codewiki.mcp.tools.injection_budget import apply_snippet_budget

        degraded_count = apply_snippet_budget(results, output_dir, _ls(str(output_dir)))
    except Exception as e:
        logger.debug("injection budget skipped: %s", e)

    # Record retrieval stats (which files were hit by this query)
    _record_retrieval_stats(output_dir, query, results)

    # P0-1: response-level cost hint — the layer claude-mem does not have.
    # Turns expand from a blind guess into a budgeted decision.
    cost_hint = None
    if _cpt and _rc_expand_hint and results:
        try:
            from codewiki.mcp.tools.injection_budget import estimate_tokens as _est_tk

            _ests = [int(r.get("est_tokens") or 0) for r in results]
            _expand_all = sum(_ests)
            _top3 = sum(_ests[:3])
            _index_tokens = _est_tk(len(json.dumps(results, ensure_ascii=False)), _cpt)
            if _expand_all:
                cost_hint = {
                    "index_tokens": _index_tokens,
                    "expand_all_tokens": _expand_all,
                    "top3_tokens": _top3,
                    "hint": (
                        f"索引已返回 {len(results)} 条（约 {_index_tokens} tokens）。"
                        f"展开前 3 条约 {_top3} tokens，全部展开约 {_expand_all} tokens。"
                        "建议先按 est_tokens 挑最相关的再 expand。"
                    ),
                }
        except Exception as e:
            logger.debug("cost_hint skipped: %s", e)
            cost_hint = None

    return json.dumps(
        {
            "query": query,
            "keywords": keywords,
            "search_method": search_method,
            **({"repo_filter": repo_filter} if repo_filter_active else {}),
            **({"query_coverage": coverage} if coverage else {}),
            **({"budget_degraded": degraded_count} if degraded_count else {}),
            **({"cost_hint": cost_hint} if cost_hint else {}),
            "results": results,
            "context_package": context_package,
            # P1 A-line: adoption convention reminder — a lower-bound usefulness
            # signal. Agents that actually use a result should declare it.
            "adoption_hint": (
                "If you actually used any result above, include this single-line "
                "comment in your final reply (paths exactly as returned): "
                '<!-- codewiki:referenced-docs: ["<file>", ...] -->. '
                "Declared docs earn adoption credit which boosts their future "
                "ranking (usage.adopted_count)."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )


# ------------------------------------------------------------------
#  Retrieval statistics (T2: per-user telemetry event stream)
# ------------------------------------------------------------------


def _record_retrieval_stats(output_dir: Path, query: str, results: List[Dict[str, Any]]) -> None:
    """Record which files were returned by a query_wiki call.

    T2 (docs/团队知识库支持优化设计方案.md §4.2): the SQLite
    retrieval_stats table is retired; each hit appends (or same-day-merges)
    one event line into ``.meta/telemetry/<user_id>.jsonl`` via
    ``telemetry.record_hit``. Aggregation is a pure in-memory fold
    (``telemetry.aggregate_usage``) consumed by the usage-heat ranking,
    lint checks and wiki_stats.

    Called on every query_wiki invocation; failures are logged and
    swallowed so stats never break the search path.
    """
    if not results:
        return
    try:
        from codewiki.mcp.tools import telemetry

        for r in results:
            # Prefer 'file' field (relative path); fall back to 'title'
            file_path = r.get("file") or r.get("title") or r.get("path", "")
            if not file_path:
                continue
            telemetry.record_hit(output_dir, str(file_path))
    except Exception as e:
        logger.debug("Failed to record retrieval stats: %s", e)



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
            if (
                file_stem.lower() != scope_norm
                and not path_lower.startswith(scope_norm + "/")
                and f"/{scope_norm}/" not in f"/{path_lower}"
            ):
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
    """Extract a value from YAML frontmatter (top-level first, then metadata).

    Delegates to the shared store parser — json-decoded values, so no quote
    drift. Returns None when the document has no fence or the key is absent.
    """
    if not content or not content.startswith("---"):
        return None
    fm, _ = parse_frontmatter(content)
    v = fm.get(key)
    if v is None and isinstance(fm.get("metadata"), dict):
        v = fm["metadata"].get(key)
    if v is None or v == "":
        return None
    return v if isinstance(v, str) else str(v)


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
