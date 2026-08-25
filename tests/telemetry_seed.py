# -*- coding: utf-8 -*-
"""Shared helpers for tests that seed telemetry data (T2 migration).

The old helpers wrote rows into .meta/retrieval_stats.db / adoption_events.
T2 retired those tables — the single source of truth is now per-user JSONL
event streams under .meta/telemetry/. These helpers write equivalent events
so existing test semantics (hit counts, last_hit dates, adoption counts,
distinct keys) carry over unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from codewiki.mcp.tools import telemetry

TELEMETRY_DIR = telemetry.TELEMETRY_DIRNAME  # ".meta/telemetry"


def write_telemetry(
    od: Path,
    user: str,
    events: list,
) -> Path:
    """Write raw event lines to .meta/telemetry/<user>.jsonl.

    ``events`` is a list of dicts (already in event format). The aggregate
    cache is invalidated by the mtime snapshot on next call, so no manual
    reset is needed.
    """
    d = Path(od) / ".meta" / TELEMETRY_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{user}.jsonl"
    lines = [json.dumps(e, ensure_ascii=False) for e in events]
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


def days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def seed_hits(
    od: Path,
    rows: dict,
    user: str = "tester",
) -> None:
    """Seed hit events — replacement for the old _write_stats SQLite helper.

    ``rows``: {rel_path: (hit_count, last_hit_date_str)}. A single hit line
    per doc carries the whole count with the given date (the aggregate sums
    ``n`` values, so one line is equivalent to N separate hits on that day).
    """
    events = []
    for doc, (hc, lh) in rows.items():
        if hc and hc > 0:
            events.append({"t": "hit", "doc": doc, "at": lh, "n": int(hc)})
    write_telemetry(od, user, events)


def seed_adopted(
    od: Path,
    rows: list,
    user: str = "tester",
) -> None:
    """Seed adopted events — replacement for adoption_events table seeding.

    ``rows``: list of (doc_path, capture_key[, adopted_at]) tuples. Same-key
    duplicates are aggregated away, mirroring the old PK behaviour.
    """
    events = []
    for row in rows:
        doc, key = row[0], row[1]
        at = row[2] if len(row) > 2 else days_ago(0) + "T10:00:00"
        events.append({"t": "adopted", "doc": doc, "at": at, "key": key})
    write_telemetry(od, user, events)
