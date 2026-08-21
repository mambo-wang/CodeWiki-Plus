#!/usr/bin/env python3
"""Freshness backfill migration for existing CodeWiki LLM Wikis.

One-shot, IDEMPOTENT migration (新鲜度机制专项, docs/新鲜度机制设计方案.md §6):
converts historical ``verified`` events into freshness so confirmed notes that
were re-validated in the past are not immediately flagged as stale once lint
starts honoring ``stale_after`` (the previously write-only field).

For every stable/confirmed note under ``notes/``:

    stale_after = max(current stale_after, last verified.at + type window)

Notes without any ``verified`` event keep their current value untouched.
Type windows are read from ``schema.yaml`` ``conventions.freshness`` with the
same fallback chain as the runtime helpers (by_type[type] →
default_window_days → default_stale_days → 90) — see
``codewiki.mcp.tools.knowledge_loop.load_freshness_config``.

Running the script twice produces the same result (the max() is idempotent).

Usage:
    python scripts/migrate_freshness.py <output_dir> [--dry-run]

``<output_dir>`` is the repowiki output directory (the one containing
``wiki/``, ``notes/`` and ``schema.yaml``), e.g. ``./repowiki``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

_FALLBACK_WINDOW_DAYS = 90
_ACTIVE_STATUSES = {"stable", "confirmed"}  # OKF v0.2 + legacy vocabulary


# --------------------------------------------------------------------------- #
# Config (mirrors knowledge_loop.load_freshness_config — keep in sync)
# --------------------------------------------------------------------------- #
def load_freshness_config(schema: Optional[dict]) -> Dict[str, Any]:
    conv = (schema or {}).get("conventions") or {}
    fresh = conv.get("freshness") or {}
    if not isinstance(fresh, dict):
        fresh = {}

    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    legacy_default = _int(conv.get("default_stale_days"), _FALLBACK_WINDOW_DAYS)
    default_window = _int(fresh.get("default_window_days"), legacy_default)
    by_type: Dict[str, int] = {}
    raw = fresh.get("by_type") or {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            by_type[str(key).strip().lower()] = _int(value, default_window)
    return {"default_window_days": default_window, "by_type": by_type}


def window_for(note_type: Any, cfg: Dict[str, Any]) -> int:
    key = str(note_type or "").strip().lower()
    return cfg["by_type"].get(key, cfg["default_window_days"])


# --------------------------------------------------------------------------- #
# Frontmatter helpers
# --------------------------------------------------------------------------- #
def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None, None
    end = text.find("---", 3)
    if end < 0:
        return None, None
    return text[3:end], text[end + 3:]


def parse_day(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def last_verified_at(fm: Dict[str, Any]) -> Optional[datetime]:
    verified = fm.get("verified")
    if isinstance(verified, dict):
        verified = [verified]
    if not isinstance(verified, list):
        return None
    latest: Optional[datetime] = None
    for event in verified:
        if not isinstance(event, dict):
            continue
        at = parse_day(event.get("at"))
        if at and (latest is None or at > latest):
            latest = at
    return latest


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
def migrate(output_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
    notes_dir = output_dir / "notes"
    if not notes_dir.is_dir():
        return {"error": f"notes/ directory not found under {output_dir}"}

    schema: Dict[str, Any] = {}
    schema_path = output_dir / "schema.yaml"
    if schema_path.is_file():
        try:
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"WARNING: could not parse {schema_path}: {e}", file=sys.stderr)
    cfg = load_freshness_config(schema)

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    stats = {
        "scanned": 0,
        "skipped_parse": 0,
        "skipped_status": 0,
        "no_verified": 0,
        "updated": 0,
        "unchanged": 0,
        "still_due": [],
    }

    for note_file in sorted(notes_dir.glob("*.md")):
        stats["scanned"] += 1
        try:
            text = note_file.read_text(encoding="utf-8")
        except OSError:
            stats["skipped_parse"] += 1
            continue
        fm_text, body = split_frontmatter(text)
        if fm_text is None:
            stats["skipped_parse"] += 1
            continue
        try:
            fm = yaml.safe_load(fm_text)
            if not isinstance(fm, dict):
                raise ValueError("frontmatter is not a mapping")
        except Exception:
            stats["skipped_parse"] += 1
            continue

        status = str(fm.get("status", "")).strip().lower()
        if status not in _ACTIVE_STATUSES:
            stats["skipped_status"] += 1
            continue

        verified_at = last_verified_at(fm)
        if verified_at is None:
            # 无 verified 事件：保持现值（设计方案 §6）
            stats["no_verified"] += 1
            current = parse_day(fm.get("stale_after"))
            if current is not None and current < today:
                stats["still_due"].append(note_file.name)
            continue

        window = window_for(fm.get("type"), cfg)
        candidate = verified_at + timedelta(days=window)
        current = parse_day(fm.get("stale_after"))
        new_due = candidate if current is None or candidate > current else current

        if current is None or new_due > current:
            if not dry_run:
                fm["stale_after"] = new_due.strftime("%Y-%m-%d")
                new_fm = yaml.safe_dump(
                    fm, allow_unicode=True, sort_keys=False, default_flow_style=False
                )
                note_file.write_text(f"---\n{new_fm}---{body}", encoding="utf-8")
            stats["updated"] += 1
            old_str = current.strftime("%Y-%m-%d") if current else "<none>"
            print(
                f"{'[dry-run] ' if dry_run else ''}renew {note_file.name}: "
                f"stale_after {old_str} -> "
                f"{new_due.strftime('%Y-%m-%d')} "
                f"(verified {verified_at.strftime('%Y-%m-%d')} + {window}d)"
            )
        else:
            stats["unchanged"] += 1

        if new_due < today:
            stats["still_due"].append(note_file.name)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill stale_after from historical verified events (idempotent)."
    )
    parser.add_argument("output_dir", help="repowiki output directory (contains notes/ and schema.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    if not output_dir.is_dir():
        print(f"ERROR: {output_dir} is not a directory", file=sys.stderr)
        return 2

    stats = migrate(output_dir, dry_run=args.dry_run)
    if "error" in stats:
        print(f"ERROR: {stats['error']}", file=sys.stderr)
        return 2

    print()
    print(f"scanned        : {stats['scanned']}")
    print(f"updated        : {stats['updated']}")
    print(f"unchanged      : {stats['unchanged']}")
    print(f"no verified[]  : {stats['no_verified']} (kept as-is)")
    print(f"skipped (parse): {stats['skipped_parse']}")
    print(f"skipped (status): {stats['skipped_status']}")
    if stats["still_due"]:
        print()
        print(
            f"still past due after backfill: {len(stats['still_due'])} note(s) — "
            "organize a batch review (confirm_note to renew / reject_note to retire):"
        )
        for name in stats["still_due"]:
            print(f"  - notes/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
