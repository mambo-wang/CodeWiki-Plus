# -*- coding: utf-8 -*-
"""Team telemetry (T2, docs/团队知识库支持优化设计方案.md §4.2).

Per-user JSONL event streams are the single source of truth for usage
signals (retrieval hits + adoptions). The old ``retrieval_stats.db`` /
``adoption_events`` SQLite tables are retired — no migration, no dual
write: replaying all ``telemetry/*.jsonl`` files always rebuilds the
correct aggregate state.

Layout (default, committed to the repo so teammates' signals merge via
ordinary git file-level flows — each user only ever appends to their own
file, so merges are conflict-free)::

    repowiki/.meta/telemetry/<user_id>.jsonl      # shared (default)
    repowiki/.meta/telemetry-local/<user_id>.jsonl # gitignored fallback
                                                   # (conventions.telemetry.enabled: false)

Event format (one JSON object per line)::

    {"t": "hit",     "doc": "notes/x.md", "at": "2026-08-22", "n": 3}
    {"t": "adopted", "doc": "notes/x.md", "at": "2026-08-22T10:05:00", "key": "u1/sess-9"}

- ``hit`` events are aggregated per (user, doc, day) at write time: the
  last line of the user's file is rewritten in place when it already is
  today's hit line for the same doc, so line counts stay bounded.
- ``adopted`` events are plain appends; idempotency is enforced at
  aggregation time by de-duplicating on ``key`` (``<user>/<session>``).

Aggregation (``aggregate_usage``) is a pure in-memory fold over both
telemetry directories, guarded by an mtime snapshot cache: a rescan only
happens when some file's (name, mtime) changes. Corrupt lines are skipped
silently — a broken line must never break the aggregate.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Directory names under output_dir/.meta/ — shared (committed) and local
# (gitignored) modes. Aggregation ALWAYS scans both so flipping the schema
# switch never orphans previously recorded events.
TELEMETRY_DIRNAME = "telemetry"
TELEMETRY_LOCAL_DIRNAME = "telemetry-local"

# output_dir (str) -> (mtime snapshot, aggregated usage dict)
_AGG_CACHE: Dict[str, Tuple[tuple, Dict[str, dict]]] = {}


def _meta_dir(output_dir) -> Path:
    try:
        from codewiki.src.config import META_DIR
        return Path(output_dir) / META_DIR
    except Exception:
        return Path(output_dir) / ".meta"


def _telemetry_dirs(output_dir) -> List[Path]:
    """Both event directories (shared + local), in a stable order."""
    meta = _meta_dir(output_dir)
    return [meta / TELEMETRY_DIRNAME, meta / TELEMETRY_LOCAL_DIRNAME]


def telemetry_enabled(output_dir) -> bool:
    """Read ``conventions.telemetry.enabled`` from the bundle schema.yaml.

    Default True (team sharing is the main scenario). Missing schema /
    missing block / malformed values all fall back to True — a broken
    schema must never silently switch a team to local mode.
    """
    try:
        from codewiki.src.config import SCHEMA_FILENAME
        name = SCHEMA_FILENAME
    except Exception:
        name = "schema.yaml"
    p = Path(output_dir) / name
    try:
        import yaml
        with open(p, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        block = (data.get("conventions") or {}).get("telemetry") or {}
        enabled = block.get("enabled")
        if isinstance(enabled, bool):
            return enabled
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("telemetry_enabled: schema read failed (%s); defaulting on", e)
    return True


def _user_events_path(output_dir, create: bool = False) -> Path:
    """Path of the current user's event file (mode-aware)."""
    sub = TELEMETRY_DIRNAME if telemetry_enabled(output_dir) else TELEMETRY_LOCAL_DIRNAME
    d = _meta_dir(output_dir) / sub
    if create:
        d.mkdir(parents=True, exist_ok=True)
    try:
        from codewiki.src.config import user_id
        uid = user_id()
    except Exception:
        uid = "local"
    return d / f"{uid}.jsonl"


