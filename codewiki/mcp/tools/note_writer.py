"""NoteWriter: the deep write interface for repowiki notes (2026-09 #1).

One module behind a small interface for everything that writes a note:
filename slug (CJK hash fallback is the ingest filename convention),
locked frontmatter status rewrite (OKF section-5 verified append and
stale_after renew), and the shared post-write index refresh.
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
logger = logging.getLogger(__name__)


# Legacy CodeWiki status values -> OKF v0.2 lifecycle vocabulary (5.4)
_STATUS_LEGACY_MAP = {
    "candidate": "draft",
    "confirmed": "stable",
    "rejected": "deprecated",
    "superseded": "deprecated",
}


def _norm_status(status: Optional[str]) -> str:
    """Normalize a status value to OKF vocabulary; unknown values pass through."""
    if not status:
        return "draft"
    return _STATUS_LEGACY_MAP.get(str(status).strip().lower(), str(status).strip().lower())


def _okf_actor(by: Optional[str] = None) -> str:
    """Resolve an OKF actor string (§7); defaults to codewiki/<version>."""
    if by:
        return by
    try:
        from codewiki.src.config import actor_id

        return actor_id()
    except Exception:
        return "codewiki"


def _note_source_ref(output_dir: Path, rel_file: str) -> Optional[str]:
    """Return a note's metadata.source_ref (link to its L0 source conversation).

    Link-first L0 provenance (团队记忆融合 §9): search results expose this so
    agents can trace distilled knowledge back to the archived original dialogue
    and read it on demand. Best-effort: any parse/read failure returns None.
    """
    try:
        text = (Path(output_dir) / rel_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end < 0:
        return None
    try:
        import yaml

        fm = yaml.safe_load(text[3:end])
    except Exception:
        return None
    if not isinstance(fm, dict):
        return None
    meta = fm.get("metadata")
    value = None
    if isinstance(meta, dict):
        value = meta.get("source_ref")
    if value is None:
        value = fm.get("source_ref")
    if not value:
        return None
    return str(value).replace("\\", "/")


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




def _apply_status_to_file(
    path: Path,
    output_dir: Path,
    new_status: str,
    reason: str = "",
    verified_by: str = "",
    renew_stale_after: bool = False,
) -> str:
    """Rewrite the ``status`` field in a markdown file's YAML frontmatter.

    OKF v0.2: when *verified_by* is given, a ``verified`` entry
    ``{by, at}`` is appended (§5.2); when *renew_stale_after* is set the
    ``stale_after`` date is reset (re-confirmation re-guarantees freshness,
    §5.5).  Mutations go through a YAML round-trip so list values stay
    well-formed.  Returns a JSON string with key ``doc_file``.
    """
    path = Path(path).expanduser().resolve()
    # Team-layout Phase 2 (§5.3): the whole parse→mutate→rewrite sequence
    # runs under the cross-process sidecar lock — two servers confirming the
    # same note must not interleave (lost verified entry / torn frontmatter).
    from codewiki.src.store import locked

    with locked(path):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            return json.dumps({"error": f"Cannot read document: {e}"})

        if not text.startswith("---"):
            return json.dumps({"error": "Document has no YAML frontmatter."})

        end = text.find("---", 3)
        if end < 0:
            return json.dumps({"error": "Malformed frontmatter."})

        fm_text = text[3:end]
        body = text[end + 3 :]

        try:
            import yaml

            data = yaml.safe_load(fm_text)
            if not isinstance(data, dict):
                raise ValueError("frontmatter is not a mapping")
        except Exception:
            # Fallback: legacy regex status replacement only
            import re as _re

            if _re.search(r"^status:", fm_text, _re.MULTILINE):
                fm_text = _re.sub(
                    r"^status:.*$", f"status: {new_status}", fm_text, flags=_re.MULTILINE
                )
            else:
                fm_text = fm_text.rstrip("\n") + f"\nstatus: {new_status}\n"
            new_text = f"---{fm_text}---{body}"
            from codewiki.src.store import atomic_write

            atomic_write(path, new_text)
            return json.dumps(
                {
                    "status": new_status,
                    "doc_file": str(path.relative_to(output_dir)),
                    "message": f"Document marked as {new_status}.",
                },
                indent=2,
                ensure_ascii=False,
            )

        data["status"] = new_status
        if reason and new_status == "deprecated":
            data["reject_reason"] = reason
        if verified_by:
            verified = data.get("verified")
            if isinstance(verified, dict):
                verified = [verified]  # bare mapping → one-element list (§5.2)
            if not isinstance(verified, list):
                verified = []
            verified.append(
                {
                    "by": verified_by,
                    "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            data["verified"] = verified
        if renew_stale_after:
            try:
                from codewiki.mcp.tools.page_router import load_schema

                _schema = load_schema(str(output_dir))
            except Exception:
                _schema = {}
            # Type-aware renewal (新鲜度机制专项): the note's own ``type`` field
            # selects the window; re-confirmation re-guarantees freshness for a
            # type-appropriate period (OKF §5.5).
            _stale_days = freshness_window_days(data.get("type"), _schema)
            data["stale_after"] = (datetime.now() + timedelta(days=_stale_days)).strftime(
                "%Y-%m-%d"
            )

        import yaml as _yaml

        new_fm = _yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        new_text = f"---\n{new_fm}---{body}"
        from codewiki.src.store import atomic_write

        atomic_write(path, new_text)

    # Update search index
    try:
        from codewiki.mcp.tools.wiki_search import update_file

        update_file(output_dir, path)
    except Exception:
        pass

    msg = f"Document marked as {new_status}."
    if reason:
        msg += f" Reason: {reason}"
    if verified_by:
        msg += f" Verified by {verified_by}."
    return json.dumps(
        {
            "status": new_status,
            "doc_file": str(path.relative_to(output_dir)),
            "message": msg,
        },
        indent=2,
        ensure_ascii=False,
    )


def _update_note_status(
    output_dir: Path,
    note_file: str,
    new_status: str,
    reason: str = "",
    verified_by: str = "",
    renew_stale_after: bool = False,
) -> str:
    """Update the status field in a note's YAML frontmatter.

    Thin wrapper around :func:`_apply_status_to_file` that keeps the
    ``notes/`` prefix resolution and the ``note_file`` response key used by
    ``confirm_note`` / ``reject_note``.
    """
    from codewiki.src.config import NOTES_DIR

    # Normalize once: _resolve_within() returns fully-resolved paths, and on
    # Windows the raw output_dir may use 8.3 short names (e.g. ADMINI~1) or
    # different casing, which would break relative_to() below.
    output_dir = Path(output_dir).expanduser().resolve()

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

    result = json.loads(
        _apply_status_to_file(
            note_path,
            output_dir,
            new_status,
            reason=reason,
            verified_by=verified_by,
            renew_stale_after=renew_stale_after,
        )
    )
    if "error" in result:
        return json.dumps(result, indent=2, ensure_ascii=False)
    # Keep the public response shape: note_file key + note-oriented message.
    result["note_file"] = result.pop("doc_file")
    result["message"] = result["message"].replace("Document", "Note")
    return json.dumps(result, indent=2, ensure_ascii=False)




def refresh_note_indexes(
    output_dir: Path,
    note_path: Path,
    *,
    session=None,
    log_action: Optional[str] = None,
    log_msg: Optional[str] = None,
) -> None:
    """Post-write refresh shared by every note write path.

    appends to the wiki log, rebuilds index.md, and updates the BM25 search
    entry — all best-effort so a refresh failure never blocks the write
    itself. (Extracted from the three copies that used to live inline in
    ingest_note, status changes, and distill dedup actions.)
    """
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log

        if log_action:
            append_log(str(output_dir), log_action, log_msg or "")
        rebuild_index(str(output_dir))
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)
    try:
        from codewiki.mcp.tools.wiki_search import update_file

        update_file(output_dir, note_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)


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
