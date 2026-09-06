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
2. ``repo_path`` → ``workspace_layout.default_output_dir`` (layout-aware:
   centralized members route to the workspace-root shared corpus, everything
   else keeps ``<repo>/repowiki``).

Raises ``ValueError`` when neither a session nor ``repo_path`` is available —
the retired ``output_dir`` parameter is ignored (with a warning) on all paths.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState
from codewiki.src.store import KnowledgeStore

logger = logging.getLogger(__name__)


def resolve_output_dir(
    session: Optional[SessionState],
    arguments: Dict[str, Any],
) -> Path:
    """Resolve the knowledge-base directory for this invocation.

    output_dir is a pure function of repo_path under the active layout
    (:func:`workspace_layout.default_output_dir`) and is never persisted — an
    external invocation cannot steer where a repo's knowledge lands.

    An active session's ``output_dir`` (already layout-derived at session
    creation) wins; otherwise ``repo_path`` derives the layout-aware directory.
    A caller-supplied explicit ``output_dir`` that differs from the derivation
    is ignored with a warning — a compat shim for callers that still send the
    retired parameter.
    """
    if session is not None:
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    if rp:
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        derived = default_output_dir(Path(rp).expanduser().resolve())
        if od:
            _warn_ignored_output_dir(rp, od, derived)
        return derived
    raise ValueError(
        "repo_path is required (or pass an active session). "
        "Provide repo_path=<repo root> to locate the knowledge base."
    )


def _warn_ignored_output_dir(rp: str, od: Any, derived: Path) -> None:
    """Warn once per invocation when a write call still sends output_dir."""
    from codewiki.mcp.tools.workspace_layout import is_foreign_output_dir

    if is_foreign_output_dir(rp, od) is not None:
        logger.warning(
            "resolve_output_dir: ignoring explicit output_dir=%r on a write "
            "path; layout derives %s from repo_path=%r (output_dir retired "
            "on write tools)",
            od,
            derived,
            rp,
        )


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
