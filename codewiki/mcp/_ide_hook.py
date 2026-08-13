#!/usr/bin/env python3
"""IDE hook for team-memory fusion (ticket T6).

This is a thin, **synchronous** sink that the CodeBuddy IDE can invoke when a
conversation ends (or is manually flushed). It performs ONLY the *capture* half
of the team-memory fusion loop:

    IDE event  ──►  capture_conversation  ──►  repowiki/raw/conv-*.md

It deliberately does NOT distill. Distillation (the LLM-heavy, async half) is
handled separately by `distill_conversation` run in a background subagent/worker
(see SPEC-conversation-to-wiki.md). The raw/ staging area is transient and is
NOT indexed by query_wiki.

Security / opt-in:
    The hook is OFF by default. The IDE must set the environment variable
    ``CODEWIKI_TEAM_MEMORY_HOOK=1`` (or pass ``--enable``) before invoking this
    script, otherwise it exits immediately with status 0 and does nothing. This
    prevents accidental capture of every session.

Usage:
    # from the IDE, after a conversation finishes:
    python -m codewiki.mcp._ide_hook --conversation /tmp/conv.json \
        --repo-path /abs/path/to/repo
    # or pipe a JSON event on stdin:
    echo '{"repo_path": "...", "conversation": [...], "link_to": "..."}' \
        | CODEWIKI_TEAM_MEMORY_HOOK=1 python -m codewiki.mcp._ide_hook

Stdin payload (a single JSON object):
    {
      "repo_path": "/abs/path/to/repo",      # required for raw/ resolution
      "session_id": "optional-active-session-id",
      "conversation": [                       # list of {role, content} turns
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ],
      "link_to": "optional-wiki-object-id",
      "keep_raw": false
    }

Exit codes:
    0  success (captured or no-op because disabled / empty)
    2  usage / argument error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = None  # lazily imported to keep CLI startup cheap


def _enabled(explicit: bool) -> bool:
    """Hook is enabled only when explicitly requested."""
    if explicit:
        return True
    return os.environ.get("CODEWIKI_TEAM_MEMORY_HOOK", "").strip() == "1"


def _extract_inline_turns(data: Dict[str, Any]) -> Optional[list]:
    """Extract inline conversation turns from common IDE payload keys.

    Some IDEs inline the conversation directly under one of several common keys
    instead of pointing at a transcript file. Returns the turns list if found,
    otherwise None. Only user/assistant dialogue turns are kept; system, tool
    and thinking/reasoning blocks are dropped so the archived raw file stays
    noise-free (capture_conversation also enforces this, but filtering here
    keeps the in-memory payload consistent).
    """
    _KEEP = {"user", "assistant"}
    for key in ("conversation", "messages", "turns",
                "transcript_turns", "chat"):
        val = data.get(key)
        if isinstance(val, list) and val:
            kept = [
                t for t in val
                if isinstance(t, dict) and t.get("role") in _KEEP
            ]
            return kept if kept else val
    return None


def _load_event(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    """Resolve the conversation event payload from --conversation file or stdin."""
    if args.conversation:
        path = args.conversation
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ide-hook: cannot read conversation file {path}: {e}", file=sys.stderr)
            return None
        # allow either a full event object or a bare turns list
        if isinstance(data, list):
            return {"conversation": data}
        if isinstance(data, dict):
            # Mirror the stdin branch: if a transcript path is provided, load it.
            if "transcript_path" in data or "transcript" in data:
                loaded = _load_transcript(
                    data.get("transcript_path") or data.get("transcript"))
                data = dict(data)
                if loaded is not None:
                    data["conversation"] = loaded
                return data
            # Some IDEs inline the conversation directly under one of several
            # common keys instead of pointing at a transcript file. Accept those.
            turns = _extract_inline_turns(data)
            if turns is not None:
                data = dict(data)
                data["conversation"] = turns
            return data
        print("ide-hook: conversation file must be a JSON list or object", file=sys.stderr)
        return None

    # Fall back to stdin (only when it is not a TTY)
    if not sys.stdin.isatty():
        # Read stdin as raw bytes and decode explicitly as UTF-8. Relying on
        # ``sys.stdin.read()`` would use the platform locale codec (e.g. cp936
        # on Chinese Windows), which turns non-ASCII bytes into lone surrogates
        # and later breaks ``write_text(encoding="utf-8")`` for CJK content.
        try:
            stdin_bytes = sys.stdin.buffer.read()
        except AttributeError:  # pragma: no cover - non-buffered stdin
            stdin_bytes = sys.stdin.read().encode("utf-8", "replace")
        raw = stdin_bytes.decode("utf-8", "replace").strip()
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"ide-hook: invalid stdin JSON: {e}", file=sys.stderr)
                return None
            if isinstance(data, list):
                return {"conversation": data}
            if isinstance(data, dict):
                # CodeBuddy/Claude-Code compatible hook events (e.g. SessionEnd)
                # may not contain `conversation` turns directly. If a transcript
                # path is provided we load it; otherwise we keep the raw event
                # and let the caller decide (it cannot synthesize turns).
                if "transcript_path" in data or "transcript" in data:
                    loaded = _load_transcript(data.get("transcript_path")
                                              or data.get("transcript"))
                    data = dict(data)
                    if loaded is not None:
                        data["conversation"] = loaded
                    return data
                # Some IDEs inline the conversation directly under one of several
                # common keys instead of pointing at a transcript file. Accept
                # those so a SessionEnd/Stop/PreCompact event with inline turns
                # still gets captured (rather than silently skipped).
                turns = _extract_inline_turns(data)
                if turns is not None:
                    data = dict(data)
                    data["conversation"] = turns
                return data
            print("ide-hook: stdin payload must be a JSON list or object", file=sys.stderr)
            return None
    return None


# Only keep genuine dialogue turns for knowledge distillation. Anything else
# (tool traffic, system prompt, internal thinking) is noise that bloats raw/
# and dilutes distillation.
_KEEP_ROLES = frozenset({"user", "assistant"})


def _try_expand_codebuddy_index(index_path: Path, messages: list) -> Optional[list]:
    """Expand CodeBuddy index.json format into full message turns.

    CodeBuddy IDE stores conversation transcripts as:
      <session>/index.json          — message metadata (id, role, isComplete)
      <session>/messages/<id>.json  — individual message content

    Only user/assistant dialogue text is kept; tool calls/results, system
    prompt, and reasoning/thinking blocks are dropped. Returns a list of
    {role, content} turns, or None if this isn't a CodeBuddy index or no
    messages could be loaded.
    """
    if not messages:
        return None
    first = messages[0] if isinstance(messages[0], dict) else None
    if first is None or "id" not in first:
        return None
    # Already has inline content — not an index
    if any(k in first for k in ("content", "message", "text")):
        return None
    messages_dir = index_path.parent / "messages"
    if not messages_dir.is_dir():
        return None

    turns: list = []
    for meta in messages:
        if not isinstance(meta, dict):
            continue
        msg_id = meta.get("id")
        if not msg_id:
            continue
        role = meta.get("role", "unknown")
        msg_file = messages_dir / f"{msg_id}.json"
        if not msg_file.is_file():
            continue
        try:
            raw = msg_file.read_text(encoding="utf-8-sig", errors="replace")
            msg_data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(msg_data, dict):
            continue
        role = msg_data.get("role") or role
        # Keep only user/assistant dialogue; drop tool/system/other roles.
        if role not in _KEEP_ROLES:
            continue
        text = _extract_codebuddy_message_text(msg_data)
        if text:
            turns.append({"role": str(role), "content": text})

    return turns or None


def _extract_codebuddy_message_text(msg_data: dict) -> str:
    """Extract readable text from a CodeBuddy message file.

    The ``message`` field is typically a JSON string:
      {"role": ..., "content": [{"type": "text", "text": "..."}, ...]}
    Extracts text from content blocks, skipping tool-call/tool-result noise.
    """
    message_raw = msg_data.get("message")
    content = None

    if isinstance(message_raw, str) and message_raw.strip():
        try:
            parsed = json.loads(message_raw)
            if isinstance(parsed, dict):
                content = parsed.get("content")
        except json.JSONDecodeError:
            return message_raw.strip()
    elif isinstance(message_raw, dict):
        content = message_raw.get("content")

    if content is None:
        content = msg_data.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return _text_from_content_blocks(content)
    return ""


_NOISE_BLOCK_TYPES = frozenset({
    "tool-call", "tool_call", "tool-result", "tool_result",
    "reasoning", "thinking",
})


def _text_from_content_blocks(blocks: list) -> str:
    """Join text from content blocks, skipping tool-call/tool-result/reasoning noise."""
    parts: list = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype in _NOISE_BLOCK_TYPES:
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _load_transcript(path: Optional[str]) -> Optional[list]:
    """Best-effort extraction of {role, content} turns from a transcript file.

    Supports a JSON list of turns, a JSON object with a ``messages``/``conversation``
    key, or a line-delimited JSON log (one JSON object per line). Also handles
    the CodeBuddy IDE transcript format (index.json + messages/ directory).
    Returns None when the path is unusable so the caller can fall back gracefully.
    """
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        print(f"ide-hook: transcript not found: {path}", file=sys.stderr)
        return None
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        print(f"ide-hook: cannot read transcript {path}: {e}", file=sys.stderr)
        return None
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # fall back to line-delimited JSON (one object per line)
        turns: list = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                turns.append(obj)
        return turns or None
    if isinstance(data, list):
        # A bare top-level JSON array is the actual CodeBuddy IDE transcript
        # format (index.json lists message metadata; real content lives in
        # sibling messages/<id>.json files). Try expanding it first; only fall
        # back to returning the array verbatim when it isn't a CodeBuddy index
        # (e.g. a plain list of {role, content} turns).
        expanded = _try_expand_codebuddy_index(p, data)
        if expanded:
            return expanded
        return data
    if isinstance(data, dict):
        # CodeBuddy IDE format: index.json holds message metadata, content lives
        # in sibling messages/<id>.json files. Try expanding first, before the
        # generic inline-turns fallback (which would return metadata-only items).
        messages = data.get("messages") or data.get("conversation")
        if isinstance(messages, list):
            expanded = _try_expand_codebuddy_index(p, messages)
            if expanded:
                return expanded
        turns = _extract_inline_turns(data)
        if turns is not None:
            return turns
    return None


def _cleanup_event_file(path: Optional[str]) -> None:
    """Remove the temporary event file the IDE wrapper created for us.

    The wrapper launches this script as a detached, fire-and-forget background
    process (so the IDE never blocks on capture). It cannot delete the temp
    file itself — it must stay on disk until we've read it. We own cleanup.
    """
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="IDE hook: capture a conversation into repowiki/raw/ (no distillation)."
    )
    parser.add_argument("--enable", action="store_true",
                        help="Enable the hook for this invocation "
                             "(otherwise requires CODEWIKI_TEAM_MEMORY_HOOK=1).")
    parser.add_argument("--conversation", help="Path to a JSON file with the "
                        "conversation payload (list of turns or {turns: [...]}).")
    parser.add_argument("--repo-path", help="Absolute path to the repo "
                        "(used to resolve repowiki/raw/).")
    parser.add_argument("--session-id", help="Active session id (optional).")
    parser.add_argument("--link-to", help="Wiki object id this conversation relates to.")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Hint distill_conversation to retain the raw file.")
    args = parser.parse_args(argv)

    # The wrapper passes the temp event file path via this env var so we can
    # clean it up after detaching (see _cleanup_event_file). --conversation and
    # CODEWIKI_HOOK_EVENT_FILE point at the same file; either may be present.
    event_file_to_clean = os.environ.get("CODEWIKI_HOOK_EVENT_FILE") or args.conversation

    # Opt-in gate: never capture unless explicitly enabled.
    if not _enabled(args.enable):
        print("ide-hook: disabled (set CODEWIKI_TEAM_MEMORY_HOOK=1 or pass --enable).")
        _cleanup_event_file(event_file_to_clean)
        return 0

    event = _load_event(args)
    if event is None:
        print("ide-hook: no conversation payload provided; nothing to capture.")
        _cleanup_event_file(event_file_to_clean)
        return 0

    # Merge CLI args over the payload file/stdin.
    def _pick(key, cli_val):
        if cli_val:
            return cli_val
        return event.get(key)

    conversation = event.get("conversation")
    # A SessionEnd / PreCompact / Stop event may carry a `session_id` but no
    # turns (the IDE does not hand over the full transcript inline). In that
    # case, if a transcript path was not provided either, we cannot synthesize
    # a conversation — but we still persist the event itself as a minimal
    # record (so the hook firing is observable and the real payload shape can
    # be inspected) instead of silently dropping it.
    is_envelope = False
    if not conversation:
        hook_event = event.get("hook_event_name") or event.get("event")
        if hook_event in ("SessionEnd", "Stop", "PreCompact") and "session_id" in event:
            print(f"ide-hook: {hook_event} event has no conversation turns and no "
                  "usable transcript_path; capturing the event envelope only "
                  "(the IDE did not provide an inline transcript).")
            # Fall through: capture the event envelope as a minimal record.
            # NOTE: role must be "user" (not "system") -- capture_conversation
            # drops every role outside {user, assistant} in _extract_transcript,
            # so a system-role envelope would be silently discarded (see
            # test_envelope_does_not_supersede_full_transcript). The envelope
            # body carries no system-injection tags, so stripping is a no-op.
            is_envelope = True
            conversation = [{
                "role": "user",
                "content": (f"[team-memory] {hook_event} hook fired but the IDE "
                            "provided no inline transcript and no readable "
                            "transcript_path. Raw event envelope preserved for "
                            "diagnosis. Event keys: "
                            + ", ".join(sorted(event.keys())) + "."),
            }]
        else:
            print("ide-hook: payload has no 'conversation' turns; nothing to capture.")
            return 0

    arguments: Dict[str, Any] = {
        "conversation": conversation,
        "repo_path": _pick("repo_path", args.repo_path),
        "link_to": _pick("link_to", args.link_to) or "",
        "keep_raw": bool(_pick("keep_raw", args.keep_raw)),
        # IDE-side session id (SessionEnd/PreCompact/Stop events all carry it).
        # capture_conversation uses it for session-scoped supersede dedup: the
        # same session re-captured with a longer transcript replaces its
        # pending raw file instead of piling up incremental copies. Named
        # source_session_id so it never collides with the MCP session_id.
        #
        # IMPORTANT: envelope records (no real transcript) must NOT carry
        # source_session_id. capture_conversation supersede-replaces pending
        # captures sharing the same source_session_id; if the envelope carried
        # it, a later SessionEnd without transcript would overwrite a
        # previously captured full transcript (data loss).
        "source_session_id": (
            "" if is_envelope
            else (_pick("session_id", args.session_id) or "")
        ),
    }
    if not arguments["repo_path"]:
        print("ide-hook: repo_path is required to resolve repowiki/raw/.", file=sys.stderr)
        return 2

    # Import heavy deps only after the opt-in gate passes.
    from codewiki.mcp.session import SessionStore
    from codewiki.mcp.tools.capture_conversation import handle_capture_conversation

    store = SessionStore()
    try:
        result = handle_capture_conversation(arguments, store)
    except Exception as e:  # never crash the IDE on a hook failure
        print(f"ide-hook: capture failed: {e}", file=sys.stderr)
        return 0
    finally:
        # We were launched as a detached background process; the temp event
        # file the wrapper created is our responsibility to remove.
        _cleanup_event_file(event_file_to_clean)

    # Print the result even when it contains non-ASCII (CJK titles from the
    # first user message). On Windows the default console encoding may mangle
    # such output, so reconfigure stdout to UTF-8 when possible.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
