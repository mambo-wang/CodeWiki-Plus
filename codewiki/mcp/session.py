"""Session state management for the CodeWiki MCP Server.

Each ``analyze_repo`` call creates a new session that caches the analysis
results (components, leaf nodes, etc.) in memory.  Subsequent tool calls
reference the session by ``session_id`` to read code, write docs, and
manage the module tree without re-parsing the repository.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.src.be.dependency_analyzer.models.core import Node


# Sessions auto-expire after this many seconds of inactivity.
_SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours


@dataclass
class SessionState:
    """Mutable state shared across all MCP tool calls within a session."""

    session_id: str
    repo_path: str
    output_dir: str
    components: Dict[str, Node]
    leaf_nodes: List[str]
    module_tree: Dict[str, Any] = field(default_factory=dict)
    registry: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update the last-accessed timestamp."""
        self.last_accessed = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > _SESSION_TTL_SECONDS


class SessionStore:
    """In-memory store for all active MCP sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def create(
        self,
        repo_path: str,
        output_dir: str,
        components: Dict[str, Node],
        leaf_nodes: List[str],
    ) -> SessionState:
        """Create a new session and return it."""
        session_id = uuid.uuid4().hex[:12]
        state = SessionState(
            session_id=session_id,
            repo_path=repo_path,
            output_dir=output_dir,
            components=components,
            leaf_nodes=leaf_nodes,
        )
        self._sessions[session_id] = state
        self._purge_expired()
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        """Return the session or ``None`` if not found / expired."""
        state = self._sessions.get(session_id)
        if state is None:
            return None
        if state.is_expired:
            del self._sessions[session_id]
            return None
        state.touch()
        return state

    def remove(self, session_id: str) -> bool:
        """Remove a session.  Returns True if it existed."""
        return self._sessions.pop(session_id, None) is not None

    def _purge_expired(self) -> None:
        """Remove all expired sessions."""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]
