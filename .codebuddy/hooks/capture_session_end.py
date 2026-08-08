#!/usr/bin/env python3
"""CodeBuddy SessionEnd hook wrapper for team-memory fusion (T6).

CodeBuddy invokes this script (absolute path) when a session ends. It receives
the SessionEnd event as JSON on **stdin**:

    {
      "session_id": "...",
      "transcript_path": "/path/to/transcript.txt",   # conversation transcript
      "cwd": "/project/path",
      "hook_event_name": "SessionEnd",
      "reason": "other"
    }

This wrapper resolves the repo path and the conversation transcript, then
delegates to ``codewiki.mcp._ide_hook`` (the capture-only sink) via a
subprocess so the codewiki package is imported with the repo on sys.path.

It deliberately does NOT distill — distillation is a separate background job.
Stdout is emitted in the CodeBuddy-expected ``{continue, systemMessage}`` shape.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # <repo>/.codebuddy/hooks/ -> <repo>


def _read_event() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        # Read raw bytes and decode leniently: PowerShell pipes may prepend one
        # or more UTF-8 BOMs, which would break json.loads.
        raw_bytes = sys.stdin.buffer.read()
        raw = raw_bytes.decode("utf-8-sig", errors="replace")
        raw = raw.lstrip("\ufeff").strip()
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_repo_path(event: dict) -> str:
    """Resolve the repo root, preferring authoritative sources.

    Priority: CODEBUDDY_PROJECT_DIR env var (CodeBuddy-specific) >
    CLAUDE_PROJECT_DIR (compat) > event's cwd > this script's repo location.
    Candidates that don't exist on disk are skipped.
    """
    candidates = [
        os.environ.get("CODEBUDDY_PROJECT_DIR"),
        os.environ.get("CLAUDE_PROJECT_DIR"),
        event.get("cwd"),
        str(REPO),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return str(REPO)


def main() -> int:
    event = _read_event()
    repo_path = _resolve_repo_path(event)

    # Forward the full event (it carries transcript_path) to _ide_hook as a
    # temporary --conversation file so _ide_hook can load the transcript.
    tmp = None
    extra = []
    if event:
        fd, tmp = tempfile.mkstemp(suffix=".json", prefix="tm-hook-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(event, fh)
        extra = ["--conversation", tmp]

    cmd = [
        sys.executable, "-m", "codewiki.mcp._ide_hook",
        "--enable",
        "--repo-path", repo_path,
        *extra,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        system_message = out or err or "team-memory capture finished"
        # Never block the IDE: a non-zero exit from the inner script is treated
        # as a non-blocking warning here.
        print(json.dumps({"continue": True, "systemMessage": system_message}))
        return 0
    except subprocess.TimeoutExpired:
        print(json.dumps({"continue": True,
                          "systemMessage": "team-memory capture timed out"}))
        return 0
    except Exception as e:  # noqa: BLE001 - never crash the IDE hook
        print(json.dumps({"continue": True,
                          "systemMessage": f"team-memory hook error: {e}"}))
        return 0
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