def _atomic_write_lines(path: Path, lines: List[str]) -> None:
    """Write jsonl lines via temp file + os.replace (crash-safe)."""
    tmp = path.parent / (path.name + f".tmp.{os.getpid()}")
    try:
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _read_lines(path: Path) -> List[str]:
    """Non-empty lines of a jsonl file; missing file → [] (never raises)."""
    try:
        return [l for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# Write path
# --------------------------------------------------------------------------- #

def record_hit(output_dir, doc_path: str, count: int = 1) -> None:
    """Append (or same-day-merge) a ``hit`` event for *doc_path*.

    Same-day aggregation: the first matching line in the user's event file
    (newest first) that already is today's hit line for the same doc gets
    its ``n`` incremented in place; otherwise a new line is appended.
    Scanning the whole file (instead of just the tail) keeps the file
    bounded at one line per (user, doc, day) even when a query returns many
    docs and interleaves hits between invocations. Corrupt lines are
    skipped and never block a merge. Failures propagate; callers keep the
    best-effort try/except posture (stats must never break the search path,
    but the write helper itself stays honest).
    """
    path = _user_events_path(output_dir, create=True)
    today = date.today().isoformat()
    lines = _read_lines(path)
    merged = False
    # Newest-first scan: merge into the most recent matching hit line.
    for i in range(len(lines) - 1, -1, -1):
        try:
            ev = json.loads(lines[i])
        except (json.JSONDecodeError, ValueError, TypeError):
            continue  # corrupt line → skip it, keep scanning
        if (isinstance(ev, dict)
                and ev.get("t") == "hit"
                and ev.get("doc") == doc_path
                and str(ev.get("at", "")) == today):
            ev["n"] = int(ev.get("n", 0) or 0) + int(count)
            lines[i] = json.dumps(ev, ensure_ascii=False)
            merged = True
            break
    if not merged:
        lines.append(json.dumps(
            {"t": "hit", "doc": doc_path, "at": today, "n": int(count)},
            ensure_ascii=False,
        ))
    _atomic_write_lines(path, lines)


def record_adopted(output_dir, doc_path: str, capture_key: str) -> None:
    """Append an ``adopted`` event (idempotency is aggregation-side, by key)."""
    path = _user_events_path(output_dir, create=True)
    event = {
        "t": "adopted",
        "doc": doc_path,
        "at": datetime.now().isoformat(timespec="seconds"),
        "key": capture_key,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def adopted_docs_for_key(output_dir, capture_key: str) -> Set[str]:
    """Docs already recorded under *capture_key* in the current user's file.

    Read-only helper for write-side de-duplication (a supersede re-capture
    of the same session should not append duplicate lines). Does NOT create
    the telemetry directory.
    """
    if not capture_key:
        return set()
    path = _user_events_path(output_dir, create=False)
    found: Set[str] = set()
    for line in _read_lines(path):
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if (isinstance(ev, dict)
                and ev.get("t") == "adopted"
                and ev.get("key") == capture_key
                and isinstance(ev.get("doc"), str)):
            found.add(ev["doc"])
    return found


# --------------------------------------------------------------------------- #
# Aggregation (pure in-memory fold + mtime snapshot cache)
# --------------------------------------------------------------------------- #

def _dir_snapshot(dirs: List[Path]) -> tuple:
    """(dir-name, file-name, mtime_ns) for every *.jsonl in every dir."""
    snap = []
    for d in dirs:
        try:
            for f in sorted(d.glob("*.jsonl")):
                try:
                    snap.append((d.name, f.name, f.stat().st_mtime_ns))
                except OSError:
                    continue
        except OSError:
            continue
    return tuple(snap)


def aggregate_usage(output_dir) -> Dict[str, dict]:
    """Fold all users' event streams into ``{doc: usage}``.

    Entry shape (T2 §4.2, extended with first_hit/hit_days for wiki_stats)::

        {"hits": int, "last_hit": Optional[str], "first_hit": Optional[str],
         "adopted": int, "adopted_keys": set, "hit_days": set}

    - ``hits`` sums every hit line's ``n`` across all users;
    - ``adopted`` counts DISTINCT capture keys (same key replayed in
      multiple lines counts once);
    - ``last_hit`` / ``first_hit`` come from hit events only (adoption
      timestamps never masquerade as retrieval activity);
    - every bad line is skipped independently (try/except per line).

    Process-wide mtime snapshot cache: while no (name, mtime) changes, the
    cached dict is returned directly.
    """
    od = Path(output_dir)
    dirs = _telemetry_dirs(od)
    snap = _dir_snapshot(dirs)
    key = str(od)
    cached = _AGG_CACHE.get(key)
    if cached is not None and cached[0] == snap:
        return cached[1]

    usage: Dict[str, dict] = {}
    for d in dirs:
        try:
            files = sorted(d.glob("*.jsonl"))
        except OSError:
            continue
        for f in files:
            for line in _read_lines(f):
                try:
                    ev = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(ev, dict):
                    continue
                doc = ev.get("doc")
                if not isinstance(doc, str) or not doc:
                    continue
                entry = usage.setdefault(doc, {
                    "hits": 0, "last_hit": None, "first_hit": None,
                    "adopted_keys": set(), "hit_days": set(),
                })
                t = ev.get("t")
                if t == "hit":
                    try:
                        n = int(ev.get("n", 1) or 0)
                    except (TypeError, ValueError):
                        n = 1
                    entry["hits"] += max(0, n)
                    at = str(ev.get("at") or "")[:10]
                    if at:
                        entry["hit_days"].add(at)
                        if entry["last_hit"] is None or at > entry["last_hit"]:
                            entry["last_hit"] = at
                        if entry["first_hit"] is None or at < entry["first_hit"]:
                            entry["first_hit"] = at
                elif t == "adopted":
                    k = ev.get("key")
                    if isinstance(k, str) and k:
                        entry["adopted_keys"].add(k)

    for entry in usage.values():
        entry["adopted"] = len(entry["adopted_keys"])

    _AGG_CACHE[key] = (snap, usage)
    return usage
