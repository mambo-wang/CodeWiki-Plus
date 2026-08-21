# -*- coding: utf-8 -*-
"""Adoption-signal extraction (P1 A-line, docs/知识飞轮增强设计方案-P1三项.md §2).

An *adoption* is the explicit claim, made by the agent inside its own reply,
that it actually used a specific doc returned by ``query_wiki``.  The claim is
a single-line HTML comment convention:

    <!-- codewiki:referenced-docs: ["notes/pitfall-x.md", "wiki/modules/y.md"] -->

This module contains ONLY pure functions (no IO beyond optional path
existence checks supplied by the caller): parsing the convention out of
conversation turns and normalising the claimed paths.  Persistence lives in
``capture_conversation`` (adoption_events table), and consumption lives in the
usage-heat ranking (``cache.compute_usage_heat``).

Design posture (mirrors friction.py): the signal is a *lower bound* — agents
forget to declare (misses happen) but rarely declare docs they did not use
(false positives are rare).  Good enough as a ranking weight; NOT good enough
as a strict audit metric.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# The declaration comment.  Tolerant on the JSON payload whitespace; strict on
# the marker so ordinary prose mentioning "referenced-docs" never matches.
_ADOPTION_RE = re.compile(
    r"<!--\s*codewiki:referenced-docs:\s*(\[.*?\])\s*-->",
    re.DOTALL,
)


def extract_adopted_docs(
    turns: List[Dict[str, str]],
    existing: Optional[Any] = None,
) -> List[str]:
    """Collect declared adoption paths from conversation turns.

    Parameters
    ----------
    turns:
        ``[{role, content}]`` — the same filtered dialogue shape used by the
        friction scorer.  Only assistant turns are scanned (declarations are
        the agent's claims about its own work).
    existing:
        Optional callable ``exists(rel_path) -> bool`` used to drop paths that
        do not resolve inside the output_dir (typos, stale paths).  ``None``
        disables the filter (caller asserts paths are already valid).

    Returns a de-duplicated, sorted list of normalised relative paths
    (forward slashes, no leading ``./``).  Malformed JSON payloads are skipped
    silently — a broken declaration must never break the capture path.
    """
    if not turns:
        return []
    found: List[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role", "")) != "assistant":
            continue
        content = turn.get("content")
        if not isinstance(content, str) or not content:
            continue
        for m in _ADOPTION_RE.finditer(content):
            payload = m.group(1)
            try:
                items = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, str):
                    continue
                norm = _normalise_path(item)
                if not norm:
                    continue
                if existing is not None:
                    try:
                        if not existing(norm):
                            continue
                    except Exception:
                        continue  # existence check failure = keep the path
                if norm not in found:
                    found.append(norm)
    return sorted(found)


def _normalise_path(raw: str) -> str:
    """Normalise a declared doc path to the query_wiki ``file`` field shape."""
    p = (raw or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    # Reject obvious junk: empty, upward traversal, absolute leftovers.
    if not p or ".." in p.split("/"):
        return ""
    return p


def looks_like_search_happened(turns: List[Dict[str, str]]) -> bool:
    """Best-effort heuristic: did this conversation consume wiki search?

    Used for the optional adoption *nudge* — when a session shows search
    traces but carries no adoption declaration, ``capture_conversation``
    flags ``adoption_nudge: true`` once so the IDE log can remind the agent
    to declare what it used.  Deliberately conservative: only obvious
    snippets of query_wiki result payloads count.
    """
    _MARKERS = (
        "context_package",
        "query_coverage",
        "[unconfirmed]",
        "matched_tokens",
    )
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role", "")) != "assistant":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        if any(marker in content for marker in _MARKERS):
            return True
    return False


# --------------------------------------------------------------------------- #
# Persistence: adoption_events table (same SQLite db as retrieval_stats)
# --------------------------------------------------------------------------- #

_ADOPTION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS adoption_events (
    capture_key TEXT NOT NULL,
    doc_path    TEXT NOT NULL,
    adopted_at  TEXT NOT NULL,
    PRIMARY KEY (capture_key, doc_path)
)
"""


def record_adoption_events(
    stats_db: Path,
    capture_key: str,
    doc_paths: List[str],
    adopted_at: str,
) -> int:
    """Persist adoption claims into ``adoption_events`` (idempotent upsert).

    The primary key ``(capture_key, doc_path)`` makes re-capturing the same
    session a no-op (``INSERT OR IGNORE``): a supersede re-capture does not
    double-count, while a *newly declared* doc under the same key still
    counts once — semantically correct, that is a new adoption.

    Best-effort: any failure is swallowed and 0 is returned — adoption stats
    must never break the capture path (same posture as retrieval stats).
    Returns the number of rows actually inserted.
    """
    if not doc_paths or not capture_key:
        return 0
    try:
        conn = sqlite3.connect(str(stats_db))
        try:
            conn.execute(_ADOPTION_TABLE_DDL)
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO adoption_events "
                "(capture_key, doc_path, adopted_at) VALUES (?, ?, ?)",
                [(capture_key, p, adopted_at) for p in doc_paths],
            )
            conn.commit()
            return conn.total_changes - before
        finally:
            conn.close()
    except Exception:
        return 0


def load_adoption_counts(output_dir: Path) -> Dict[str, int]:
    """Aggregate ``doc_path → adopted_count`` from adoption_events.

    Missing table/db → empty mapping (callers treat "no data" as adopted=0,
    never as an error). Not mtime-cached: this is used by low-frequency paths
    (lint / wiki_stats); the hot search path reuses the combined loader in
    cache.py instead.
    """
    from codewiki.src.config import META_DIR
    db = Path(output_dir) / META_DIR / "retrieval_stats.db"
    counts: Dict[str, int] = {}
    if not db.exists():
        return counts
    try:
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(_ADOPTION_TABLE_DDL)  # ensure before SELECT (old dbs)
            for path, cnt in conn.execute(
                "SELECT doc_path, COUNT(*) FROM adoption_events GROUP BY doc_path"
            ).fetchall():
                counts[str(path)] = int(cnt)
        finally:
            conn.close()
    except Exception:
        return {}
    return counts
