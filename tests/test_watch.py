"""Tests for watch_repo — background incremental graph sync.

Covers:
* incremental refresh: modified / new / deleted files update the graph
  (and the session's component store) without re-parsing unchanged files
* polling idempotency: a second refresh after a sync reports no changes
* graceful degradation: a failing poll stops the watcher, never raises
* MCP entry point lifecycle: start → status → stop
* graph_stale attachment on query-tool responses
"""

from __future__ import annotations

import json
import time

from codewiki.mcp.tools.watch import (
    RepoWatcher,
    attach_graph_stale,
    handle_watch_repo,
)
from tests.conftest import PY_B


def _session(store, tmp_path):
    return store.find_or_restore(str(tmp_path.resolve()))


# ------------------------------------------------------------------
# Incremental refresh: modified file
# ------------------------------------------------------------------

def test_refresh_modified_file_updates_graph(analyzed_repo) -> None:
    """Editing b.py (adding a function) shows up in the session store;
    untouched files (a.py, c.py) keep their components."""
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)

    (tmp_path / "b.py").write_text(
        PY_B + "\ndef func_new():\n    return 1\n", encoding="utf-8"
    )

    watcher = RepoWatcher(session, store, interval=1.0)
    changed = watcher.refresh_once()
    assert "b.py" in changed, changed

    ids = set(session.components.keys())
    assert "b.py::func_new" in ids          # new function parsed
    assert "b.py::func_b" in ids            # old function still cached
    assert "b.py::func_other" in ids
    assert "a.py::func_a" in ids            # untouched file untouched
    assert "c.py::func_c" in ids
    assert watcher.batches == 1
    assert watcher.last_sync is not None


def test_refresh_is_idempotent(analyzed_repo) -> None:
    """After a refresh, the next poll reports zero changes (fingerprints
    updated — a git-based detector would loop forever on uncommitted edits)."""
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    (tmp_path / "b.py").write_text(
        PY_B.replace("return 42", "return 43"), encoding="utf-8"
    )

    watcher = RepoWatcher(session, store, interval=1.0)
    assert "b.py" in watcher.refresh_once()
    assert watcher.refresh_once() == []
    assert watcher.batches == 1


# ------------------------------------------------------------------
# Incremental refresh: new / deleted files
# ------------------------------------------------------------------

def test_refresh_new_file_adds_components(analyzed_repo) -> None:
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    (tmp_path / "d.py").write_text("def func_d():\n    return 4\n", encoding="utf-8")

    watcher = RepoWatcher(session, store, interval=1.0)
    changed = watcher.refresh_once()
    assert "d.py" in changed, changed
    assert "d.py::func_d" in session.components
    assert watcher.refresh_once() == []  # idempotent after fingerprint update


def test_refresh_deleted_file_removes_components(analyzed_repo) -> None:
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    (tmp_path / "a.py").unlink()

    watcher = RepoWatcher(session, store, interval=1.0)
    changed = watcher.refresh_once()
    assert "a.py" in changed, changed
    assert not any(cid.startswith("a.py::") for cid in session.components)
    assert "c.py::func_c" in session.components  # others survive
    assert watcher.refresh_once() == []  # idempotent (fingerprint row dropped)


# ------------------------------------------------------------------
# Degradation
# ------------------------------------------------------------------

def test_watcher_degrades_gracefully(analyzed_repo, monkeypatch) -> None:
    """A failing poll stops the loop and marks the watcher degraded —
    the session falls back to manual mode instead of crashing."""
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    watcher = RepoWatcher(session, store, interval=1.0)

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(watcher, "refresh_once", boom)
    watcher.start()
    deadline = time.time() + 5
    while watcher.running and time.time() < deadline:
        time.sleep(0.05)
    assert not watcher.running
    assert watcher.degraded
    assert watcher.errors == 1
    watcher.stop()


# ------------------------------------------------------------------
# MCP entry point
# ------------------------------------------------------------------

def test_handle_watch_repo_lifecycle(analyzed_repo) -> None:
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)

    # status before start
    raw = handle_watch_repo({"repo_path": str(tmp_path), "action": "status"}, store)
    parsed = json.loads(raw)
    assert parsed["watch"] is None

    # start
    raw = handle_watch_repo(
        {"repo_path": str(tmp_path), "action": "start", "interval": 1.0}, store
    )
    parsed = json.loads(raw)
    assert parsed["ok"] is True
    assert parsed["watch"]["running"] is True
    assert session.watcher is not None

    # status while running
    raw = handle_watch_repo({"repo_path": str(tmp_path), "action": "status"}, store)
    assert json.loads(raw)["watch"]["running"] is True

    # stop
    raw = handle_watch_repo({"repo_path": str(tmp_path), "action": "stop"}, store)
    parsed = json.loads(raw)
    assert parsed["watch"]["running"] is False
    assert session.watcher is None

    # start again after stop (restart works)
    raw = handle_watch_repo(
        {"repo_path": str(tmp_path), "action": "start", "interval": 1.0}, store
    )
    assert json.loads(raw)["watch"]["running"] is True
    handle_watch_repo({"repo_path": str(tmp_path), "action": "stop"}, store)


def test_handle_watch_repo_requires_session(tmp_path) -> None:
    from codewiki.mcp.session import SessionStore

    store = SessionStore()
    raw = handle_watch_repo({"repo_path": str(tmp_path), "action": "start"}, store)
    parsed = json.loads(raw)
    assert "error" in parsed


# ------------------------------------------------------------------
# graph_stale attachment on query tools
# ------------------------------------------------------------------

def test_attach_graph_stale_noop_without_watcher(analyzed_repo) -> None:
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    resp = attach_graph_stale({"ok": True}, session)
    assert resp == {"ok": True}  # unchanged


def test_attach_graph_stale_reports_stopped_and_synced(analyzed_repo) -> None:
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)

    # watcher present but not running → stale
    session.watcher = RepoWatcher(session, store, interval=1.0)
    resp = attach_graph_stale({"ok": True}, session)
    assert resp["graph_stale"] is True
    assert resp["graph_sync"]["reason"] == "watch stopped"

    # running and synced → fresh
    session.watcher.running = True
    session.watcher.last_sync = time.time()
    resp = attach_graph_stale({"ok": True}, session)
    assert resp["graph_stale"] is False
    assert resp["graph_sync"]["batches"] == 0

    # degraded → stale with hint
    session.watcher.running = False
    session.watcher.degraded = True
    resp = attach_graph_stale({"ok": True}, session)
    assert resp["graph_stale"] is True
    assert "re-run analyze_repo" in resp["graph_sync"]["hint"]


def test_analyze_impact_attaches_freshness(analyzed_repo) -> None:
    """analyze_impact's MCP response carries graph_stale while watch is on."""
    tmp_path, store = analyzed_repo
    session = _session(store, tmp_path)
    session.watcher = RepoWatcher(session, store, interval=1.0)  # not running

    from codewiki.mcp.tools.impact import handle_analyze_impact

    raw = handle_analyze_impact(
        {
            "repo_path": str(tmp_path),
            "component_ids": ["b.py::func_b"],
            "direction": "depended_by",
        },
        store,
    )
    parsed = json.loads(raw)
    assert "error" not in parsed
    assert parsed["graph_stale"] is True
    assert parsed["graph_sync"]["reason"] == "watch stopped"
