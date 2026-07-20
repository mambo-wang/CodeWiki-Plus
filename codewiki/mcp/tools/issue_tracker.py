"""MCP tool: flag_issue — quality issue tracker for LLM Wiki.

Records documentation quality issues in .meta/issues.json, each with a
stable FNV-1a hash ID derived from issue_type + page_path.  Issues can be
created by lint_wiki, Agent-driven reviews, or manual flagging.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)

# FNV-1a 32-bit constants
_FNV_OFFSET_BASIS = 0x811C9DC5
_FNV_PRIME = 0x01000193


def _fnv1a_32(data: bytes) -> int:
    """Compute FNV-1a 32-bit hash."""
    h = _FNV_OFFSET_BASIS
    for byte in data:
        h ^= byte
        h = (h * _FNV_PRIME) & 0xFFFFFFFF
    return h


def _generate_issue_id(issue_type: str, page_path: str) -> str:
    """Generate a stable FNV-1a hash ID for an issue."""
    key = f"{issue_type}::{page_path}"
    return format(_fnv1a_32(key.encode("utf-8")), "08x")


def _load_issues(output_dir: Path) -> Dict[str, Any]:
    """Load issues.json from .meta/. Returns empty tracker on failure."""
    from codewiki.src.config import ISSUES_FILENAME, meta_resolve
    issues_path = Path(meta_resolve(output_dir, ISSUES_FILENAME))
    if not issues_path.exists():
        return {"issues": {}, "version": 1}
    try:
        data = json.loads(issues_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "issues" in data else {"issues": {}, "version": 1}
    except (json.JSONDecodeError, OSError):
        return {"issues": {}, "version": 1}


def _save_issues(output_dir: Path, tracker: Dict[str, Any]) -> None:
    """Persist issues.json to .meta/."""
    from codewiki.src.config import ISSUES_FILENAME, meta_join
    issues_path = Path(meta_join(output_dir, ISSUES_FILENAME))
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text(
        json.dumps(tracker, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def handle_flag_issue(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Flag a documentation quality issue.

    Creates or updates an entry in .meta/issues.json.  Issues are keyed
    by a stable hash of (issue_type, page_path) so duplicate flags are
    idempotent (the timestamp is updated but the ID stays the same).
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    # Resolve output directory
    if session:
        output_dir = Path(session.output_dir)
    else:
        od = arguments.get("output_dir")
        if not od:
            return json.dumps({"error": "session_id or output_dir is required."})
        output_dir = Path(od).expanduser().resolve()

    # Validate inputs
    issue_type = arguments.get("issue_type")
    if not issue_type:
        return json.dumps({"error": "issue_type is required."})

    valid_types = {
        "orphan_page", "no_outlinks", "missing_aliases",
        "stale_source", "broken_link", "outdated_content",
        "missing_section", "low_coverage", "custom",
    }
    if issue_type not in valid_types:
        logger.warning("Unknown issue_type '%s', treating as 'custom'", issue_type)
        issue_type = "custom"

    page_path = arguments.get("page_path", "")
    description = arguments.get("description", "")
    severity = arguments.get("severity", "warning")

    # Generate stable ID
    issue_id = _generate_issue_id(issue_type, page_path)

    # Load, update, save
    tracker = _load_issues(output_dir)
    now = datetime.now().isoformat()

    is_new = issue_id not in tracker["issues"]
    tracker["issues"][issue_id] = {
        "id": issue_id,
        "issue_type": issue_type,
        "page_path": page_path,
        "description": description,
        "severity": severity,
        "created_at": tracker["issues"].get(issue_id, {}).get("created_at", now),
        "updated_at": now,
        "status": "open",
        "occurrences": tracker["issues"].get(issue_id, {}).get("occurrences", 0) + 1,
    }
    _save_issues(output_dir, tracker)

    # Log the operation
    try:
        from codewiki.mcp.tools.wiki_index import append_log
        action = "新增" if is_new else "更新"
        append_log(str(output_dir), "flag_issue",
                   f"{action}问题: [{issue_type}] {page_path}")
    except Exception:
        pass

    return json.dumps({
        "status": "flagged",
        "issue_id": issue_id,
        "issue_type": issue_type,
        "page_path": page_path,
        "is_new": is_new,
        "total_issues": len(tracker["issues"]),
    }, indent=2, ensure_ascii=False)
