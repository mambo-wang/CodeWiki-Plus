"""Tests for team-layout Phase 2 (§5.3): concurrency收口.

Covers:
* locked_rmw / locked_write — no lost update under real thread contention;
* gc_bindings — stale one-shot vouchers swept, undateable ones kept;
* create_task duplicate rejection still works through the locked path;
* schema _write_yaml now goes through atomic_write (tmp + replace).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codewiki.mcp.tools.task_manager import handle_create_task
from codewiki.src.store import KnowledgeStore, atomic_write, locked, locked_rmw, locked_write


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


def test_locked_rmw_no_lost_update_under_threads(tmp_path):
    """N threads × +1 increments on one file — all must survive.

    With a bare read-modify-write this fails catastrophically (lost
    updates); the sidecar lock must make every increment durable.
    """
    target = tmp_path / "counter.json"
    target.write_text("0", encoding="utf-8")
    n_threads, n_incr = 8, 25

    def bump():
        for _ in range(n_incr):
            locked_rmw(
                target,
                lambda t: str(int(t) + 1),
            )

    threads = [threading.Thread(target=bump) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert target.read_text(encoding="utf-8") == str(n_threads * n_incr)


def test_locked_rmw_abort_returns_none_without_write(tmp_path):
    target = tmp_path / "keep.txt"
    target.write_text("original", encoding="utf-8")
    result = locked_rmw(target, lambda t: None)  # None → read-only peek
    assert result is None
    assert target.read_text(encoding="utf-8") == "original"


def test_locked_write_creates_and_replaces(tmp_path):
    target = tmp_path / "sub" / "f.md"
    locked_write(target, "v1")
    assert target.read_text(encoding="utf-8") == "v1"
    locked_write(target, "v2")
    assert target.read_text(encoding="utf-8") == "v2"
    # no temp file leftovers
    assert list(target.parent.glob("*.tmp.*")) == []


def test_locked_write_whole_file_wins(tmp_path):
    """Concurrent whole-file writers leave one complete write (atomicity)."""
    target = tmp_path / "w.log"
    barrier = threading.Barrier(4)

    def write_big(idx: int):
        barrier.wait()
        for _ in range(10):
            locked_write(target, f"writer-{idx}-" + "x" * 500)

    threads = [threading.Thread(target=write_big, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    content = target.read_text(encoding="utf-8")
    assert content.startswith("writer-") and content.endswith("x" * 500)
    assert "xx" in content  # payload intact, not truncated


def test_gc_bindings_sweeps_only_stale(tmp_path):
    ks = KnowledgeStore(tmp_path)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    ks.write_binding("old-session", "task-a")  # then age it manually
    p = ks.bindings_dir / "old-session.json"
    p.write_text(json.dumps({"task_id": "task-a", "bound_at": old.isoformat()}), encoding="utf-8")
    ks.write_binding("fresh-session", "task-b")  # bound_at = now
    # undateable voucher: no bound_at → must be kept
    (ks.bindings_dir / "corrupt.json").write_text('{"task_id": "x"}', encoding="utf-8")

    removed = ks.gc_bindings(max_age_days=30)
    assert removed == 1
    assert not (ks.bindings_dir / "old-session.json").exists()
    assert (ks.bindings_dir / "fresh-session.json").exists()
    assert (ks.bindings_dir / "corrupt.json").exists()


def test_gc_bindings_noop_without_dir(tmp_path):
    assert KnowledgeStore(tmp_path).gc_bindings() == 0


def test_create_task_duplicate_still_rejected(tmp_path):
    out = str(tmp_path)
    r1 = json.loads(handle_create_task({"output_dir": out, "title": "Alpha Task"}, _StubStore()))
    assert r1.get("ok") is True
    r2 = json.loads(handle_create_task({"output_dir": out, "title": "Alpha Task"}, _StubStore()))
    assert "error" in r2 and "already exists" in r2["error"]


def test_atomic_write_replaces_via_tmp(tmp_path):
    target = tmp_path / "t.md"
    atomic_write(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_locked_not_reentrant_by_design(tmp_path):
    """locked() is NOT reentrant — a nested acquire on the same path from the
    SAME thread would block forever.  Document the contract by proving the
    second acquire blocks (a helper thread times out) — call sites must hold
    one lock per RMW sequence (doc_writer wraps its whole post-processing
    chain in a single lock, never nested).
    """
    target = tmp_path / "x.md"
    target.write_text("x", encoding="utf-8")
    with locked(target):
        started = threading.Event()
        got_in = threading.Event()

        def try_acquire():
            started.set()
            # blocks on the same path-keyed lock held by the main thread —
            # which is exactly the "not reentrant" contract
            with locked(target):
                got_in.set()

        t = threading.Thread(target=try_acquire)
        t.daemon = True
        t.start()
        assert started.wait(timeout=1.0), "helper thread never started"
        assert not got_in.wait(timeout=0.5), "second acquire must block while held"
    t.join(timeout=2)
    assert got_in.wait(timeout=2), "lock released after the with-block — helper proceeds"


# --------------------------------------------------------------------------- #
# Review blind-spot coverage: REAL concurrency tests (Phase 2 review)
# --------------------------------------------------------------------------- #

_SUBPROC_WORKER = """
import sys
from pathlib import Path
from codewiki.src.store import locked_rmw

target = Path(sys.argv[1])
n = int(sys.argv[2])
for _ in range(n):
    locked_rmw(target, lambda t: str(int(t) + 1))
print(target.read_text(encoding="utf-8"))
"""


def test_locked_rmw_across_processes(tmp_path):
    """Two real subprocesses incrementing one file — the OS lock layer
    (msvcrt/fcntl, not just the thread layer) must serialise them.

    This is the actual Phase 2 threat model: multiple stdio MCP server
    processes writing the same repowiki.
    """
    import os
    import subprocess
    import sys

    target = tmp_path / "counter.txt"
    target.write_text("0", encoding="utf-8")
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"

    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _SUBPROC_WORKER, str(target), "15"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        for _ in range(2)
    ]
    outs = [p.communicate(timeout=60) for p in procs]
    for p, (out, err) in zip(procs, outs):
        assert p.returncode == 0, err.decode("utf-8", "replace")
    # 2 processes x 15 increments — any lost update fails this
    assert target.read_text(encoding="utf-8") == "30"


def test_append_log_concurrent_same_day(tmp_path):
    """Concurrent append_log calls on one day: exactly one ``##`` section
    header, every entry present (no interleave, no lost entry)."""
    from codewiki.mcp.tools.wiki_index import append_log

    n_threads, n_entries = 4, 10

    def append(idx: int):
        for i in range(n_entries):
            append_log(tmp_path, "op", f"entry-{idx}-{i}")

    threads = [threading.Thread(target=append, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    import glob

    shards = glob.glob(str(tmp_path / "wiki" / "log-*.md"))
    assert len(shards) == 1
    text = Path(shards[0]).read_text(encoding="utf-8")
    assert text.count("## ") == 1  # single day section, no duplicated headers
    for idx in range(n_threads):
        for i in range(n_entries):
            assert f"entry-{idx}-{i}" in text  # nothing lost


def test_apply_status_concurrent_keeps_frontmatter_valid(tmp_path):
    """Concurrent confirm/reject on the same note: both complete, the file
    ends up with valid frontmatter carrying one of the two statuses."""
    import yaml

    from codewiki.mcp.tools.knowledge_loop import _apply_status_to_file

    note = tmp_path / "note.md"
    note.write_text(
        "---\ntype: general\ntitle: t\nstatus: draft\n---\n\nbody\n",
        encoding="utf-8",
    )
    errors = []

    def flip(status: str):
        try:
            _apply_status_to_file(note, tmp_path, status, verified_by="human:x")
        except Exception as e:  # pragma: no cover - surfaced via errors list
            errors.append(e)

    t1 = threading.Thread(target=flip, args=("stable",))
    t2 = threading.Thread(target=flip, args=("deprecated",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors
    text = note.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    fm = yaml.safe_load(text[3:end])
    assert fm["status"] in ("stable", "deprecated")


def test_create_task_concurrent_same_title_one_wins(tmp_path):
    """Two threads creating the same-titled task: exactly one succeeds."""
    out = str(tmp_path)

    results = []

    def create():
        results.append(
            json.loads(handle_create_task({"output_dir": out, "title": "Race"}, _StubStore()))
        )

    t1 = threading.Thread(target=create)
    t2 = threading.Thread(target=create)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    oks = [r for r in results if r.get("ok")]
    errs = [r for r in results if "error" in r]
    assert len(oks) == 1 and len(errs) == 1
    assert "already exists" in errs[0]["error"]
