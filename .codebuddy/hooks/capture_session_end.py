#!/usr/bin/env python3
"""CodeBuddy session hook wrapper for team-memory fusion (T6).

Registered in ``.codebuddy/settings.json`` for THREE events, all pointing at
this one script (it is event-agnostic — it forwards whatever it receives):

  - ``SessionEnd``  (matcher "other", the only reason currently supported):
    the session is over — final, complete transcript.
  - ``PreCompact``  (matcher "*", i.e. both manual and auto triggers):
    context is about to be compacted — checkpoint the full transcript before
    compaction dilutes it. Rare (long sessions only).
  - ``Stop``        (no matcher — fires after every agent response):
    crash insurance. capture_conversation supersedes the same session's
    pending raw file on each capture, so this per-turn fire does NOT
    accumulate incremental transcripts — only the latest one is kept.

CodeBuddy invokes this script (absolute path) and passes the event as JSON on
**stdin**, e.g. for SessionEnd:

    {
      "session_id": "...",
      "transcript_path": "/path/to/transcript.txt",   # conversation transcript
      "cwd": "/project/path",
      "hook_event_name": "SessionEnd",
      "reason": "other"
    }

PreCompact additionally carries ``trigger`` / ``custom_instructions``; Stop
carries ``stop_hook_active``. All three carry ``session_id`` +
``transcript_path``, which is all the capture path needs.

This wrapper resolves the repo path and the conversation transcript, then
delegates to ``codewiki.mcp._ide_hook`` (the capture-only sink) via a
subprocess so the codewiki package is imported with the repo on sys.path.

Requirements: the ``codewiki`` package must be importable by this hook's
python — either pip-installed, or this hook lives inside a CodeWiki source
checkout, or ``$CODEWIKI_HOME`` points at one. Otherwise the wrapper returns
an actionable systemMessage and skips capture (it never blocks the IDE).

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


def _codewiki_launch_env():
    """Resolve how the subprocess will import the ``codewiki`` package.

    Returns ``(env, error)``. ``env`` extends ``os.environ`` (adding
    ``$CODEWIKI_HOME`` to PYTHONPATH when that fallback is used); ``error`` is
    a human-actionable message when no import path exists.

    Importability order (mirrors how ``python -m codewiki.mcp._ide_hook``
    resolves when run with cwd=REPO):
      1. ``codewiki`` installed in this interpreter (pip) — find_spec sees it.
      2. This hook lives inside a CodeWiki source checkout (``REPO/codewiki/``
         exists) — the subprocess runs with cwd=REPO, and ``-m`` puts cwd on
         sys.path, so the local package is importable without installation.
      3. ``$CODEWIKI_HOME`` points at a CodeWiki source checkout — the hook was
         copied into another project, so we add the checkout to PYTHONPATH.

    Without one of these the inner ``python -m`` would fail with an unhelpful
    ModuleNotFoundError buried in systemMessage; detect it up front instead.
    """
    import importlib.util

    if importlib.util.find_spec("codewiki") is not None:
        return dict(os.environ), ""
    if (REPO / "codewiki" / "__init__.py").is_file():
        return dict(os.environ), ""
    home = os.environ.get("CODEWIKI_HOME", "").strip()
    if home and (Path(home) / "codewiki" / "__init__.py").is_file():
        env = dict(os.environ)
        old = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = home + (os.pathsep + old if old else "")
        return env, ""
    return dict(os.environ), (
        "team-memory capture skipped: the 'codewiki' package is not importable "
        "by this hook's python. Install it (pip install codewiki-plus), keep "
        "this hook inside a CodeWiki checkout, or set CODEWIKI_HOME to a "
        "CodeWiki source checkout directory."
    )


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

    env, import_err = _codewiki_launch_env()
    if import_err:
        # Non-blocking: the IDE session still ends cleanly, but the user gets
        # an actionable hint instead of a silent no-capture.
        print(json.dumps({"continue": True, "systemMessage": import_err}))
        return 0

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
            env=env,
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
