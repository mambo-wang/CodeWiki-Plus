# -*- coding: utf-8 -*-
"""Index freshness self-healing (T1a, docs/团队知识库支持优化设计方案.md §3).

The search index (SQLite main path or JSON fallback) is derived state: it can
silently fall behind the md files on disk — most commonly after a ``git pull``
brought new/deleted/confirmed notes from a teammate. This module adds a cheap
gate at the search entry points: when the index no longer matches the disk
inventory, the index is rebuilt transparently.

Three-tier check (all O(inventory scan), file contents are never read):
  1. count    — number of indexable md files vs index total_docs
  2. manifest — index doc_key set vs disk relative-path set (count tiebreak)
  3. mtime   — sample ≤8 files; any mtime newer than the index build time
               (covers content-only changes: a teammate confirm_note'd a draft
               you pulled — file count unchanged, authority changed)

Failure posture: self-healing must NEVER break search. A failed rebuild falls
back to the stale index and the caller flags ``index_stale`` in its result.
Check frequency is throttled to one scan per output_dir per 60s.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_S = 60  # per output_dir throttle
_MTIME_SAMPLE = 8  # files sampled for tier-3
_INDEX_BUILT_KEY = "index_built_at"  # search_stats key (SQLite) / dict key (JSON)

# Throttle state: output_dir str -> (last_check_ts, was_stale)
_last_check: Dict[str, Tuple[float, bool]] = {}


def scan_disk_inventory(output_dir: Path) -> Set[str]:
    """Relative paths of all indexable md files under output_dir.

    Mirrors the inventory build_full_index walks: wiki/**/*.md (minus system
    files), notes/*.md, raw/sources/**. Paths use forward slashes — the same
    doc_key shape the indexes store.
    """
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES, NOTES_DIR, RAW_SOURCES_DIR

    inv: Set[str] = set()
    wiki_dir = output_dir / WIKI_DIR
    if wiki_dir.is_dir():
        for md in wiki_dir.rglob("*.md"):
            if md.name in WIKI_SYSTEM_FILES:
                continue
            inv.add(str(md.relative_to(output_dir)).replace("\\", "/"))
    else:
        # Repos without a wiki/ dir: root-level md files are indexed too
        # (mirrors build_full_index's legacy branch); index.md/log.md/overview.md excluded.
        for md in output_dir.iterdir():
            if (
                md.is_file()
                and md.suffix == ".md"
                and md.name not in ("index.md", "log.md", "overview.md")
            ):
                inv.add(md.name)
    notes_dir = output_dir / NOTES_DIR
    if notes_dir.is_dir():
        for md in notes_dir.glob("*.md"):
            inv.add(str(md.relative_to(output_dir)).replace("\\", "/"))
    src_dir = output_dir / RAW_SOURCES_DIR
    if src_dir.is_dir():
        for md in src_dir.rglob("*.md"):
            inv.add(str(md.relative_to(output_dir)).replace("\\", "/"))
    return inv


def _read_sqlite_index_info(output_dir: Path) -> Optional[Dict[str, object]]:
    """(total_docs, doc_keys, built_at) from the standalone analysis cache db.

    Returns None when the db is absent or unreadable (caller then has no
    SQLite index to validate — nothing to self-heal on this path).
    """
    from codewiki.mcp.tools.wiki_search import _resolve_db_path

    db_path = _resolve_db_path(output_dir)
    if db_path is None or not db_path.exists():
        return None
    import sqlite3

    try:
        conn = sqlite3.connect(
            str(db_path), timeout=30.0
        )  # Team-layout Phase 2: explicit busy timeout
        try:
            row = conn.execute("SELECT value FROM search_stats WHERE key='total_docs'").fetchone()
            if not row or int(row[0]) == 0:
                return None
            keys = {r[0] for r in conn.execute("SELECT doc_key FROM search_index").fetchall()}
            # Total = actual row count in search_index, NOT search_stats.total_docs.
            # Incremental deletes (update_search_doc/remove_file) don't maintain
            # the stats field, so using it here would flag every tool-side
            # delete as a count mismatch and force a full rebuild.
            total = len(keys)
            built = conn.execute(
                "SELECT value FROM search_stats WHERE key=?", (_INDEX_BUILT_KEY,)
            ).fetchone()
            return {"total": total, "keys": keys, "built_at": built[0] if built else None}
        finally:
            conn.close()
    except Exception as e:
        logger.debug("freshness: sqlite index info read failed: %s", e)
        return None


def _read_json_index_info(output_dir: Path) -> Optional[Dict[str, object]]:
    """(total_docs, doc_keys, built_at) from the legacy JSON index file."""
    # NOTE: the JSON index filename is wiki_search's module constant
    # (``search_index.json``) — NOT config.SEARCH_INDEX_FILENAME (which is
    # the SQLite db name). Import it to stay in lockstep.
    from codewiki.mcp.tools.wiki_search import _SEARCH_INDEX_FILENAME
    from codewiki.src.config import META_DIR

    for cand in (
        output_dir / META_DIR / _SEARCH_INDEX_FILENAME,
        output_dir / _SEARCH_INDEX_FILENAME,
    ):
        if not cand.exists():
            continue
        try:
            import json

            data = json.loads(cand.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("freshness: json index read failed: %s", e)
            continue
        docs = data.get("docs") or {}
        if not docs:
            return None
        return {
            "total": int(data.get("total_docs") or len(docs)),
            "keys": set(docs.keys()),
            # JSON index stores the build stamp under "built_at"
            # (_IndexData.to_dict); SQLite uses the search_stats key.
            "built_at": data.get("built_at"),
        }
    return None


def _stale_by_check(
    inventory: Set[str], info: Dict[str, object], output_dir: Path
) -> Optional[str]:
    """Return a human-readable staleness reason, or None when fresh.

    Tier 1/2 operate purely on sets; tier 3 samples mtimes against the build
    timestamp recorded at index build time.
    """
    if info["total"] != len(inventory):
        return f"count mismatch: index={info['total']} disk={len(inventory)}"
    idx_keys = info["keys"]
    if idx_keys is not None and idx_keys != inventory:
        added = inventory - idx_keys
        removed = idx_keys - inventory
        return f"manifest mismatch: +{len(added)} -{len(removed)}"
    # Tier 3: mtime sampling (only when a build timestamp exists)
    built_at = info.get("built_at")
    if built_at and inventory:
        try:
            built = float(built_at)
        except (TypeError, ValueError):
            return None
        sample = random.sample(sorted(inventory), min(_MTIME_SAMPLE, len(inventory)))
        for rel in sample:
            try:
                if (output_dir / rel).stat().st_mtime > built:
                    return f"stale content: {rel} modified after index build"
            except OSError:
                continue
    return None


def has_search_index(output_dir: Path) -> bool:
    """True when a usable search index already exists on disk.

    Mirrors ensure_fresh's info probing (SQLite-with-data first, legacy JSON
    fallback).  Callers that previously used ``idx_path.exists()`` against
    ``SEARCH_INDEX_FILENAME`` (a name that is never written) should switch to
    this — the real index lives in ``.codewiki/analysis_cache.db``.
    """
    return (
        _read_sqlite_index_info(output_dir) is not None
        or _read_json_index_info(output_dir) is not None
    )


def ensure_fresh(
    output_dir: Path,
    *,
    force: bool = False,
    session: Any = None,
) -> bool:
    """Validate the search index against disk and rebuild when stale.

    Called at the wiki_search.search() entry (sessionless path) and by
    handle_query_wiki when a usable index already exists (session or not) —
    replacing the old "always full-rebuild on session" behaviour with the
    same cheap three-tier gate. Returns True when the index was (re)built and
    can be used; False means stale-and-unrecoverable — the caller should flag
    ``index_stale`` but still search.

    Cheap by design: throttled to one inventory scan per output_dir per 60s
    (a stale verdict bypasses the throttle so the rebuild is attempted
    immediately on the next call after files change).

    ``session`` is forwarded to build_full_index so a rebuild reuses the
    active session's shared AnalysisCache connection instead of opening a
    second writer against the same db file.
    """
    od = Path(output_dir)
    key = str(od)
    now = time.time()
    if not force:
        prev = _last_check.get(key)
        if prev is not None and (now - prev[0]) < _CHECK_INTERVAL_S and not prev[1]:
            return True  # recently checked and fresh

    inventory = scan_disk_inventory(od)
    stale_reason = None
    info = _read_sqlite_index_info(od)
    if info is None:
        info = _read_json_index_info(od)
    if info is None:
        # No index at all — not "stale", the caller's build-if-missing path
        # handles this. Record as fresh to avoid re-scanning every call.
        _last_check[key] = (now, False)
        return True
    stale_reason = _stale_by_check(inventory, info, od)

    if stale_reason is None:
        _last_check[key] = (now, False)
        return True

    logger.warning("index stale (%s) — rebuilding: %s", key, stale_reason)
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index

        build_full_index(od, session=session)
        # T3: wiki/index.md is a full-rewrite aggregate too — after a pull
        # conflict (either side wins), a manifest mismatch here means the
        # catalog is stale. Rebuild it alongside the search index.
        try:
            from codewiki.mcp.tools.wiki_index import rebuild_index

            rebuild_index(str(od))
        except Exception as e:
            logger.debug("index.md rebuild skipped: %s", e)
        _last_check[key] = (now, False)
        return True
    except Exception as e:
        logger.warning("index rebuild failed, searching with stale index: %s", e)
        _last_check[key] = (now, True)
        return False


def mark_index_built(output_dir: Path) -> None:
    """Record the build timestamp so tier-3 (mtime sampling) has a baseline.

    Called from build_full_index on every successful build. For the SQLite
    path the stamp lands in search_stats; for JSON it is persisted in the
    index file (added by _save_index via the version dict).
    """
    now = str(time.time())
    od = Path(output_dir)
    # SQLite path (standalone db, if present)
    try:
        from codewiki.mcp.tools.wiki_search import _resolve_db_path
        import sqlite3

        db_path = _resolve_db_path(od)
        if db_path is not None and db_path.exists():
            conn = sqlite3.connect(
                str(db_path), timeout=30.0
            )  # Team-layout Phase 2: explicit busy timeout
            try:
                conn.execute(
                    "INSERT INTO search_stats VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (_INDEX_BUILT_KEY, now),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.debug("freshness: sqlite built-stamp write failed: %s", e)
    # JSON path: stamp is written by _save_index callers via idx.built_at
    _last_check[str(od)] = (time.time(), False)
