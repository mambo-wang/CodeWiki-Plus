"""Note lifecycle tools (split from knowledge_loop.py, 2026-09 #1).

confirm_note / reject_note / batch_set_status: status transitions, doc
inventory iteration, and the aggregation hint.
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
    _apply_status_to_file,
    _norm_status,
    _okf_actor,
    _resolve_within,
    _update_note_status,
)
logger = logging.getLogger(__name__)


def _maybe_attach_aggregation_hint(result_json: str, output_dir: Path, count: int) -> str:
    """P2 (§4.5.2): after a successful confirmation, bump the aggregation
    counters and attach a proactive ``aggregation_hint`` when a threshold is
    crossed. Best-effort — any failure returns the original response so the
    confirmation itself is never affected. The hint only REMINDS: the host
    agent must ask the user before running consolidate_notes.
    """
    try:
        data = json.loads(result_json)
    except (json.JSONDecodeError, TypeError):
        return result_json
    if not isinstance(data, dict) or "error" in data:
        return result_json
    try:
        from codewiki.mcp.tools import aggregation_state as agg

        state = agg.record_confirmations(output_dir, count)
        hint = agg.build_aggregation_hint(output_dir, state)
        if hint is not None:
            data["aggregation_hint"] = hint
            return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:  # counters must never break confirmations
        logger.debug("aggregation hint skipped: %s", e)
    return result_json


def handle_confirm_note(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Confirm a draft note, promoting it to stable (verified) domain knowledge.

    OKF v0.2: appends a ``verified`` entry (``human:<id>`` when ``by`` is
    passed, else ``codewiki/<version>``) and renews ``stale_after``.
    P2: bumps aggregation counters and may attach ``aggregation_hint`` (§4.5.2).
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif rp:
        # Prefer repo_path derivation over the restored session's cached
        # output_dir: find_or_restore() may return a stale/incorrect path that
        # does not match where notes were actually written.
        output_dir = Path(rp).expanduser().resolve() / "repowiki"
    elif session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    note_file = arguments.get("note_file", "")
    if not note_file:
        return json.dumps({"error": "note_file is required (relative path within notes/)."})

    result_json = _update_note_status(
        output_dir,
        note_file,
        "stable",
        verified_by=_okf_actor(arguments.get("by")),
        renew_stale_after=True,
    )
    return _maybe_attach_aggregation_hint(result_json, output_dir, count=1)


def handle_reject_note(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Reject a candidate note, excluding it from future query results."""
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif rp:
        # Prefer repo_path derivation over the restored session's cached
        # output_dir: find_or_restore() may return a stale/incorrect path that
        # does not match where notes were actually written.
        output_dir = Path(rp).expanduser().resolve() / "repowiki"
    elif session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    note_file = arguments.get("note_file", "")
    if not note_file:
        return json.dumps({"error": "note_file is required (relative path within notes/)."})
    reason = arguments.get("reason", "")

    return _update_note_status(output_dir, note_file, "deprecated", reason)


# ---------------------------------------------------------------------------
#  batch_set_status
# ---------------------------------------------------------------------------


def _iter_wiki_docs(output_dir: Path):
    """Yield wiki page files (excluding system files) under *output_dir*."""
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    wiki_dir = Path(output_dir) / WIKI_DIR
    if not wiki_dir.exists():
        return
    for p in sorted(wiki_dir.rglob("*.md")):
        if p.name in WIKI_SYSTEM_FILES:
            continue
        yield p


def _iter_note_docs(output_dir: Path):
    """Yield note files under *output_dir*."""
    from codewiki.src.config import NOTES_DIR

    notes_dir = Path(output_dir) / NOTES_DIR
    if not notes_dir.exists():
        return
    yield from sorted(notes_dir.rglob("*.md"))


