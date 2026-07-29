from pathlib import Path
import os

# Maximum file size for source code reading (2MB).
# Files larger than this (minified JS, generated protobuf, data blobs)
# are skipped to prevent OOM on large legacy projects.
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB

def _inside(base: Path, target: Path) -> bool:
    base_r = base.resolve()
    try:
        target_r = target.resolve()
        return target_r.is_relative_to(base_r)  # py>=3.9
    except AttributeError:
        return str(target.resolve()).startswith(str(base_r))

def assert_safe_path(base_dir: Path, target: Path):
    # Block symlinks (file or dir)
    if target.is_symlink():
        raise PermissionError(f"Symlink blocked: {target}")
    # Block paths that escape repo
    if not _inside(base_dir, target):
        raise PermissionError(f"Path escapes repo: {target} -> {target.resolve()}")

def safe_open_text(base_dir: Path, target: Path, encoding="utf-8"):
    assert_safe_path(base_dir, target)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(target), flags)
    try:
        # Guard against OOM from minified/generated files (e.g. bundled JS, protobuf output)
        stat = os.fstat(fd)
        if stat.st_size > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large ({stat.st_size / 1024 / 1024:.1f}MB > {MAX_FILE_SIZE / 1024 / 1024:.0f}MB): {target}"
            )
        with os.fdopen(fd, "r", encoding=encoding, errors="replace") as f:
            return f.read()
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def is_likely_minified(content: str) -> bool:
    """Detect minified/bundled code that slips past the size guard.

    Heuristics (any one triggers):
    1. Average line length > 300 chars (normal code rarely exceeds 120).
    2. File > 10KB but has fewer than 1 newline per 500 chars.
    3. Longest single line > 5000 chars AND total lines < 20.

    Returns True if the content is likely machine-generated/minified.
    """
    if not content:
        return False

    size = len(content)
    # Small files are never problematic
    if size < 4096:
        return False

    lines = content.split("\n")
    num_lines = len(lines)

    # Heuristic 1: average line length
    avg_line_len = size / max(num_lines, 1)
    if avg_line_len > 300:
        return True

    # Heuristic 2: very low newline density for a sizable file
    if size > 10240 and num_lines < size / 500:
        return True

    # Heuristic 3: extremely long lines with very few total lines
    if num_lines < 20:
        max_line_len = max(len(line) for line in lines)
        if max_line_len > 5000:
            return True

    return False
