"""Session state management for the CodeWiki MCP Server.

Each ``analyze_repo`` call creates a new session. Components are stored
in SQLite via :class:`AnalysisCache`; the session holds lightweight
:class:`ComponentMeta` references and provides lazy-loading access through
a :class:`LazyComponentStore`.
"""

from __future__ import annotations

import threading, time, uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from codewiki.mcp.cache import AnalysisCache, ComponentMeta, LazyComponentStore

if TYPE_CHECKING:
    from codewiki.mcp.workspace import SessionWorkspace

_SESSION_TTL_SECONDS = 2 * 60 * 60
_MAX_SESSIONS = 10


@dataclass
class SessionState:
    """Mutable state shared across all MCP tool calls within a session.

    ``components`` is a :class:`LazyComponentStore` — iteration yields
    lightweight :class:`ComponentMeta` objects, and ``.get(cid)`` lazy-loads
    a full ``Node`` from SQLite with LRU caching.
    """

    session_id: str
    repo_path: str
    output_dir: str
    components: LazyComponentStore
    leaf_nodes: List[str]
    module_tree: Dict[str, Any] = field(default_factory=dict)
    registry: Dict[str, Any] = field(default_factory=dict)
    workspace: Optional[SessionWorkspace] = None
    cache: Optional[AnalysisCache] = None
    analyzed_commit: Optional[str] = None
    docs_written: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None: self.last_accessed = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > _SESSION_TTL_SECONDS


class SessionStore:
    """In-memory store for all active MCP sessions (thread-safe).

    Also manages a global registry of :class:`AnalysisCache` instances
    keyed by repo path, enabling cross-session cache reuse.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._caches: Dict[str, AnalysisCache] = {}  # repo_path -> cache
        self._lock = threading.Lock()

    def get_cache(self, repo_path: str) -> AnalysisCache:
        """Get or create a shared AnalysisCache for *repo_path*."""
        rp = str(repo_path)
        with self._lock:
            if rp not in self._caches:
                self._caches[rp] = AnalysisCache(repo_path)
            return self._caches[rp]

    def create(
        self,
        repo_path: str,
        output_dir: str,
        components: LazyComponentStore,
        leaf_nodes: List[str],
        workspace: Optional[SessionWorkspace] = None,
        cache: Optional[AnalysisCache] = None,
    ) -> SessionState:
        """Create a new session and return it."""
        with self._lock:
            self._purge_expired_locked()
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_accessed)
                evicted = self._sessions[oldest_id]
                if evicted.workspace is not None: evicted.workspace.cleanup()
                del self._sessions[oldest_id]
            sid = uuid.uuid4().hex[:12]
            while sid in self._sessions: sid = uuid.uuid4().hex[:12]
            state = SessionState(
                session_id=sid, repo_path=repo_path, output_dir=output_dir,
                components=components, leaf_nodes=leaf_nodes,
                workspace=workspace, cache=cache,
            )
            self._sessions[sid] = state
            return state

    def get(self, session_id: str) -> Optional[SessionState]:
        """Return the session or ``None`` if not found / expired."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None: return None
            if state.is_expired:
                if state.workspace is not None: state.workspace.cleanup()
                del self._sessions[session_id]
                return None
            state.touch()
            return state

    def remove(self, session_id: str) -> bool:
        with self._lock: return self._sessions.pop(session_id, None) is not None

    def close_cache(self, repo_path: str) -> None:
        """Close a repo's shared cache (e.g. on server shutdown)."""
        with self._lock:
            cache = self._caches.pop(str(repo_path), None)
            if cache: cache.close()

    def _purge_expired_locked(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            s = self._sessions[sid]
            if s.workspace is not None: s.workspace.cleanup()
            del self._sessions[sid]
