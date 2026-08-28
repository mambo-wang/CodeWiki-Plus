"""Workspace layout resolution (centralized vs colocated knowledge layouts).

Single routing seam for the centralized-wiki-layout feature (see
``.scratch/centralized-wiki-layout/spec.md``): every tool that routes
knowledge by ``output_dir`` consults :func:`resolve_workspace` instead of
walking directories on its own.

Guardrails:

1. **Discovery signal is ``<dir>/repowiki/.meta/workspace.json`` only.**
   The bootstrap registration tables are *not* discovery signals — a
   directory without a layout config is a v5.5.0 workspace or a plain
   directory and keeps status-quo behaviour.
2. **A hit still requires membership.**  The repo's directory name (the
   first path component under the workspace root) must appear in the
   bootstrap registration table; unregistered directories (e.g. a stray
   clone inside a workspace tree) are never routed centrally.
3. **Tri-state fallback.**  No workspace found / not a member /
   ``colocated`` layout all mean "keep the status-quo path
   (``repo_path/repowiki``)".
4. **Results are cached** per resolved path for the process lifetime
   (:func:`clear_cache` for tests).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

LAYOUT_COLOCATED = "colocated"
LAYOUT_CENTRALIZED = "centralized"
VALID_LAYOUTS = (LAYOUT_COLOCATED, LAYOUT_CENTRALIZED)

#: Location of the machine-readable layout config, relative to the root.
CONFIG_RELPARTS = ("repowiki", ".meta", "workspace.json")

_cache: dict[str, "WorkspaceResolution"] = {}


@dataclass(frozen=True)
class WorkspaceResolution:
    """Outcome of resolving a directory against workspace layout rules."""

    root: Path | None
    layout: str
    member: bool

    @property
    def centralized(self) -> bool:
        """True when centralized routing must be applied for this path."""
        return self.root is not None and self.member and self.layout == LAYOUT_CENTRALIZED


def clear_cache() -> None:
    """Drop all cached resolutions (tests and config changes)."""
    _cache.clear()


def find_workspace_root(start: Path) -> Path | None:
    """Walk upward from *start* looking for a workspace layout config.

    Only ``repowiki/.meta/workspace.json`` counts as a signal; stops at the
    filesystem root.  Returns the workspace root directory or None.
    """
    current = start.resolve()
    while True:
        if current.joinpath(*CONFIG_RELPARTS).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def read_layout_value(config_path: Path) -> str | None:
    """Return the stored ``wiki_layout`` value, or None.

    None covers every degraded case: file missing, unreadable, not a JSON
    object, or an unknown value.  Callers decide what None means for them
    (lenient fallback during resolution; conflict detection during init).
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    layout = data.get("wiki_layout")
    return layout if layout in VALID_LAYOUTS else None


def read_layout(workspace_root: Path) -> str:
    """Read ``wiki_layout`` from the workspace config (lenient)."""
    config_path = workspace_root.joinpath(*CONFIG_RELPARTS)
    layout = read_layout_value(config_path)
    if layout is None and config_path.is_file():
        logger.warning(
            "unreadable or invalid workspace config %s; assuming %s",
            config_path,
            LAYOUT_COLOCATED,
        )
    return layout or LAYOUT_COLOCATED


def resolve_workspace(repo_path: Union[str, Path]) -> WorkspaceResolution:
    """Resolve *repo_path* against the workspace layout rules.

    See the module docstring for the guardrails.  Callers should branch on
    :attr:`WorkspaceResolution.centralized`: everything else (single repos,
    unregistered directories, colocated workspaces) keeps the status-quo
    ``repo_path/repowiki`` behaviour.
    """
    start = Path(repo_path).resolve()
    key = str(start)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    root = find_workspace_root(start)
    if root is None:
        resolution = WorkspaceResolution(root=None, layout=LAYOUT_COLOCATED, member=False)
    else:
        # Lazy import: workspace_bootstrap imports this module at top level
        # (layout constants), so the reverse edge must not exist at load time.
        from codewiki.mcp.tools.workspace_bootstrap import read_registration_table_names

        layout = read_layout(root)
        rel = start.relative_to(root)
        first = rel.parts[0] if rel.parts else None
        member = first is not None and first in read_registration_table_names(root)
        resolution = WorkspaceResolution(root=root, layout=layout, member=member)

    _cache[key] = resolution
    return resolution
