"""Friction scoring for captured conversations (K-line, v1: dialogue-level signals).

Team-memory fusion trigger sensor: when a session shows *friction* — the user
correcting the assistant, interrupting it, or repeating the same request — the
conversation is likely to contain a worth-distilling lesson. This module turns
that intuition into an objective, cheap score computed at capture time from the
already-filtered user/assistant turns only (tool traffic is dropped upstream by
``capture_conversation._extract_transcript`` — see 设计方案 §2.1).

Scoring model (docs/知识飞轮增强设计方案-P0三项.md §2.2):

    friction_score = correction×20 + interrupt×20 + repeat×15 + min(scale, 10)
    scale          = (user_turns >= 8 → +5) + (total_turns >= 20 → +5)
    hard gate      : user_turns < min_user_turns (default 4) → score = 0
    verdict        : score >= threshold (default 20) → "suggest_distill"

Anti-false-positive properties (borrowed from teamai's math):
  1. scale bonus is capped at 10 < threshold 20 — a long but smooth session
     never triggers;
  2. short sessions (user_turns < 4) never trigger;
  3. the output is a *hint only*: it influences distillation priority and
     prompt copy, never auto-distills and never bypasses the confirm gate.

Pure-function module: stdlib only, no codewiki imports, no I/O — safe to call
from the lightweight capture path and from the stdlib-only session-start hook
logic (which re-implements its own line scanner).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# User-correction keywords. Hit anywhere in a user turn's content counts as one
# correction (at most one per turn, even when several keywords match).
DEFAULT_CORRECTION_KEYWORDS = [
    "不对", "你搞错", "搞错了", "不是这样", "不是这样的", "错了", "应该是",
    "不用这样", "别这样",
    "wrong", "incorrect", "that's not right", "redo", "重来",
]

# Interruption markers. CodeBuddy/Claude-family transcripts append these to the
# user turn that got cut off.
DEFAULT_INTERRUPT_MARKERS = [
    "[Request interrupted",
    "[Request interrupted by user",
]

DEFAULT_THRESHOLD = 20
DEFAULT_MIN_USER_TURNS = 4

_CORRECTION_WEIGHT = 20
_INTERRUPT_WEIGHT = 20
_REPEAT_WEIGHT = 15
_SCALE_USER_TURNS_BONUS = 5       # user_turns >= 8
_SCALE_TOTAL_TURNS_BONUS = 5      # total_turns >= 20
_SCALE_CAP = 10


def _normalize(text: str) -> str:
    """Whitespace-stripped, lowercased comparison form for repeat detection."""
    return "".join(str(text).split()).lower()


def score_friction(
    turns: List[Dict[str, str]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score the friction level of a user/assistant conversation.

    Args:
        turns: list of ``{"role": "user"|"assistant", "content": str}`` dicts
            (the shape ``capture_conversation._extract_transcript`` produces).
        config: optional overrides, all keys optional:
            - ``threshold`` (int, default 20): verdict cutoff;
            - ``min_user_turns`` (int, default 4): hard gate;
            - ``correction_keywords`` (list[str]);
            - ``interrupt_markers`` (list[str]).

    Returns:
        ``{"score": int, "verdict": str, "signals": {
            "correction": int, "interrupt": int, "repeat": int,
            "user_turns": int, "total_turns": int}}``.
        ``verdict`` is ``"suggest_distill"`` when score >= threshold, else ``""``.
    """
    cfg = config if isinstance(config, dict) else {}
    try:
        threshold = int(cfg.get("threshold", DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        threshold = DEFAULT_THRESHOLD
    try:
        min_user_turns = int(cfg.get("min_user_turns", DEFAULT_MIN_USER_TURNS))
    except (TypeError, ValueError):
        min_user_turns = DEFAULT_MIN_USER_TURNS
    keywords = cfg.get("correction_keywords") or DEFAULT_CORRECTION_KEYWORDS
    markers = cfg.get("interrupt_markers") or DEFAULT_INTERRUPT_MARKERS

    user_contents: List[str] = []
    total_turns = 0
    for t in turns if isinstance(turns, list) else []:
        if not isinstance(t, dict):
            continue
        total_turns += 1
        if t.get("role") != "user":
            continue
        content = t.get("content", "")
        user_contents.append(content if isinstance(content, str) else str(content))
    user_turns = len(user_contents)

    correction = 0
    interrupt = 0
    for content in user_contents:
        if any(k in content for k in keywords):
            correction += 1
        if any(m in content for m in markers):
            interrupt += 1

    # Repeat: adjacent user turns whose normalized text (lower + all whitespace
    # removed) is identical. A run of >2 identical turns counts as ONE group.
    repeat = 0
    prev: Optional[str] = None
    prev_matched = False
    for content in user_contents:
        norm = _normalize(content)
        if prev is not None and norm == prev:
            if not prev_matched:
                repeat += 1
                prev_matched = True
        else:
            prev_matched = False
        prev = norm

    scale = 0
    if user_turns >= 8:
        scale += _SCALE_USER_TURNS_BONUS
    if total_turns >= 20:
        scale += _SCALE_TOTAL_TURNS_BONUS
    scale = min(scale, _SCALE_CAP)

    score = (
        correction * _CORRECTION_WEIGHT
        + interrupt * _INTERRUPT_WEIGHT
        + repeat * _REPEAT_WEIGHT
        + scale
    )
    # Hard gate: too few user turns → friction is meaningless, score forced to 0.
    if user_turns < min_user_turns:
        score = 0

    verdict = "suggest_distill" if score >= threshold else ""
    return {
        "score": score,
        "verdict": verdict,
        "signals": {
            "correction": correction,
            "interrupt": interrupt,
            "repeat": repeat,
            "user_turns": user_turns,
            "total_turns": total_turns,
        },
    }


def format_friction_signals(signals: Dict[str, Any]) -> str:
    """Render a signals dict as the single-line frontmatter value
    ``correction=2,interrupt=0,repeat=0,user_turns=9``.

    The format deliberately avoids YAML-special characters (only ``=`` and ``,``
    on a bare word/value basis) so the value survives the simple line scanners
    used by distill_conversation and the session-start hook.
    """
    return (
        f"correction={signals.get('correction', 0)},"
        f"interrupt={signals.get('interrupt', 0)},"
        f"repeat={signals.get('repeat', 0)},"
        f"user_turns={signals.get('user_turns', 0)}"
    )
