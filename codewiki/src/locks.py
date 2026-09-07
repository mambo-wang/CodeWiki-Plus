"""Cross-platform file-locking primitive.

Provides :func:`file_lock` — an exclusive advisory lock bound to a file,
usable as a context manager around any read-modify-write sequence (not just
appends).  Locking layers, outermost to innermost:

1. A process-local ``threading.Lock`` per resolved path — serialises threads
   within one process on every platform (OS file locks do not arbitrate
   between handles of the same process on Windows).
2. An OS-level lock — ``fcntl.flock`` on Unix, ``msvcrt.locking`` on
   Windows — serialises separate processes (e.g. concurrent stdio MCP
   server instances writing the same shared-pool page).

**Windows constraint**: ``msvcrt.locking`` (Win32 ``LockFile``) blocks
*every* handle touching the locked region, including other handles of the
same process.  The context manager therefore yields the very handle that
holds the lock; all I/O inside the block MUST go through it.  Opening the
target a second time inside the block raises on Windows.

The file is opened read/write and created if missing; the yielded handle is
a UTF-8 text stream positioned at 0.  Callers seek/read/write/truncate as
needed (append: ``f.seek(0, 2)``).  Closing the handle releases the OS lock
on both platforms, so no explicit unlock step is required.  If no OS
primitive exists at all — or if acquiring the OS lock fails on an exotic
filesystem — the lock degrades to the thread layer alone and the operation
still proceeds (the historical append-lock "still write" semantics).

**Lock-file cleanup**: this primitive never deletes the file it locks (a
caller may lock a *content* file directly, not a sidecar — see
``wiki_index``).  Callers that know they locked a pure sidecar may
best-effort unlink it after release, **Windows only**: ``msvcrt.locking``
holds a byte-range lock on an open handle, and Windows refuses to delete a
file another process has open (sharing violation), so the unlink can only
succeed when no other holder exists — there is no inode race and the next
``file_lock`` simply re-creates the file.  On Unix the sidecar must be kept:
``flock`` locks the inode, so if a contender has already opened the file and
is blocked on the lock, unlinking the path lets a *third* process create and
lock a fresh inode while the blocked contender still waits on the old one —
two exclusive holders of "the same" lock.  ``store.locked`` implements
exactly this policy.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Union

logger = logging.getLogger(__name__)

try:
    import fcntl as _fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows
    _fcntl = None

try:
    import msvcrt as _msvcrt  # type: ignore
except ImportError:  # pragma: no cover - non-Windows
    _msvcrt = None

# Per-path process-local locks (thread layer).
_path_locks: dict[str, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for(path_key: str) -> threading.Lock:
    with _path_locks_guard:
        lock = _path_locks.get(path_key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[path_key] = lock
        return lock


def _open_lock_file(filepath: Union[str, Path], *, attempts: int = 50, delay: float = 0.01) -> int:
    """``os.open`` with a short retry on Windows delete-pending races.

    A sidecar lock file that another thread/process is releasing may be in
    the delete-pending state exactly while we open it — ``CreateFile`` then
    fails with ``ERROR_ACCESS_DENIED``/``ERROR_DELETE_PENDING``
    (``PermissionError``).  This is transient: once the unlink completes,
    ``O_CREAT`` re-creates a fresh file.  Retry briefly instead of letting a
    release/unlink race kill the caller's whole read-modify-write sequence
    (observed as lost updates under threads — 2026-09-07).
    """
    for attempt in range(attempts):
        try:
            return os.open(str(filepath), os.O_RDWR | os.O_CREAT, 0o666)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


@contextmanager
def file_lock(
    filepath: Union[str, Path], *, unlink_on_release: bool = False
) -> Iterator[IO[str]]:
    """Hold an exclusive lock bound to *filepath* for the ``with`` block.

    Yields the UTF-8 text handle that holds the lock; perform all reads and
    writes through it.  The file is created if missing.

    ``unlink_on_release=True`` (sidecar locks only — never content files)
    best-effort removes the file after releasing, **still inside the per-path
    thread-lock critical section** so a sibling thread can never be mid-open
    against the delete-pending file.  Windows only: the flag is ignored on
    Unix, where unlinking a flock'd path reintroduces the inode race.
    """
    path_key = str(Path(filepath).resolve())
    with _lock_for(path_key):
        fd = _open_lock_file(filepath)
        try:
            _acquire_os_lock(fd)
            f = os.fdopen(fd, "r+", encoding="utf-8")
            try:
                yield f
            finally:
                # Closing the handle releases flock/LockFile on both
                # platforms and closes the fd.
                f.close()
        finally:
            try:
                os.close(fd)
            except OSError:
                pass  # fd already closed via f.close()
        # Still inside the per-path thread lock: no thread of this process
        # can be mid-open here.  Cross-process contenders hitting the
        # delete-pending window are covered by _open_lock_file's retry.
        if unlink_on_release and os.name == "nt":  # pragma: no cover - platform branch
            try:
                os.unlink(str(filepath))
            except OSError:
                # Another holder keeps the file open — sharing violation.
                # The leftover is transient and bounded (≤ one file per lock
                # target, git-ignored); manual cleanup is safe once no
                # process holds the lock.
                pass


def _acquire_os_lock(fd: int) -> None:
    """Acquire the OS-level exclusive lock on *fd* (blocking).

    Failure to acquire the lock degrades gracefully: the operation proceeds
    under the thread layer alone.  This matches the historical append-lock
    behaviour ("locking may fail on some filesystems; still write") and
    keeps this prefactor free of user-visible behaviour change.
    """
    if _fcntl is not None:
        _fcntl.flock(fd, _fcntl.LOCK_EX)
        return
    if _msvcrt is not None:
        # Lock a 1-byte region at a deterministic position so every
        # contender blocks on the same bytes regardless of file length.
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            _msvcrt.locking(fd, _msvcrt.LK_LOCK, 1)
        except OSError:  # pragma: no cover - exotic filesystems
            logger.warning("could not acquire OS file lock; proceeding thread-locked only")
        return
    # No OS primitive available: thread layer alone covers this process.
