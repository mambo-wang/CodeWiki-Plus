"""Session file workspace -- write large analysis artifacts to disk.

Instead of transmitting bulky data through the MCP stdio channel, the
server writes analysis results (component index, leaf nodes, source code,
etc.) to a per-session directory on disk.  The IDE agent then reads these
files directly using its own file-access capabilities.

Directory layout (relative to ``repo_path``)::

    .codewiki/sessions/{session_id}/
        component_index.json
        leaf_nodes.json
        languages.json
        changes.json
        summary.json
        processing_order.json
        sources/
            {sanitized_component_id}.src
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Base directory under repo_path
_WORKSPACE_REL = Path(".codewiki") / "workspace"


def _safe_filename(component_id: str) -> str:
    """Sanitize a component ID for use as a filename.

    Component IDs look like ``src/main.py::MyClass``.  We replace any
    character that is not a word char, hyphen, or dot with ``__``.
    A short hash suffix is appended to prevent collisions when different
    component IDs sanitize to the same string (e.g. ``src/a-b.py`` vs
    ``src/a_b.py``).

    The sanitized part is truncated so the filename stays under the
    common 255-byte NAME_MAX (separator chars expand to two chars each,
    so deep paths overflow it easily); the hash suffix keeps truncated
    names unique.
    """
    sanitized = re.sub(r"[^\w\-.]", "__", component_id)[:180]
    hash_suffix = hashlib.sha1(component_id.encode()).hexdigest()[:8]
    return f"{sanitized}_{hash_suffix}.src"


class SessionWorkspace:
    """Manages the on-disk workspace for a single MCP session."""

    def __init__(self, repo_path: Path, session_id: str = "") -> None:
        # Use a fixed directory per repo instead of per-session.
        # Tools write to uniquely-named files (dependencies.json, etc.)
        # and the MCP server is single-threaded per repo, so no conflicts.
        rp = Path(repo_path).resolve()
        try:
            from codewiki.mcp.tools.workspace_layout import resolve_workspace

            resolution = resolve_workspace(rp)
            if resolution.centralized:
                # Centralized member repos are pure code: their session
                # workspace lives at <ws>/.codewiki/<repo>/workspace.
                first = rp.relative_to(resolution.root).parts[0]
                self.root = resolution.root / ".codewiki" / first / "workspace"
            else:
                self.root = rp / _WORKSPACE_REL
        except Exception:  # pragma: no cover - layout must never break analysis
            self.root = rp / _WORKSPACE_REL
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sources").mkdir(exist_ok=True)
        logger.debug("Workspace at %s", self.root)

    # -- writers ----------------------------------------------------------

    def write_json(self, name: str, data: Any, *, compact: bool = False) -> Path:
        """Write *data* as JSON and return the file path.

        When *compact* is True, uses minimal separators (no extra
        whitespace), reducing file size by ~30-40% — useful for very
        large dependency graphs.
        """
        p = self.root / name
        if compact:
            p.write_text(
                json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
            )
        else:
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def write_component_source(
        self,
        component_id: str,
        source: str,
        language: str = "",
    ) -> Path:
        """Write a single component's source code to the ``sources/`` dir."""
        p = self.root / "sources" / _safe_filename(component_id)
        header = f"// Component: {component_id}\n// Language: {language}\n"
        p.write_text(header + source, encoding="utf-8")
        return p

    def write_text(self, name: str, data: str) -> Path:
        """Write arbitrary text to a workspace file and return the path."""
        p = self.root / name
        p.write_text(data, encoding="utf-8")
        return p

    # -- readers ----------------------------------------------------------

    def read_json(self, name: str) -> Any:
        """Read a JSON file from the workspace.  Returns ``None`` if missing."""
        p = self.root / name
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    # -- cleanup ----------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up per-session artefacts (sources/).

        The shared workspace JSON files (component_list, dependencies,
        etc.) are kept across sessions — only transient source excerpts
        written by ``read_code_components`` are removed.
        """
        sources_dir = self.root / "sources"
        if sources_dir.exists():
            count = 0
            for f in sources_dir.iterdir():
                if f.is_file():
                    f.unlink()
                    count += 1
            if count:
                logger.debug("Cleaned up %d source files from %s", count, sources_dir)

    @staticmethod
    def cleanup_legacy_sessions(repo_path: Path) -> int:
        """Remove legacy per-session directories under .codewiki/sessions/.

        Returns the number of directories removed.
        """
        sessions_dir = repo_path / ".codewiki" / "sessions"
        if not sessions_dir.exists():
            return 0
        count = 0
        for entry in sessions_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
                count += 1
        try:
            sessions_dir.rmdir()
        except OSError:
            pass
        if count:
            logger.info("Cleaned up %d legacy session directories", count)
        return count
