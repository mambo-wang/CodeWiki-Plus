"""Code-evidence helpers: content-hash anchoring of ``repo://`` code regions.

Borrowed from langchain-ai/openwiki's Grounded Claims (evidence versioning by
content hash rather than git SHA).  We keep only the data model: a wiki page's
frontmatter ``sources`` list carries a ``repo://<rel>#L<start>-L<end>``
resource plus the content hash observed when the page was written.  A lint
check re-reads the region and flags drift so humans can review — evidence
drives a *review reminder*, never an automatic rewrite.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# repo://<rel-path>[#L<start>[-L<end>]]
_RESOURCE_RE = re.compile(r"^repo://(?P<path>[^#]+?)(?:#L(?P<start>\d+)(?:-L(?P<end>\d+))?)?$")

_HASH_PREFIX = "sha256:"


def _sha256(data: str) -> str:
    return _HASH_PREFIX + hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_region_hash(path: Path, start: int, end: int) -> str:
    """Content hash of the 1-indexed, inclusive line range ``start..end``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = max(1, start)
    region = lines[start - 1 : end] if start - 1 < len(lines) else []
    return _sha256("\n".join(region))


def compute_file_hash(path: Path) -> str:
    """Content hash of the whole file."""
    return _sha256(path.read_text(encoding="utf-8", errors="replace"))


def resource_for(rel_path: str, start: int, end: int) -> str:
    """Canonical evidence resource URI (repo-relative posix path)."""
    return f"repo://{rel_path}#L{start}-L{end}"


def parse_resource(resource: str) -> Optional[Tuple[str, int, int]]:
    """Parse ``repo://<rel>[#L<start>[-L<end>]]`` → (rel_path, start, end).

    Returns ``None`` when *resource* is not a repo evidence URI.  A missing
    line range yields ``(rel, 1, 1)``; callers then treat it as file-level.
    """
    m = _RESOURCE_RE.match(resource)
    if not m:
        return None
    rel = m.group("path")
    start = int(m.group("start")) if m.group("start") else 0
    end = int(m.group("end")) if m.group("end") else start
    return rel, start, end


def make_entry(rel_path: str, start: int, end: int, content_hash: str) -> Dict[str, Any]:
    """Build an OKF ``sources`` evidence entry (idempotent key = resource).

    ``start <= 0`` denotes a whole-file resource (no ``#L`` range).
    """
    if start <= 0:
        resource = f"repo://{rel_path}"
    else:
        resource = resource_for(rel_path, start, end)
    return {"id": resource, "resource": resource, "content_hash": content_hash}


def hash_resource(resource: str, repo_root: Path) -> Optional[str]:
    """Compute the current content hash for *resource* against *repo_root*.

    Returns ``None`` when the resource is malformed or the file is missing.
    """
    parsed = parse_resource(resource)
    if parsed is None:
        return None
    rel, start, end = parsed
    target = repo_root / rel
    if not target.is_file():
        return None
    if start <= 0:
        return compute_file_hash(target)
    return compute_region_hash(target, start, end)


def verify_entry(entry: Dict[str, Any], repo_root: Path) -> str:
    """Classify an evidence ``sources`` entry against the current tree.

    Returns one of ``ok`` / ``stale`` / ``missing`` / ``unresolvable``.
    ``ok`` means the referenced code still hashes to the recorded value.
    """
    resource = entry.get("resource") if isinstance(entry, dict) else None
    if not isinstance(resource, str) or not resource.startswith("repo://"):
        return "unresolvable"
    current = hash_resource(resource, repo_root)
    if current is None:
        return "unresolvable" if parse_resource(resource) is None else "missing"
    return "ok" if current == entry.get("content_hash") else "stale"
