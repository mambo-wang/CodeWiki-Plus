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
        print("ide-hook: conversation file must be a JSON list or object", file=sys.stderr)
        return None

    # Fall back to stdin (only when it is not a TTY)
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
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
                return data
            print("ide-hook: stdin payload must be a JSON list or object", file=sys.stderr)
            return None
    return None


def _load_transcript(path: Optional[str]) -> Optional[list]:
    """Best-effort extraction of {role, content} turns from a transcript file.

    Supports a JSON list of turns, a JSON object with a ``messages``/``conversation``
    key, or a line-delimited JSON log (one JSON object per line). Returns None when
    the path is unusable so the caller can fall back gracefully.
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
        return data
    if isinstance(data, dict):
        for key in ("conversation", "messages", "turns"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return None


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

    # Opt-in gate: never capture unless explicitly enabled.
    if not _enabled(args.enable):
        print("ide-hook: disabled (set CODEWIKI_TEAM_MEMORY_HOOK=1 or pass --enable).")
        return 0

    event = _load_event(args)
    if event is None:
        print("ide-hook: no conversation payload provided; nothing to capture.")
        return 0

    # Merge CLI args over the payload file/stdin.
    def _pick(key, cli_val):
        if cli_val:
            return cli_val
        return event.get(key)

    conversation = event.get("conversation") or _pick("conversation", None)
    # A SessionEnd event may carry a `session_id` but no turns (the IDE does not
    # hand over the full transcript inline). In that case, if a transcript path
    # was not provided either, we cannot synthesize a conversation.
    if not conversation:
        hook_event = event.get("hook_event_name") or event.get("event")
        if hook_event in ("SessionEnd", "Stop") and "session_id" in event:
            print("ide-hook: SessionEnd event has no conversation turns and no "
                  "transcript_path; the IDE does not provide the transcript inline. "
                  "Re-run with --conversation <file> or supply transcript_path.")
            return 0
        print("ide-hook: payload has no 'conversation' turns; nothing to capture.")
        return 0

    arguments: Dict[str, Any] = {
        "conversation": conversation,
        "repo_path": _pick("repo_path", args.repo_path),
        "link_to": _pick("link_to", args.link_to) or "",
        "keep_raw": bool(_pick("keep_raw", args.keep_raw)),
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

    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
