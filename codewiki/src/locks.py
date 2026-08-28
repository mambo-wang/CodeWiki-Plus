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
"""

from __future__ import annotations

import logging
import os
import threading
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


@contextmanager
def file_lock(filepath: Union[str, Path]) -> Iterator[IO[str]]:
    """Hold an exclusive lock bound to *filepath* for the ``with`` block.

    Yields the UTF-8 text handle that holds the lock; perform all reads and
    writes through it.  The file is created if missing.
    """
    path_key = str(Path(filepath).resolve())
    with _lock_for(path_key):
        fd = os.open(str(filepath), os.O_RDWR | os.O_CREAT, 0o666)
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
