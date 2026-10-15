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
    {"t": "outcome", "doc": "notes/x.md", "task_id": "他山之石",
     "at": "2026-09-14T11:30:00", "result": "success|failure", "note": "…",
     "adopted_key": "u1/sess-9"}

- ``hit`` events are aggregated per (user, doc, day) at write time: the
  last line of the user's file is rewritten in place when it already is
  today's hit line for the same doc, so line counts stay bounded.
- ``adopted`` events are plain appends; idempotency is enforced at
  aggregation time by de-duplicating on ``key`` (``<user>/<session>``).
- ``outcome`` events (docs/负反馈与经验通道设计方案.md §三) are plain
  appends too — low-frequency, no same-day merge. ``task_id`` / ``note`` /
  ``adopted_key`` are optional and omitted when empty; ``adopted_key``
  links the outcome back to the adoption that preceded it
  ("引用→结果" association). ``aggregate_usage`` folds ``success`` /
  ``failure`` counts per doc; ``by_file`` events stay in their own pipe.

Aggregation (``aggregate_usage``) is a pure in-memory fold over both
telemetry directories, guarded by an mtime snapshot cache: a rescan only
happens when some file's (name, mtime) changes. Corrupt lines are skipped
silently — a broken line must never break the aggregate.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

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

        uid = user_id(output_dir)
    except Exception:
        uid = "local"
    return d / f"{uid}.jsonl"


def _atomic_write_lines(path: Path, lines: List[str]) -> None:
    """Write jsonl lines atomically — delegates to the shared store writer."""
    from codewiki.src.store import atomic_write

    atomic_write(path, "\n".join(lines) + "\n")


