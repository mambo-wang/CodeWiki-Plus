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
  truncated error excerpt. Successful results stay dropped.

This module is stdlib-only by design (the IDE hook must import it without
the package's third-party deps).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

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

# Compressed-line budgets (chars). A tool line that exceeds its budget is
# truncated — the point is recognizability for distillation, not fidelity.
_TOOL_LINE_MAX = 160
_RESULT_ERROR_EXCERPT = 200

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


def digest_tool_result_block(block: Dict[str, Any]) -> str:
    """Compress a tool-result block into an error excerpt line, or ''.

    Empty string means "successful / unremarkable — drop entirely".
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
        return ""  # success output stays dropped
    if not content:
        return "[tool-error: <empty>]" if is_err else ""
    excerpt = " ".join(content.split())  # collapse whitespace/newlines
    return _clip(f"[tool-error: {excerpt}]", _TOOL_LINE_MAX + _RESULT_ERROR_EXCERPT)


def classify_block(btype: Any) -> str:
    """Classify a content-block type: 'noise' | 'tool_call' | 'tool_result' | 'text'."""
    if btype in PURE_NOISE_BLOCK_TYPES:
        return "noise"
    if btype in TOOL_CALL_BLOCK_TYPES:
        return "tool_call"
    if btype in TOOL_RESULT_BLOCK_TYPES:
        return "tool_result"
    return "text"


def digest_blocks(blocks: List[Any]) -> List[str]:
    """Flatten a content-block array to text lines with two-tier tool digestion.

    Order is preserved — the interleaving of text, ``[tool: …]`` and
    ``[tool-error: …]`` lines IS the command→error→fix chain distillation
    reads. Returns [] when nothing survives (caller decides the fallback).
    """
    out: List[str] = []
    for block in blocks:
        if isinstance(block, str):
            if block.strip():
                out.append(block.strip())
            continue
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        kind = classify_block(btype)
        if kind == "noise":
            continue
        if kind == "tool_call":
            out.append(digest_tool_call_block(block))
            continue
        if kind == "tool_result":
            line = digest_tool_result_block(block)
            if line:
                out.append(line)
            continue
        # plain text-ish block
        text = block.get("text")
        if not isinstance(text, str):
            text = block.get("content") if btype is None else None
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return out
