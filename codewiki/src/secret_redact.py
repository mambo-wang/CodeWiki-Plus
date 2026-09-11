# -*- coding: utf-8 -*-
"""Secret redaction for captured text.

Why this exists
---------------
Captured conversations are archived under ``repowiki/`` — an asset that is
committed and pushed (``git_sync``). Anything a user ever typed or ran lands
there verbatim, including shell history like::

    $env:UV_PUBLISH_TOKEN='pypi-AgEI…'

On 2026-09-11 a real PyPI token took exactly that path into
``repowiki/conversations/`` and reached the public remote
(``bbc10f9``); the push was only stopped by GitHub's push protection.
Redaction therefore belongs on the **write** side, before any text is
archived — not on the push side, where it is already too late.

Scope (deliberately narrow)
---------------------------
Only unambiguous shapes are matched: vendor-specific token prefixes and
environment assignments whose variable name says it holds a secret. There is
no entropy heuristic and no attempt to catch "looks random" strings — a
redactor that guesses too much silently destroys the operational detail
(flags, version pins, paths) that skills are compiled from.

Contract
--------
- stdlib-only: the IDE hook (``codewiki.mcp._ide_hook``) imports it inside the
  package environment but must not pull third-party deps.
- Pure and total: never raises, never returns a non-string. A regex failure
  degrades to "nothing redacted" — capture must not break because of hygiene.
- Single implementation: both capture paths call this module so they cannot
  drift apart (same rationale as ``tool_digest``).
"""

from __future__ import annotations

import re
from typing import List, Tuple

# (kind, pattern). Order matters only for readability — patterns are disjoint.
#
# Vendor prefixes: the token itself carries its own type, so matching the
# prefix is unambiguous and needs no variable-name context.
_SECRET_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("pypi", re.compile(r"pypi-[A-Za-z0-9_\-]{16,}")),
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("openai", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Environment assignments whose NAME declares a secret. Two shapes:
#   TOKEN=abc / API_KEY="abc"            (POSIX + most CLIs)
#   $env:UV_PUBLISH_TOKEN='abc'          (PowerShell)
# The variable name is preserved so the archived line still reads as
# "a token was set here", only the value is gone.
_SECRET_ASSIGN_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|APIKEY|API_KEY)[A-Za-z0-9_]*"

_ENV_ASSIGN_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "env-assign",
        re.compile(
            r"(?i)(?P<name>\b" + _SECRET_ASSIGN_NAME + r")\s*=\s*['\"]?(?P<value>[^\s'\"&|;]{8,})"
        ),
    ),
    (
        "env-assign",
        re.compile(
            r"(?i)(\$env:)(?P<name>" + _SECRET_ASSIGN_NAME + r")\s*=\s*['\"]?(?P<value>[^\s'\"&|;]{8,})"
        ),
    ),
]


def _redact_kind(kind: str):
    """Replacement callable for the vendor-prefix patterns."""

    def _sub(_m: "re.Match[str]") -> str:
        return f"<redacted:{kind}>"

    return _sub


def _redact_env_assign(m: "re.Match[str]") -> str:
    """Keep the variable name, drop the value (groupdict-driven)."""
    groups = m.groupdict()
    name = groups.get("name") or ""
    prefix = m.group(0)[: m.start("name") - m.start()] if name else ""
    return f"{prefix}{name}=<redacted:secret>"


def redact_secrets(text: str) -> str:
    """Replace secret-shaped substrings in *text* with redaction markers.

    Never raises: on any failure the input is returned unchanged. Callers sit
    on the capture path, where a hygiene step must never cost a conversation.
    """
    if not isinstance(text, str) or not text:
        return text
    out = text
    try:
        for kind, pattern in _SECRET_PATTERNS:
            out = pattern.sub(_redact_kind(kind), out)
        for _kind, pattern in _ENV_ASSIGN_PATTERNS:
            out = pattern.sub(_redact_env_assign, out)
    except Exception:  # pragma: no cover — defensive, capture must not break
        return text
    return out
