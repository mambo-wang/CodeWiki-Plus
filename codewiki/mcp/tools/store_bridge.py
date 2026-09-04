"""MCP bridge between session/argument resolution and the pure KnowledgeStore.

``codewiki/src/store.py`` is deliberately free of MCP imports (pure filesystem
semantics over a resolved repowiki root). This module is the ONE place that
knows how to get from an MCP tool invocation — an optional active session plus
an arguments dict — to a ``KnowledgeStore``:

    store = store_for(session, arguments)

Resolution order (unifies the previously duplicated ``_resolve_output_dir``
copies across capture_conversation / distill_conversation / task_manager /
source_ingest / knowledge_loop):

1. An active session's ``output_dir`` (already fully resolved at session
   creation time, including centralized-workspace routing).
2. An explicit ``output_dir`` argument.
3. ``repo_path`` → ``workspace_layout.default_output_dir`` (layout-aware:
   centralized members route to the workspace-root shared corpus, everything
   else keeps ``<repo>/repowiki``).

Raises ``ValueError`` when none of the three is available — same contract the
old per-tool copies had, so handler error paths behave identically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState
from codewiki.src.store import KnowledgeStore


def resolve_output_dir(
    session: Optional[SessionState],
    arguments: Dict[str, Any],
) -> Path:
    """Resolve the repowiki output directory for this invocation."""
    if session is not None:
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    if od:
        return Path(od).expanduser().resolve()
    rp = arguments.get("repo_path")
    if rp:
        # Layout-aware: centralized members write into the workspace-root
        # shared corpus; single repos keep <repo>/repowiki.
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        return default_output_dir(Path(rp).expanduser().resolve())
    raise ValueError("output_dir or repo_path is required (or pass an active session).")


def store_for(
    session: Optional[SessionState],
    arguments: Dict[str, Any],
) -> KnowledgeStore:
    """A KnowledgeStore rooted at the resolved repowiki output directory."""
    return KnowledgeStore(resolve_output_dir(session, arguments))


def pending_raws_by_task(output_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """Pending (undistilled) raw conversations grouped by task_id.

    Thin re-export of ``KnowledgeStore.pending_raws_by_task`` — the seam for
    task-scoped capture/distill tooling. (Architecture review 2026-09 #5:
    previously imported from capture_conversation, a historical home that
    forced sibling tools to reach into its private namespace.)
    """
    return KnowledgeStore(output_dir).pending_raws_by_task()
