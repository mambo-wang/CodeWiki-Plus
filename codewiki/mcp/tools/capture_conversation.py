"""MCP tool: capture_conversation — store a raw conversation transcript.

capture_conversation is the *ingest* half of the team-memory fusion loop
(spec: SPEC-conversation-to-wiki.md, ticket T1). It accepts a structured
conversation object (turns with role/content), resolves the target
repowiki, and writes it as a markdown file into ``repowiki/raw/``.

Design constraints (must hold):
  - The raw/ staging area is NOT indexed by query_wiki; it is a transient
    holding pen for conversations awaiting async distillation by
    distill_conversation.
  - capture_conversation is synchronous and cheap: it only persists raw
    text. No LLM is involved here.
  - Deduplication is by content hash (sha256) of the transcript so the
    same conversation captured twice does not create two files.
  - link_to (optional) records what wiki object the conversation relates to.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Output directory resolution (mirrors source_ingest.py)
# --------------------------------------------------------------------------- #
def _resolve_output_dir(
    session: Optional[SessionState],
    arguments: Dict[str, Any],
) -> Path:
    """Resolve the repowiki output directory from session or arguments.

    Resolution order:
      1. An active session's ``output_dir`` (a fully-resolved repowiki path).
      2. An explicit ``output_dir`` argument.
      3. ``repo_path``/repowiki fallback.
    """
    if session:
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    if od:
        return Path(od).expanduser().resolve()
    rp = arguments.get("repo_path")
    if rp:
        return Path(rp).expanduser().resolve() / "repowiki"
    raise ValueError(
        "output_dir or repo_path is required (or pass an active session)."
    )


# --------------------------------------------------------------------------- #
# Transcript extraction
# --------------------------------------------------------------------------- #
def _extract_transcript(conversation: Any) -> List[Dict[str, str]]:
    """Normalize the conversation argument into a flat list of turns.

    Accepts either:
      - a list of {"role": ..., "content": ...} dicts, or
      - a dict with a "turns" key containing such a list.

    Returns a list of {"role": str, "content": str}. Missing/invalid items
    are skipped rather than raising, so a partial capture still persists.
    """
    raw_turns: Any = conversation
    if isinstance(conversation, dict):
        raw_turns = conversation.get("turns", [])
    if not isinstance(raw_turns, list):
        return []

    turns: List[Dict[str, str]] = []
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("speaker") or "unknown"
        content = item.get("content") or item.get("message") or item.get("text")
        if content is None:
            continue
        turns.append({"role": str(role), "content": str(content)})
    return turns


def _transcript_text(turns: List[Dict[str, str]]) -> str:
    """Render turns to a plain-text transcript for hashing and fallback body."""
    lines = []
    for t in turns:
        lines.append(f"{t['role']}: {t['content']}")
    return "\n".join(lines)


def _content_hash(turns: List[Dict[str, str]], linked: str) -> str:
    payload = json.dumps(
        {"turns": turns, "link_to": linked},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def handle_capture_conversation(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Persist a raw conversation transcript into repowiki/raw/.

    Arguments:
      - session_id (optional): active session id.
      - output_dir / repo_path (optional): repowiki resolution fallback.
      - conversation (required): list of turns or {"turns": [...]} object.
      - link_to (optional): wiki object id/title this conversation relates to.
      - source_session_id (optional): the IDE-side session id (e.g. CodeBuddy's
        session_id carried by SessionEnd / PreCompact / Stop hook events).
        Distinct from session_id (the active MCP session). Re-capturing the
        same source session replaces its pending raw file instead of piling
        up incremental transcripts.
      - keep_raw (optional, bool, default False): hint for distill_conversation
        to retain the raw file after distillation. Stored as metadata only.

    Returns a JSON status object.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    conversation = arguments.get("conversation")
    if not conversation:
        return json.dumps({"error": "conversation is required (list of turns or {turns: [...]})."})

    turns = _extract_transcript(conversation)
    if not turns:
        return json.dumps({"error": "conversation contained no usable turns."})

    link_to = arguments.get("link_to", "")
    if link_to is None:
        link_to = ""
    link_to = str(link_to)

    keep_raw = bool(arguments.get("keep_raw", False))

    source_session_id = str(arguments.get("source_session_id") or "")

    content_hash = _content_hash(turns, link_to)

    # Ensure repowiki/raw/ exists
    from codewiki.src.config import RAW_DIR
    raw_dir = output_dir / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Deduplicate: skip if a file with the same content hash already exists
    for existing in sorted(raw_dir.glob("conv-*.md")):
        try:
            text = existing.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"content_hash: {content_hash}" in text:
            return json.dumps({
                "status": "duplicate",
                "content_hash": content_hash[:24] + "...",
                "stored_at": str(existing.relative_to(output_dir)),
                "message": "Identical conversation already captured; skipped.",
            }, indent=2, ensure_ascii=False)

    # Session-scoped supersede: Stop fires every turn and PreCompact can fire
    # mid-session, so the same IDE session is captured repeatedly with a
    # growing transcript. Each capture is a superset of the previous one —
    # replace that session's still-pending raw file instead of accumulating
    # incremental copies. Distilled / keep_raw files are left untouched.
    superseded = False
    dest_path: Optional[Path] = None
    if source_session_id:
        for existing in sorted(raw_dir.glob("conv-*.md")):
            try:
                text = existing.read_text(encoding="utf-8")
            except OSError:
                continue
            if f"source_session: {json.dumps(source_session_id, ensure_ascii=False)}" in text \
                    and "status: pending" in text:
                dest_path = existing
                superseded = True
                break

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    if dest_path is None:
        # Build a stable, sortable filename from the timestamp
        safe_link = "".join(c if c.isalnum() else "-" for c in link_to)[:40]
        fname = f"conv-{stamp}{('-' + safe_link) if safe_link else ''}.md"
        dest_path = raw_dir / fname
        # Collision guard (extremely unlikely given second-resolution stamp)
        if dest_path.exists():
            dest_path = raw_dir / f"conv-{stamp}-{int(now.timestamp() * 1000) % 100000}.md"

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        from codewiki.src.config import actor_id
        actor = actor_id()
    except Exception:
        actor = "codewiki"

    body = _transcript_text(turns)
    meta = {
        "captured_at": now_iso,
        "content_hash": content_hash,
        "turn_count": len(turns),
        "link_to": link_to,
        "source_session": source_session_id,
        "keep_raw": keep_raw,
        "status": "pending",  # pending → distilled (T2) → deleted
    }
    fm = (
        "---\n"
        "type: Conversation\n"
        f"title: {json.dumps('conversation ' + stamp, ensure_ascii=False)}\n"
        f"captured_at: {now_iso}\n"
        f"content_hash: {content_hash}\n"
        f"turn_count: {len(turns)}\n"
        f"link_to: {json.dumps(link_to, ensure_ascii=False)}\n"
        f"source_session: {json.dumps(source_session_id, ensure_ascii=False)}\n"
        f"keep_raw: {str(keep_raw).lower()}\n"
        "status: pending\n"
        f"generated: {{ by: {actor}, at: {now_iso} }}\n"
        "---\n\n"
    )
    content = fm + "# Conversation Transcript\n\n" + body + "\n"

    try:
        dest_path.write_text(content, encoding="utf-8")
    except OSError as e:
        return json.dumps({"error": f"Failed to write conversation file: {e}"})

    # NOTE: deliberately no append_log() here. Raw capture is transient (the
    # file is deleted after distillation), and the hook fires on every session
    # end — logging each capture would leave permanent log.md entries pointing
    # at files that no longer exist. Note creation is logged by ingest_note
    # during distillation instead.

    logger.info(
        "%s conversation at %s (%d turns)",
        "Superseded" if superseded else "Captured", dest_path, len(turns),
    )

    return json.dumps({
        "status": "captured",
        "conversation_id": dest_path.stem,
        "stored_at": str(dest_path.relative_to(output_dir)),
        "turn_count": len(turns),
        "content_hash": content_hash[:24] + "...",
        "link_to": link_to,
        "source_session": source_session_id,
        "superseded": superseded,
        "keep_raw": keep_raw,
    }, indent=2, ensure_ascii=False)