def _read_lines(path: Path) -> List[str]:
    """Non-empty lines of a jsonl file; missing file → [] (never raises)."""
    try:
        return [
            line
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
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
    # Team-layout Phase 2: the merge-or-append is a read-modify-write on the
    # per-user event file; the whole sequence runs under the SAME sidecar
    # lock as record_adopted's append, so a hit merge and an adopted append
    # serialise instead of interleaving (a target-file lock would not
    # exclude this atomic replace on Windows).
    from codewiki.src.store import atomic_write, locked

    with locked(path):
        lines = _read_lines(path)
        merged = False
        # Newest-first scan: merge into the most recent matching hit line.
        for i in range(len(lines) - 1, -1, -1):
            try:
                ev = json.loads(lines[i])
            except (json.JSONDecodeError, ValueError, TypeError):
                continue  # corrupt line → skip it, keep scanning
            if (
                isinstance(ev, dict)
                and ev.get("t") == "hit"
                and ev.get("doc") == doc_path
                and str(ev.get("at", "")) == today
            ):
                ev["n"] = int(ev.get("n", 0) or 0) + int(count)
                lines[i] = json.dumps(ev, ensure_ascii=False)
                merged = True
                break
        if not merged:
            lines.append(
                json.dumps(
                    {"t": "hit", "doc": doc_path, "at": today, "n": int(count)},
                    ensure_ascii=False,
                )
            )
        atomic_write(path, "\n".join(lines) + "\n")


def record_adopted(output_dir, doc_path: str, capture_key: str) -> None:
    """Append an ``adopted`` event (idempotency is aggregation-side, by key)."""
    path = _user_events_path(output_dir, create=True)
    event = {
        "t": "adopted",
        "doc": doc_path,
        "at": datetime.now().isoformat(timespec="seconds"),
        "key": capture_key,
    }
    # Team-layout Phase 2: locked append under the SAME sidecar lock as
    # record_hit's rewrite — the two write paths of one user file serialise.
    from codewiki.src.store import locked

    with locked(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_by_file(output_dir, doc_path: str, count: int = 1) -> None:
    """Append (or same-day-merge) a ``by_file`` event for *doc_path*.

    P0-2 (claude-mem borrowing): by_file is a pre-read pre-check, NOT a
    deep-consumption event — it must not feed the usage-heat ranking (same
    discipline as mode=check). But acceptance #8 needs by_file adoption-rate
    data, so it IS recorded in the telemetry event stream under its own
    event type. ``aggregate_usage`` folds only ``hit``/``adopted`` events,
    so the two pipes stay separate by construction.
    """
    path = _user_events_path(output_dir, create=True)
    today = date.today().isoformat()
    from codewiki.src.store import atomic_write, locked

    with locked(path):
        lines = _read_lines(path)
        merged = False
        for i in range(len(lines) - 1, -1, -1):
            try:
                ev = json.loads(lines[i])
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
            if (
                isinstance(ev, dict)
                and ev.get("t") == "by_file"
                and ev.get("doc") == doc_path
                and str(ev.get("at", "")) == today
            ):
                ev["n"] = int(ev.get("n", 0) or 0) + int(count)
                lines[i] = json.dumps(ev, ensure_ascii=False)
                merged = True
                break
        if not merged:
            lines.append(
                json.dumps(
                    {"t": "by_file", "doc": doc_path, "at": today, "n": int(count)},
                    ensure_ascii=False,
                )
            )
        atomic_write(path, "\n".join(lines) + "\n")


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
        if (
            isinstance(ev, dict)
            and ev.get("t") == "adopted"
            and ev.get("key") == capture_key
            and isinstance(ev.get("doc"), str)
        ):
            found.add(ev["doc"])
    return found


def record_outcome(
    output_dir,
    doc_path: str,
    result: str,
    task_id: str = "",
    note: str = "",
    adopted_key: str = "",
) -> None:
    """Append an ``outcome`` event (design §三, telemetry third event).

    hit = I saw it, adopted = I cited it, outcome = after using it, did the
    work succeed? Plain append under the same sidecar lock as the other
    write paths (low-frequency event, no same-day merge). Optional fields
    (``task_id`` / ``note`` / ``adopted_key``) are omitted from the event
    when empty — a minimal event stays one readable line. Callers validate
    ``result`` ∈ {success, failure}; this writer trusts its inputs like
    its siblings do.
    """
    path = _user_events_path(output_dir, create=True)
    event: Dict[str, object] = {
        "t": "outcome",
        "doc": doc_path,
        "at": datetime.now().isoformat(timespec="seconds"),
        "result": result,
    }
    if task_id:
        event["task_id"] = task_id
    if note:
        event["note"] = note
    if adopted_key:
        event["adopted_key"] = adopted_key
    from codewiki.src.store import locked

    with locked(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def last_adopted_key_for_doc(output_dir, doc_path: str, keys=None) -> str:
    """Newest ``adopted`` event key for *doc_path* in the current user's file.

    Read-only helper for the outcome → adoption association (design §三):
    when the same doc was adopted in the same session/task lineage, the
    outcome event copies that key so "引用→结果" chains are traceable.
    ``keys`` (optional set) restricts matching to specific capture keys;
    an EMPTY set matches nothing (lineage known, no qualifying adoption);
    ``None`` matches any (doc-level, used when no lineage is known).
    Newest-first scan; '' when nothing matches.
    """
    path = _user_events_path(output_dir, create=False)
    for line in reversed(_read_lines(path)):
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(ev, dict)
            and ev.get("t") == "adopted"
            and ev.get("doc") == doc_path
            and isinstance(ev.get("key"), str)
            and (keys is None or ev["key"] in keys)
        ):
            return ev["key"]
    return ""


def recent_outcome_failures(output_dir, days: int = 30, limit: int = 5) -> List[dict]:
    """Recent ``failure`` outcomes across ALL users, newest-first.

    Consumption-side helper for negative_examples (design §四): the
    distill/consolidate prepare payloads carry the last *limit* failures
    inside a *days* window so new knowledge extraction can avoid the same
    failure pattern. Pure prompt material (observe) — nothing downstream
    behaves differently. Returns ``[{doc, note, task_id?, at}]``.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    rows: List[tuple] = []
    for d in _telemetry_dirs(output_dir):
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
                if not isinstance(ev, dict) or ev.get("t") != "outcome":
                    continue
                if ev.get("result") != "failure":
                    continue
                doc = ev.get("doc")
                if not isinstance(doc, str) or not doc:
                    continue
                at = str(ev.get("at") or "")
                if not at or at < cutoff:
                    continue
                row: Dict[str, str] = {"doc": doc, "note": str(ev.get("note") or "")}
                tid = str(ev.get("task_id") or "").strip()
                if tid:
                    row["task_id"] = tid
                rows.append((at, row))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in rows[:limit]]


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

    Entry shape (T2 §4.2, extended with first_hit/hit_days for wiki_stats;
    success/failure folded from outcome events, design §三)::

        {"hits": int, "last_hit": Optional[str], "first_hit": Optional[str],
         "adopted": int, "adopted_keys": set, "hit_days": set,
         "success": int, "failure": int}

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
                entry = usage.setdefault(
                    doc,
                    {
                        "hits": 0,
                        "last_hit": None,
                        "first_hit": None,
                        "adopted_keys": set(),
                        "hit_days": set(),
                        "success": 0,
                        "failure": 0,
                    },
                )
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
                elif t == "outcome":
                    # Design §三: binary result, no grading — invalid values
                    # are skipped (an outcome event that can't be classified
                    # must not pollute either counter).
                    r = ev.get("result")
                    if r == "success":
                        entry["success"] += 1
                    elif r == "failure":
                        entry["failure"] += 1

    for entry in usage.values():
        entry["adopted"] = len(entry["adopted_keys"])

    _AGG_CACHE[key] = (snap, usage)
    return usage