def _read_doc_status(path: Path) -> str:
    """Return the normalized OKF status of a markdown doc (default 'draft')."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "draft"
    if not text.startswith("---"):
        return "draft"
    end = text.find("---", 3)
    if end < 0:
        return "draft"
    try:
        import yaml

        data = yaml.safe_load(text[3:end])
        if not isinstance(data, dict):
            return "draft"
        return _norm_status(data.get("status", "draft"))
    except Exception:
        return "draft"


def handle_batch_set_status(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Batch-promote wiki pages and/or notes from draft to stable (OKF v0.2).

    Scans the output directory and rewrites the frontmatter ``status`` field
    of every matching document, appending a ``verified`` event and renewing
    ``stale_after`` exactly like :func:`handle_confirm_note`.  Use this after
    a user confirms a batch of generated pages.
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    if od:
        output_dir = Path(od).expanduser().resolve()
    elif rp:
        output_dir = Path(rp).expanduser().resolve() / "repowiki"
    elif session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        return json.dumps({"error": "output_dir is required (or pass repo_path to derive it)."})

    target = arguments.get("status", "stable") or "stable"
    scope = (arguments.get("scope", "all") or "all").lower()  # all | wiki | notes
    only_draft = bool(arguments.get("only_draft", True))
    dry_run = bool(arguments.get("dry_run", False))
    by = _okf_actor(arguments.get("by"))
    renew = bool(arguments.get("renew_stale_after", True))

    if target not in ("stable", "deprecated"):
        return json.dumps(
            {
                "error": f"Unsupported target status: {target}. Use 'stable' or 'deprecated'.",
            },
            ensure_ascii=False,
        )

    # Collect candidate files per scope
    candidates: List[Path] = []
    if scope in ("all", "wiki"):
        candidates.extend(_iter_wiki_docs(output_dir))
    if scope in ("all", "notes"):
        candidates.extend(_iter_note_docs(output_dir))
    if not candidates:
        return json.dumps(
            {
                "scope": scope,
                "scanned": 0,
                "updated": [],
                "skipped": [],
                "message": "No documents found.",
            },
            ensure_ascii=False,
        )

    updated: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    for path in candidates:
        current = _read_doc_status(path)
        rel = str(path.relative_to(output_dir))
        if only_draft and current != "draft":
            skipped.append({"file": rel, "from": current, "reason": "not draft"})
            continue
        if current == target:
            skipped.append({"file": rel, "from": current, "reason": "already target"})
            continue
        if dry_run:
            updated.append({"file": rel, "from": current, "to": target, "dry_run": True})
            continue
        result = json.loads(
            _apply_status_to_file(
                path,
                output_dir,
                target,
                verified_by=by,
                renew_stale_after=(renew and target == "stable"),
            )
        )
        if "error" in result:
            errors.append({"file": rel, "error": result["error"]})
        else:
            updated.append({"file": result["doc_file"], "from": current, "to": target})

    summary = {
        "target": target,
        "scope": scope,
        "dry_run": dry_run,
        "scanned": len(candidates),
        "updated": len([u for u in updated if not u.get("dry_run")]),
        "previewed": len([u for u in updated if u.get("dry_run")]),
        "skipped": len(skipped),
        "errors": len(errors),
        "verified_by": by,
        "renewed_stale_after": renew and target == "stable",
    }
    msg = (
        "Dry run preview — nothing written. "
        if dry_run
        else f"Batch-completed: {summary['updated']} document(s) promoted to {target}."
    )
    if errors:
        msg += f" {len(errors)} error(s) encountered."
    result_json = json.dumps(
        {
            **summary,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "message": msg,
        },
        indent=2,
        ensure_ascii=False,
    )
    # P2 (§4.5.2): batch confirmations drive the same aggregation counters.
    n_promoted = summary["updated"]
    if target == "stable" and not dry_run and n_promoted > 0:
        result_json = _maybe_attach_aggregation_hint(result_json, output_dir, count=n_promoted)
    return result_json


# ---------------------------------------------------------------------------
#  query_wiki
# ---------------------------------------------------------------------------


