"""MCP tool: watch_repo — background incremental graph sync.

Keeps a session's dependency graph fresh without manual ``analyze_repo``
re-runs: a background thread polls the SQLite cache's fingerprint detector
every ``interval`` seconds; when files changed on disk, only those files are
re-parsed through the same incremental pipeline as ``analyze_repo`` and the
session's component store is swapped to the refreshed graph.

Design notes:

* **Idempotent polling** — the watcher calls ``cache._fp_detect()`` (mtime /
  size / content-hash comparison) instead of ``detect_changes()``, because
  the git-based detector reports *uncommitted* changes on every poll (an
  edited-but-unstaged file would trigger an endless refresh loop).  After
  each refresh the fingerprints are updated, so an unchanged worktree
  reports zero changes.
* **Deleted files** — stale fingerprint rows are dropped after a refresh
  (``cache.remove_file_fingerprints``), keeping the poll idempotent.
* **Debounce** — the poll interval *is* the debounce window: N saves within
  one interval are coalesced into a single batch by the next poll.
* **Degradation** — any unexpected failure marks the watcher ``degraded``
  and stops the loop; the session falls back to manual mode and the error is
  logged (never raised into the MCP request thread).
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.mcp.cache import AnalysisCache, ComponentMeta, LazyComponentStore
from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)


class RepoWatcher:
    """Background poller keeping a session's graph in sync with disk."""

    def __init__(self, session: Any, store: SessionStore, interval: float = 2.0) -> None:
        self.session = session
        self.store = store
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.running = False
        self.degraded = False
        self.last_sync: Optional[float] = None
        self.batches = 0
        self.errors = 0
        self.last_changed: List[str] = []

    # -- lifecycle ----------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread (no-op if already running)."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"codewiki-watch-{self.session.session_id}",
            daemon=True,
        )
        self.running = True
        self._thread.start()
        logger.info("watch started for %s (interval=%.1fs)", self.session.repo_path, self.interval)

    def stop(self) -> None:
        """Stop the polling thread and join it (safe to call twice)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 2.0)
            self._thread = None
        self.running = False
        logger.info("watch stopped for %s", self.session.repo_path)

    def status(self) -> Dict[str, Any]:
        """Snapshot of watcher state (safe to call from any thread)."""
        with self._lock:
            return {
                "running": self.running,
                "degraded": self.degraded,
                "interval": self.interval,
                "last_sync": self.last_sync,
                "seconds_since_sync": (
                    round(time.time() - self.last_sync, 1) if self.last_sync else None
                ),
                "batches": self.batches,
                "errors": self.errors,
                "last_changed_files": self.last_changed[-50:],
            }

    # -- internals ----------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                changed = self.refresh_once()
                if changed:
                    logger.info("watch: %d changed file(s) -> graph refreshed", len(changed))
            except Exception:
                self.degraded = True
                self.errors += 1
                logger.exception(
                    "Watch degraded for %s; falling back to manual mode (re-run analyze_repo)",
                    self.session.repo_path,
                )
                break
        self.running = False

    def refresh_once(self) -> List[str]:
        """Detect and apply one batch of changes; return the changed paths.

        Public so tests (and manual sync) can drive a single poll without
        waiting on the background thread.
        """
        cache = self.session.cache or self.store.get_cache(self.session.repo_path)
        # Fingerprint mode on purpose — see module docstring (idempotency).
        info = cache._fp_detect()
        changed = sorted((info or {}).get("changed_files") or [])
        if not changed:
            return []
        new_metas, new_leafs, routes = _incremental_refresh(
            self.session.repo_path,
            self.session.output_dir,
            cache,
            changed,
            analyze_options=self.session.analyze_options,
        )
        self.session.components = LazyComponentStore(cache, new_metas)
        self.session.leaf_nodes = new_leafs
        if routes:
            try:
                cache.batch_insert_routes(routes, incremental=True)
            except Exception as exc:
                logger.warning("watch: route update failed (non-fatal): %s", exc)
        with self._lock:
            self.last_sync = time.time()
            self.batches += 1
            self.last_changed = changed
        return changed


# ----------------------------------------------------------------------
# Incremental re-parse (mirrors the incremental branch of handle_analyze_repo)
# ----------------------------------------------------------------------


def _incremental_refresh(
    repo_path: str,
    output_dir: str,
    cache: AnalysisCache,
    changed_files: List[str],
    *,
    analyze_options: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, ComponentMeta], List[str], List[Dict[str, Any]]]:
    """Re-parse only *changed_files* and merge with cached components.

    Mirrors ``handle_analyze_repo``'s incremental branch but skips the
    doc/workspace/schema steps — watch only needs the graph (SQLite + the
    session's lazy store) to stay fresh.  Returns ``(metas, leaf_nodes,
    routes)`` for the refreshed graph.
    """
    import tempfile

    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    from codewiki.src.config import MAX_DEPTH, Config

    opts = analyze_options or {}
    _tmp = Path(tempfile.mkdtemp(prefix="codewiki_watch_"))
    config = Config(
        repo_path=str(repo_path), output_dir=str(_tmp),
        dependency_graph_dir=str(_tmp / "dependency_graphs"),
        docs_dir=str(output_dir), max_depth=MAX_DEPTH,
        llm_base_url="not-needed", llm_api_key="not-needed",
        main_model="unused", cluster_model="unused",
    )
    ai: Dict[str, Any] = {"doc_type": "design"}
    if opts.get("include_patterns"):
        ai["include_patterns"] = [p.strip() for p in str(opts["include_patterns"]).split(",")]
    if opts.get("exclude_patterns"):
        ai["exclude_patterns"] = [p.strip() for p in str(opts["exclude_patterns"]).split(",")]
    config.agent_instructions = ai

    # Drop stale rows for changed files; everything else stays cached.
    for cf in changed_files:
        try:
            cache.remove_by_file(cf)
        except Exception as exc:
            logger.warning("watch: remove_by_file(%s) failed: %s", cf, exc)
        try:
            cache.remove_routes_by_file(cf)
        except Exception as exc:
            logger.warning("watch: remove_routes_by_file(%s) failed (non-fatal): %s", cf, exc)

    cached_unchanged = cache.get_components_by_files(cache.get_cached_file_paths())
    skip_file_paths = {c.file_path for c in cached_unchanged.values() if c.file_path}

    builder = DependencyGraphBuilder(config)
    try:
        components, leaf_nodes, routes = builder.build_dependency_graph(
            skip_file_paths=skip_file_paths
        )
    finally:
        shutil.rmtree(str(_tmp), ignore_errors=True)

    # Merge cached unchanged components with newly parsed ones and recompute
    # leaf nodes on the full merged graph (builder only saw changed files).
    if cached_unchanged:
        for comp_id, node in cached_unchanged.items():
            if comp_id not in components:
                components[comp_id] = node
        try:
            from codewiki.src.be.dependency_analyzer.topo_sort import (
                build_graph_from_components,
                get_leaf_nodes,
            )

            graph = build_graph_from_components(components)
            raw_leafs = get_leaf_nodes(graph, components)
            valid_types = {"class", "interface", "struct"}
            available_types = {c.component_type for c in components.values()}
            if not available_types & valid_types:
                valid_types.add("function")
            leaf_nodes = [
                l
                for l in raw_leafs
                if isinstance(l, str)
                and l in components
                and components[l].component_type in valid_types
            ]
        except Exception as exc:
            logger.warning("watch: leaf-node recompute failed, keeping builder list: %s", exc)

    try:
        cache.batch_insert_components(components, leaf_nodes, incremental=True)
    except Exception as exc:
        logger.warning("watch: SQLite write failed (continuing in memory): %s", exc)

    # Fingerprints: refresh rows for files that still exist, drop rows for
    # deleted ones — both keep the next poll idempotent.
    root = Path(repo_path)
    existing = [cf for cf in changed_files if (root / cf).is_file()]
    gone = [cf for cf in changed_files if cf not in existing]
    try:
        if existing:
            cache.update_file_fingerprints(existing)
        if gone:
            cache.remove_file_fingerprints(gone)
    except Exception as exc:
        logger.warning("watch: fingerprint update failed: %s", exc)

    # Build ComponentMeta dict for the session's lazy store.
    metas: Dict[str, ComponentMeta] = {}
    for comp_id, node in components.items():
        metas[comp_id] = ComponentMeta(
            id=node.id, name=node.name, component_type=node.component_type,
            file_path=node.file_path, relative_path=node.relative_path,
            start_line=node.start_line, end_line=node.end_line,
            language=(node.language or "").strip() or "unknown", depends_on=node.depends_on,
            node_type=node.node_type, base_classes=node.base_classes,
            class_name=node.class_name, display_name=node.display_name,
            qualified_name=node.qualified_name, has_docstring=node.has_docstring,
            parameters=node.parameters,
        )
    return metas, leaf_nodes, routes


# ----------------------------------------------------------------------
# MCP handler
# ----------------------------------------------------------------------


def handle_watch_repo(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Start / stop / query the background graph watcher for *repo_path*.

    Parameters (via *arguments*)
    ----------------------------
    repo_path : str
        Repository path (session auto-restored from SQLite cache).
    action : str
        ``"start"`` (default) | ``"stop"`` | ``"status"``.
    interval : float
        Poll interval in seconds (default 2.0, minimum 1.0).  Saves within
        one interval are coalesced into a single refresh batch.
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    repo_path = arguments.get("repo_path")
    if not repo_path:
        return json.dumps({"error": "repo_path is required."})
    action = arguments.get("action", "start")

    session = resolve_session(arguments, store)
    if session is None:
        return json.dumps(
            {
                "error": (
                    "Session not found. Run analyze_repo first (or point repo_path "
                    "at a previously analyzed repository)."
                )
            }
        )

    if action == "start":
        interval = float(arguments.get("interval", 2.0))
        watcher = session.watcher
        if watcher is None:
            watcher = RepoWatcher(session, store, interval=interval)
            session.watcher = watcher
        if not watcher.running:
            watcher.start()
        return json.dumps(
            {"ok": True, "action": "start", "watch": watcher.status()},
            indent=2,
            ensure_ascii=False,
        )

    if action == "stop":
        watcher = session.watcher
        if watcher is not None:
            watcher.stop()
            session.watcher = None
        return json.dumps(
            {"ok": True, "action": "stop", "watch": {"running": False}},
            indent=2,
            ensure_ascii=False,
        )

    # status
    watcher = session.watcher
    if watcher is None:
        return json.dumps(
            {
                "ok": True,
                "action": "status",
                "watch": None,
                "hint": "Watch is not active. Call watch_repo with action='start' to enable it.",
            },
            indent=2,
            ensure_ascii=False,
        )
    return json.dumps(
        {"ok": True, "action": "status", "watch": watcher.status()},
        indent=2,
        ensure_ascii=False,
    )


# ----------------------------------------------------------------------
# Freshness hint for query tools
# ----------------------------------------------------------------------


def graph_stale_info(session: Any) -> Optional[Dict[str, Any]]:
    """Graph freshness info for query tools, or ``None`` when watch is off.

    Query tools (analyze_impact, list_components, ...) attach this to their
    response so the Agent knows whether the graph may lag behind disk:
    ``None`` → watch not active (no claim about freshness); otherwise a dict
    with ``graph_stale: bool`` plus watcher stats.
    """
    watcher = getattr(session, "watcher", None)
    if watcher is None:
        return None
    if watcher.degraded:
        return {
            "graph_stale": True,
            "reason": "watch degraded",
            "hint": "Watch mode failed; re-run analyze_repo to refresh the graph.",
        }
    if not watcher.running:
        return {"graph_stale": True, "reason": "watch stopped"}
    st = watcher.status()
    return {
        "graph_stale": False,
        "last_sync": st["last_sync"],
        "seconds_since_sync": st["seconds_since_sync"],
        "batches": st["batches"],
    }


def attach_graph_stale(response: Dict[str, Any], session: Any) -> Dict[str, Any]:
    """Attach ``graph_stale`` / ``graph_sync`` fields to a tool response.

    No-op (returns *response* unchanged) when watch mode is not active, so
    query tools can call this unconditionally.
    """
    stale = graph_stale_info(session)
    if stale is not None:
        response["graph_stale"] = stale["graph_stale"]
        response["graph_sync"] = {k: v for k, v in stale.items() if k != "graph_stale"}
    return response
