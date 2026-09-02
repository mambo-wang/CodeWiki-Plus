"""MCP tool: stamp_evidence — attach content-hashed code evidence to a page.

Companion to :mod:`codewiki.src.evidence`.  The agent calls this after writing
or updating a page to bind factual content to ``repo://`` code regions; the
``stale_evidence`` lint check then verifies the recorded hashes on demand.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.src.evidence import hash_resource, make_entry, parse_resource
from codewiki.src.frontmatter import format_frontmatter_value

logger = logging.getLogger(__name__)

_SOURCES_KEY_RE = re.compile(r"(?m)^sources\s*:")


def _resolve_targets(
    arguments: Dict[str, Any], store: SessionStore
) -> Tuple[Optional[Path], Optional[Path]]:
    """Resolve (output_dir, repo_root) following the write_doc_file convention."""
    from codewiki.mcp.tools.workspace_result import resolve_session

    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")

    repo_path: Optional[Path] = None
    if rp:
        p = Path(rp).expanduser()
        repo_path = p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()

    session = resolve_session(arguments, store)

    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    elif repo_path:
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        output_dir = default_output_dir(repo_path)
    else:
        return None, None

    if repo_path is None and session is not None and session.repo_path:
        repo_path = Path(session.repo_path).expanduser().resolve()

    repo_root = repo_path or output_dir.parent
    return output_dir, repo_root


def _read_frontmatter(path: Path) -> Optional[Tuple[Dict[str, Any], str]]:
    """Return (frontmatter_dict, body) for a fenced doc, or None without FM."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end < 0:
        return None
    try:
        import yaml

        data = yaml.safe_load(content[3:end]) or {}
    except Exception:  # noqa: BLE001 - malformed FM is handled by other checks
        return None
    if not isinstance(data, dict):
        return None
    return data, content[end + 3 :]


def _merge_sources(
    path: Path,
    frontmatter: Dict[str, Any],
    body: str,
    entries: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Merge evidence entries into the ``sources`` list (idempotent by ``id``).

    Returns ``{"new": n, "updated": m}``.  Uses a YAML round-trip so
    list-of-mapping values stay well-formed, mirroring source_ingest.

    Team-layout Phase 2 (§5.3): the merge runs as a locked read-modify-write
    — the caller's *frontmatter*/*body* (read outside the lock) are only a
    pre-check; the authoritative parse happens INSIDE the lock so a
    concurrent writer's change is never lost.
    """
    from codewiki.src.store import locked_rmw

    result: Dict[str, int] = {"new": 0, "updated": 0}

    def _merge(text: str) -> Optional[str]:
        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end < 0:
            return None
        try:
            import yaml

            data = yaml.safe_load(text[3:end]) or {}
        except Exception:  # noqa: BLE001 - malformed FM is other checks' concern
            return None
        if not isinstance(data, dict):
            return None

        sources = data.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        if not isinstance(sources, list):
            sources = []
        sources = [s for s in sources if isinstance(s, dict)]

        by_id = {s.get("id"): s for s in sources}
        for entry in entries:
            eid = entry["id"]
            existing = by_id.get(eid)
            if existing is None:
                sources.append(entry)
                by_id[eid] = entry
                result["new"] += 1
            elif existing.get("content_hash") != entry.get("content_hash"):
                existing.update(entry)
                result["updated"] += 1

        data["sources"] = sources
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return f"---\n{new_fm}---{text[end + 3 :]}"

    try:
        locked_rmw(path, _merge)
    except OSError as e:
        logger.warning("evidence merge failed for %s: %s", path, e)
    return result


def append_evidence_block(content: str, entries: List[Dict[str, Any]]) -> str:
    """Surgically append a ``sources:`` block to a doc's frontmatter.

    Used by auto-stamp (write_doc_file): the block is inserted before the
    closing fence without reformatting the rest of the frontmatter.  Returns
    *content* unchanged when the doc has no frontmatter or already declares
    ``sources`` — auto-stamp never clobbers existing/manual evidence.
    """
    if not content.startswith("---") or not entries:
        return content
    end = content.find("---", 3)
    if end < 0:
        return content
    fm = content[3:end]
    if _SOURCES_KEY_RE.search(fm):
        return content

    block_lines = ["sources:"]
    for e in entries:
        block_lines.append(f"- id: {format_frontmatter_value(e['id'])}")
        block_lines.append(f"  resource: {format_frontmatter_value(e['resource'])}")
        block_lines.append(f"  content_hash: {format_frontmatter_value(e['content_hash'])}")
    block = "\n".join(block_lines)

    body = content[end + 3 :]
    new_fm = fm.rstrip("\n") + "\n" + block
    return "---\n" + new_fm + "\n---" + body


def handle_stamp_evidence(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Stamp content-hashed code evidence onto a wiki page's ``sources``.

    Parameters (via *arguments*)
    ----------------------------
    page : str
        Page path relative to output_dir (e.g. ``wiki/modules/auth.md``).
    evidence : list
        Items ``{"resource": "repo://src/x.py#L10-L40"}`` — the resource URI
        (whole file when no ``#L`` range is given).
    output_dir / repo_path : str, optional
        As elsewhere; at least one must resolve.
    """
    page_arg = arguments.get("page")
    if not page_arg:
        return json.dumps(
            {"error": "page (relative to output_dir) is required."}, ensure_ascii=False
        )

    evidence = arguments.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return json.dumps(
            {"error": "evidence must be a non-empty list of {resource: ...}."}, ensure_ascii=False
        )

    output_dir, repo_root = _resolve_targets(arguments, store)
    if output_dir is None:
        return json.dumps({"error": "output_dir or repo_path is required."}, ensure_ascii=False)

    page_path = (output_dir / page_arg).resolve()
    try:
        page_path.relative_to(output_dir.resolve())
    except ValueError:
        return json.dumps({"error": f"page escapes output_dir: {page_arg!r}"}, ensure_ascii=False)
    if not page_path.is_file():
        return json.dumps({"error": f"page not found: {page_arg!r}"}, ensure_ascii=False)

    parsed = _read_frontmatter(page_path)
    if parsed is None:
        return json.dumps({"error": f"page has no frontmatter: {page_arg!r}"}, ensure_ascii=False)
    frontmatter, body = parsed

    entries: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    for item in evidence:
        if not isinstance(item, dict):
            skipped.append({"resource": str(item), "reason": "item is not an object"})
            continue
        resource = item.get("resource")
        if not isinstance(resource, str) or not resource.startswith("repo://"):
            skipped.append({"resource": str(resource), "reason": "not a repo:// resource"})
            continue
        parsed_res = parse_resource(resource)
        if parsed_res is None:
            skipped.append({"resource": resource, "reason": "malformed repo:// resource"})
            continue
        rel, start, end = parsed_res
        content_hash = hash_resource(resource, repo_root)
        if content_hash is None:
            skipped.append({"resource": resource, "reason": f"file not found under {repo_root}"})
            continue
        entries.append(make_entry(rel, start, end, content_hash))

    if not entries:
        return json.dumps(
            {"error": "no valid evidence could be stamped.", "skipped": skipped},
            ensure_ascii=False,
        )

    stats = _merge_sources(page_path, frontmatter, body, entries)

    return json.dumps(
        {
            "page": page_arg,
            "stamped": stats,
            "evidence": [e["resource"] for e in entries],
            "skipped": skipped,
            "hint": (
                "Evidence recorded. Run lint_wiki checks=['stale_evidence'] after "
                "code changes to surface drifted facts; evidence drives review, "
                "not automatic rewrites."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )
