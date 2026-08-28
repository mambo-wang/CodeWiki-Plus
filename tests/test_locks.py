"""Tests for codewiki.src.locks: cross-platform file-lock primitive.

The primitive must serialize both same-process threads and separate
processes around a read-modify-write sequence on a shared file — the
concurrency contract the centralized-layout shared pool relies on.

All I/O inside the locked block goes through the yielded handle (required
on Windows: msvcrt.locking blocks every other handle, same process or not).
"""

from __future__ import annotations

import multiprocessing
import threading

from codewiki.src.locks import file_lock

N_THREADS = 8
N_ITER = 25


def test_threaded_appends_no_interleaving(tmp_path):
    target = tmp_path / "pool.md"

    def worker(tid):
        for i in range(N_ITER):
            with file_lock(target) as f:
                f.seek(0, 2)
                f.write(f"t{tid}-{i}\n")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == N_THREADS * N_ITER
    # Every line intact (no interleaved writes), each expected line once.
    expected = {f"t{t}-{i}" for t in range(N_THREADS) for i in range(N_ITER)}
    assert set(lines) == expected


def test_read_modify_write_counter(tmp_path):
    target = tmp_path / "counter.txt"
    target.write_text("0", encoding="utf-8")

    def worker():
        for _ in range(N_ITER):
            with file_lock(target) as f:
                value = int(f.read())
                f.seek(0)
                f.write(str(value + 1))
                f.truncate()

    threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert int(target.read_text(encoding="utf-8")) == N_THREADS * N_ITER


def _mp_increment_worker(path_str):
    # Module-level worker: must be picklable for the spawn start method.
    from codewiki.src.locks import file_lock

    for _ in range(N_ITER):
        with file_lock(path_str) as f:
            value = int(f.read())
            f.seek(0)
            f.write(str(value + 1))
            f.truncate()


def test_multiprocess_read_modify_write(tmp_path):
    target = tmp_path / "mp-counter.txt"
    target.write_text("0", encoding="utf-8")

    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_mp_increment_worker, args=(str(target),)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0

    assert int(target.read_text(encoding="utf-8")) == 4 * N_ITER


def test_lock_creates_missing_file(tmp_path):
    target = tmp_path / "fresh.md"
    with file_lock(target) as f:
        f.write("hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_append_with_lock_uses_primitive(tmp_path):
    """wiki_index._append_with_lock keeps its append contract via file_lock."""
    from codewiki.mcp.tools.wiki_index import _append_with_lock

    target = tmp_path / "log.md"
    _append_with_lock(target, "first")
    _append_with_lock(target, "second")
    assert target.read_text(encoding="utf-8") == "first\nsecond\n"
