"""Content-block tool digestion for conversation capture (skill-creator §9).

Shared by BOTH capture paths so they can never drift apart:

- ``codewiki.mcp.tools.capture_conversation`` (MCP tool, QwenWork protocol)
- ``codewiki.mcp._ide_hook`` (stdlib-only IDE hook, deployed hook wrapper
  runs it via ``python -m codewiki.mcp._ide_hook`` — inside the package
  environment, so sharing this module is safe)

Design (docs/skill-creator需求与设计方案.md §9, issue feedback 2026-09-06):
raw conversations used to drop EVERY tool block as noise. But the
"command → error → fix" pairs, exact flags and version pins carried by tool
calls are exactly the material skills are compiled from — what the capture
layer drops, distillation never recovers.

Two-tier replacement for the old flat noise set:

- Pure noise (internal monologue / system plumbing) is still dropped
  unconditionally.
- ``tool_use`` / ``tool_call`` / ``function_call`` blocks survive as ONE
  compressed line each (tool name + first parameter line, e.g. the bash
  command), in original position — order is the "command → error → fix"
  chain.
- ``tool_result`` / ``function_result`` blocks survive ONLY when they look
  like an error (is_error flag or error fingerprint in the text), as a
  truncated error excerpt.
- Successful results survive too, as a one-line ``[tool-ok: …]`` tail
  excerpt — every tool EXCEPT read-only ones (see ``_READ_ONLY_TOOL_NAMES``;
  a blocklist, so a miss costs one line instead of losing a step).
  Added 2026-09-10: dropping every success meant a procedure that ran clean
  left no trace, so multi-step workflows could never be distilled into
  skills — only their failures could. Kill switch: ``CODEWIKI_RAW_TOOL_DETAIL=0``.

This module is stdlib-only by design (the IDE hook must import it without
the package's third-party deps).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from codewiki.src.secret_redact import redact_secrets

# Tier 1: dropped unconditionally — internal monologue and system plumbing
# carry no reusable operational detail.
PURE_NOISE_BLOCK_TYPES = frozenset(
    {
        "thinking",
        "reasoning",
        "thought",
        "system",
        "system_prompt",
        "context",
    }
)

# Tier 2a: tool invocation blocks → one compressed line each.
# (Both underscore and hyphen spellings: Claude/API uses tool_use,
# CodeBuddy transcripts use tool-call.)
TOOL_CALL_BLOCK_TYPES = frozenset(
    {
        "tool_use",
        "tool_call",
        "tool-call",
        "function_call",
    }
)

# Tier 2b: tool result blocks → kept only as truncated error excerpts.
TOOL_RESULT_BLOCK_TYPES = frozenset(
    {
        "tool_result",
        "tool-result",
        "function_result",
    }
)

# Tier 1b: high-frequency, low-signal EDITING tools — dropped WHOLESALE,
# call line included (not just the result). Their payloads (old_str/new_str)
# are bulk with no procedural signal, they dominate the call count in coding
# sessions, and "what changed" is recoverable from git rather than from a
# transcript. Contrast with _READ_ONLY_TOOL_NAMES (tier 2), which drops only
# the RESULT and keeps the `[tool: …]` line as a step marker.
_LOW_SIGNAL_TOOL_NAMES = frozenset(
    {
        "replace_in_file",
        "edit_file",
        "apply_patch",
        "multi_edit",
        "str_replace",
        "str_replace_editor",
    }
)

# Compressed-line budgets (chars). A tool line that exceeds its budget is
# truncated — the point is recognizability for distillation, not fidelity.
_TOOL_LINE_MAX = 160
_RESULT_ERROR_EXCERPT = 200

# ── Successful-result detail (procedure capture, 2026-09-10) ────────────────
# Success results used to be dropped unconditionally, so raw held only
# "command → error → fix" chains: multi-step procedures that ran clean were
# invisible downstream and could never be compiled into skills.
#
# Now EVERY successful result survives as one tail line. No tool-name
# allowlist and no per-conversation cap: the tool-name namespace is open
# (each host ships its own names, MCP tools carry a server prefix), so any
# frozen allowlist silently misses tools — measured on this repo's own
# archives, all 38 MCP calls (capture/distill/confirm/skill_creator, i.e.
# the workflows we most want to capture) fell outside a hand-written list.
# The only remaining limit is per-line: one tail line, never the payload.
_SUCCESS_LINE_MAX = 120

# Read-only tools whose results are bulky and carry no procedural signal.
# A BLOCKLIST, not an allowlist — deliberately. The tool-name namespace is
# open (each host ships its own names, MCP tools carry a mcp__<server>__
# prefix), so any frozen allowlist silently misses tools; measured on this
# repo's own archives, all 38 MCP calls (capture/distill/confirm/
# skill_creator — the workflows we most want) fell outside a hand-written
# list. A blocklist fails in the safe direction: missing a read-only tool
# costs one 120-char line, while missing an allowlist entry costs the step
# forever.
_READ_ONLY_TOOL_NAMES = frozenset(
    {
        "read", "read_file", "readfile", "read_file", "view", "view_file",
        "view_repo_file", "cat", "show", "open",
        "search", "search_content", "searchcontent", "search_file",
        "searchfile", "grep", "rg", "glob", "find", "codebase_search",
        "list", "list_dir", "listdir", "ls", "tree", "dir",
        "fetch", "web_fetch", "webfetch", "web_search", "websearch",
    }
)


def _is_read_only_tool(name: str) -> bool:
    return (name or "").strip().lower() in _READ_ONLY_TOOL_NAMES

# Runtime escape hatch (a runaway capture still needs a kill switch). Both
# capture paths share this module and the IDE hook cannot read schema.yaml
# (no YAML dep) — an env var is the only carrier both can see.
#   unset / "1" / "on"  → enabled (default)
#   "0" / "off" / "no"  → disabled (legacy: success results dropped)
_ENV_DETAIL = "CODEWIKI_RAW_TOOL_DETAIL"
_OFF_VALUES = frozenset({"0", "off", "false", "no", "none"})


def detail_enabled() -> bool:
    """Whether successful tool results are kept (default: yes)."""
    return (os.environ.get(_ENV_DETAIL) or "").strip().lower() not in _OFF_VALUES

# Error fingerprints for result classification (case-insensitive substring).
_ERROR_FINGERPRINTS = (
    "traceback (most recent call last)",
    "error:",
    "error:",
    "exception",
    "failed",
    "permission denied",
    "not found",
    "exit code",
    "fatal",
)


def _first_param_line(payload: Any) -> str:
    """Extract the most informative single line from a tool-call payload.

    Preference order: ``command`` / ``cmd`` (shell), ``file_path`` /
    ``path`` (fs), ``pattern`` (search), else the compact JSON of the whole
    input. Returns at most one line.
    """
    if not isinstance(payload, dict) or not payload:
        return ""
    for key in ("command", "cmd", "file_path", "path", "pattern", "query", "url"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().splitlines()[0]
    try:
        compact = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""
    return compact


def _looks_like_error(text: str) -> bool:
    lowered = text.lower()
    return any(fp in lowered for fp in _ERROR_FINGERPRINTS)


def _clip(s: str, limit: int) -> str:
    s = s.strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def digest_tool_call_block(block: Dict[str, Any]) -> str:
    """Compress a tool-invocation block into one ``[tool: …]`` line."""
    name = block.get("name") or block.get("toolName") or block.get("tool_name") or "?"
    payload = block.get("input") or block.get("arguments") or block.get("args") or block.get("params")
    detail = _first_param_line(payload)
    line = f"[tool: {name}" + (f" · {detail}" if detail else "") + "]"
    return _clip(line, _TOOL_LINE_MAX)


def digest_tool_result_block(block: Dict[str, Any], tool_name: str = "") -> str:
    """Compress a tool-result block into one line, or '' when unremarkable.

    Errors always survive (the "command → error → fix" chain). Successful
    results survive too as a one-line tail excerpt — enough to show "this
    step ran and completed", which is what procedural skill material needs
    and which used to be thrown away. Except for read-only tools
    (``tool_name``): their output is bulk without procedural signal.
    """
    if block.get("is_error") in (True, "true", 1):
        is_err = True
    else:
        is_err = False
    content = block.get("content") or block.get("text") or block.get("result") or ""
    if isinstance(content, list):
        content = " ".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    if not isinstance(content, str):
        content = str(content) if content else ""
    content = content.strip()
    if not is_err and content and not _looks_like_error(content):
        if not detail_enabled():
            return ""  # kill switch: legacy behaviour
        if _is_read_only_tool(tool_name):
            return ""  # read-only output: bulk without procedural signal
        tail = content.splitlines()[-1].strip() if content else ""
        if not tail:
            return ""
        return _clip(f"[tool-ok: {tail}]", _SUCCESS_LINE_MAX)
    if not content:
        return "[tool-error: <empty>]" if is_err else ""
    excerpt = " ".join(content.split())  # collapse whitespace/newlines
    return _clip(f"[tool-error: {excerpt}]", _TOOL_LINE_MAX + _RESULT_ERROR_EXCERPT)


def _tool_name(block: Dict[str, Any]) -> str:
    return str(
        block.get("name") or block.get("toolName") or block.get("tool_name") or ""
    )


def _is_low_signal_tool(name: str) -> bool:
    return (name or "").strip().lower() in _LOW_SIGNAL_TOOL_NAMES


def classify_block(btype: Any, block: Optional[Dict[str, Any]] = None) -> str:
    """Classify a content-block type: 'noise' | 'tool_call' | 'tool_result' | 'text'.

    Pass *block* to let high-frequency low-signal tools (edits) be classified
    as noise — the name is unavailable from the type alone.
    """
    if btype in PURE_NOISE_BLOCK_TYPES:
        return "noise"
    if btype in TOOL_CALL_BLOCK_TYPES:
        if block and _is_low_signal_tool(_tool_name(block)):
            return "noise"
        return "tool_call"
    if btype in TOOL_RESULT_BLOCK_TYPES:
        return "tool_result"
    return "text"


def digest_blocks(blocks: List[Any]) -> List[str]:
    """Flatten a content-block array to text lines with two-tier tool digestion.

    Order is preserved — the interleaving of text, ``[tool: …]``,
    ``[tool-error: …]`` and ``[tool-ok: …]`` lines IS the command→error→fix
    (and step→step) chain distillation reads.

    Every emitted line passes through ``secret_redact.redact_secrets``: raw
    tool I/O is where commands like ``$env:UV_PUBLISH_TOKEN='pypi-…'`` show
    up, and the archived raw is committed and pushed.
    """
    out: List[str] = []
    last_tool_name = ""
    for block in blocks:
        if isinstance(block, str):
            if block.strip():
                out.append(block.strip())
            continue
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        # Capture the name BEFORE classifying: an edit call is dropped, but
        # its result must be dropped too, and only the name says so.
        if btype in TOOL_CALL_BLOCK_TYPES:
            last_tool_name = _tool_name(block)
        kind = classify_block(btype, block)
        if kind == "noise":
            continue
        if kind == "tool_call":
            out.append(digest_tool_call_block(block))
            continue
        if kind == "tool_result":
            if _is_low_signal_tool(last_tool_name):
                continue  # result of a dropped edit — drop it as well
            line = digest_tool_result_block(block, last_tool_name)
            if line:
                out.append(line)
            continue
        # plain text-ish block
        text = block.get("text")
        if not isinstance(text, str):
            text = block.get("content") if btype is None else None
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return [redact_secrets(line) for line in out]
