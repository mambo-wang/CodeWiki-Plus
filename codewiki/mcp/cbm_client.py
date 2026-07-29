"""CBM (codebase-memory-mcp) client — sync subprocess + asyncio.to_thread.

Spawns the CBM binary as a subprocess and communicates via MCP stdio protocol
(newline-delimited JSON-RPC 2.0 on stdin/stdout). Uses synchronous subprocess
I/O wrapped in asyncio.to_thread() for event-loop compatibility (asyncio's
native subprocess pipes hang on Windows 10 ProactorEventLoop).

Usage:
    from codewiki.mcp.cbm_client import get_cbm_client

    client = get_cbm_client()
    result = await client.call("trace_path", {"function_name": "foo", "direction": "inbound"})
    if result is not None:
        # CBM responded — use result dict
        ...
    else:
        # CBM unavailable or call failed — use local fallback
        ...

Configuration:
    Environment variable CODEBASE_MEMORY_MCP_PATH overrides binary discovery.
    Set CODEWIKI_CBM_DISABLED=1 to force-disable CBM delegation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Binary discovery
# ---------------------------------------------------------------------------

# Common install locations (Windows + Unix)
_CANDIDATE_PATHS = [
    Path(r"D:\software\codebase-memory-mcp\codebase-memory-mcp.exe"),
    Path(r"C:\Program Files\codebase-memory-mcp\codebase-memory-mcp.exe"),
    Path.home() / ".local" / "bin" / "codebase-memory-mcp",
    Path.home() / ".local" / "bin" / "codebase-memory-mcp.exe",
    Path("/usr/local/bin/codebase-memory-mcp"),
    Path("/opt/codebase-memory-mcp/codebase-memory-mcp"),
]


def find_cbm_binary() -> Optional[Path]:
    """Locate the CBM binary via env var, common paths, or PATH."""
    # 1. Explicit env override
    env_path = os.environ.get("CODEBASE_MEMORY_MCP_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.warning("CODEBASE_MEMORY_MCP_PATH=%s does not exist", env_path)

    # 2. Common install locations
    for candidate in _CANDIDATE_PATHS:
        if candidate.is_file():
            return candidate

    # 3. System PATH
    found = shutil.which("codebase-memory-mcp")
    if found:
        return Path(found)

    return None


def is_cbm_enabled() -> bool:
    """Check if CBM delegation is enabled and binary is available."""
    if os.environ.get("CODEWIKI_CBM_DISABLED", "").strip() in ("1", "true", "yes"):
        return False
    return find_cbm_binary() is not None


# ---------------------------------------------------------------------------
#  Synchronous JSON-RPC subprocess (runs in thread via to_thread)
# ---------------------------------------------------------------------------

_PROTOCOL_VERSION = "2024-11-05"


class _SyncCbmProcess:
    """Synchronous MCP subprocess wrapper. Thread-safe via internal lock.

    This class is designed to be called from asyncio.to_thread() — all methods
    are blocking and thread-safe.
    """

    def __init__(self, binary: Path) -> None:
        self._proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._request_id = 0
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def pid(self) -> int:
        return self._proc.pid

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def initialize(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Perform MCP initialize handshake + initialized notification."""
        result = self.request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "codewiki", "version": "5.1.0"},
        }, timeout=timeout)

        if result is not None:
            # Send initialized notification (no response expected)
            self._send_notification("notifications/initialized", {})
            self._initialized = True
            server_info = result.get("serverInfo", {})
            logger.info(
                "CBM initialized: %s v%s (PID %d)",
                server_info.get("name", "?"),
                server_info.get("version", "?"),
                self.pid,
            )
        return result

    def request(
        self, method: str, params: Dict[str, Any], timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC request, wait for matching response. Thread-safe."""
        with self._lock:
            if not self.alive:
                return None

            self._request_id += 1
            req_id = self._request_id
            message = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
            line = json.dumps(message) + "\n"

            try:
                self._proc.stdin.write(line.encode("utf-8"))  # type: ignore[union-attr]
                self._proc.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, OSError) as e:
                logger.warning("CBM stdin write failed: %s", e)
                return None

            # Read lines until we get our response (skip notifications)
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw_line = self._proc.stdout.readline()  # type: ignore[union-attr]
                except (OSError, ValueError):
                    return None
                if not raw_line:
                    return None  # EOF — process exited
                text = raw_line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue  # Skip non-JSON (debug output)

                # Skip notifications (no "id" field)
                if "id" not in msg:
                    continue

                if msg.get("id") == req_id:
                    if "error" in msg:
                        err = msg["error"]
                        logger.warning(
                            "CBM error on %s: [%s] %s",
                            method, err.get("code"), err.get("message"),
                        )
                        return None
                    return msg.get("result")

            logger.warning("CBM request %s (id=%d) timed out", method, req_id)
            return None

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        line = json.dumps(message) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))  # type: ignore[union-attr]
            self._proc.stdin.flush()  # type: ignore[union-attr]
        except (BrokenPipeError, OSError):
            pass

    def kill(self) -> None:
        """Kill the subprocess."""
        try:
            self._proc.kill()
            self._proc.wait(timeout=5)
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Async CBM Client (public API)
# ---------------------------------------------------------------------------


class CbmClient:
    """Async wrapper around _SyncCbmProcess using asyncio.to_thread().

    All public methods are async. The synchronous subprocess I/O runs in
    a thread pool to avoid blocking the event loop.
    """

    def __init__(self) -> None:
        self._sync_proc: Optional[_SyncCbmProcess] = None
        self._lock = asyncio.Lock()
        self._binary: Optional[Path] = None
        self._connect_failed = False

    @property
    def binary_path(self) -> Optional[Path]:
        if self._binary is None:
            self._binary = find_cbm_binary()
        return self._binary

    async def _ensure_connected(self) -> bool:
        """Lazily spawn CBM and perform MCP initialize handshake."""
        if self._sync_proc is not None and self._sync_proc.alive:
            return True

        if self._connect_failed:
            return False

        binary = self.binary_path
        if binary is None:
            self._connect_failed = True
            logger.info("CBM binary not found — delegation disabled")
            return False

        try:
            # Spawn in thread (subprocess.Popen is fast but let's not block)
            proc = await asyncio.to_thread(_SyncCbmProcess, binary)
            result = await asyncio.to_thread(proc.initialize)
            if result is None:
                proc.kill()
                self._connect_failed = True
                logger.warning("CBM initialize handshake failed")
                return False

            self._sync_proc = proc
            return True

        except Exception as e:
            self._connect_failed = True
            logger.warning("Failed to connect to CBM (%s): %s", binary, e)
            return False

    async def call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Call a CBM tool and return parsed JSON result, or None on failure.

        This is the primary public API. All errors are swallowed and logged —
        callers should treat None as "CBM unavailable, use local fallback".
        """
        async with self._lock:
            if not await self._ensure_connected():
                return None

            try:
                result = await asyncio.to_thread(
                    self._sync_proc.request,  # type: ignore[union-attr]
                    "tools/call",
                    {"name": tool_name, "arguments": arguments},
                    timeout_seconds,
                )
                if result is None:
                    return None

                # MCP tools/call returns {content: [{type: "text", text: "..."}]}
                content = result.get("content", [])
                if content and isinstance(content, list):
                    text = content[0].get("text", "")
                    if text:
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            return {"raw_text": text}
                # Fallback: return structured content or raw result
                if "structuredContent" in result:
                    return result["structuredContent"]
                return result

            except Exception as e:
                logger.warning("CBM %s call failed: %s", tool_name, e)
                return None

    async def list_tools(self) -> Optional[List[str]]:
        """List available CBM tool names (for diagnostics)."""
        async with self._lock:
            if not await self._ensure_connected():
                return None
            try:
                result = await asyncio.to_thread(
                    self._sync_proc.request,  # type: ignore[union-attr]
                    "tools/list",
                    {},
                    10.0,
                )
                if result is None:
                    return None
                tools = result.get("tools", [])
                return [t.get("name", "") for t in tools if t.get("name")]
            except Exception as e:
                logger.warning("CBM list_tools failed: %s", e)
                return None

    async def shutdown(self) -> None:
        """Kill the CBM subprocess."""
        async with self._lock:
            if self._sync_proc is not None:
                await asyncio.to_thread(self._sync_proc.kill)
                self._sync_proc = None
            logger.info("CBM client shut down")


# ---------------------------------------------------------------------------
#  Module-level singleton
# ---------------------------------------------------------------------------

_client: Optional[CbmClient] = None


def get_cbm_client() -> CbmClient:
    """Get the module-level CBM client singleton."""
    global _client
    if _client is None:
        _client = CbmClient()
    return _client
