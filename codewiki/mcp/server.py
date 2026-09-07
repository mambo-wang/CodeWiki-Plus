"""
CodeWiki MCP Server.

Provides two sets of tools:

**Fine-grained tools (IDE-driven, zero LLM config):**
  - ``analyze_repo``      — Parse a repo and build a dependency graph (session-based)
  - ``read_code_components`` — Write component source code to workspace files
  - ``write_doc_file``    — Create a documentation .md file with Mermaid validation
  - ``edit_doc_file``     — Edit a documentation file (str_replace / insert / undo)
  - ``save_module_tree``  — Persist IDE agent's module clustering
  - ``get_processing_order`` — Get leaf-first documentation order
  - ``get_prompt``        — Retrieve CodeWiki's prompt templates
  - ``close_session``     — Clean up a session and workspace files

**LLM Wiki tools (knowledge management, zero LLM config):**
  - ``list_dependencies`` — Expose component dependency data for crosslinking
  - ``lint_wiki``         — Documentation-code consistency checker
  - ``ingest_note``       — File structured notes into the knowledge base
  - ``query_wiki``        — Search across docs and notes for development context

Large analysis results (component index, source code, processing order) are
written to workspace files on disk.  The IDE agent reads these files directly
instead of receiving large payloads through the MCP stdio channel.

**Legacy tools (require CodeWiki LLM config):**
  - ``generate_docs``     — Full documentation generation (black-box)
  - ``get_module_tree``   — Retrieve existing module clustering

Usage:
    python -m codewiki.mcp.server

    # Cursor / Claude Desktop config:
    {
        "mcpServers": {
            "codewiki": {
                "command": "python",
                "args": ["-m", "codewiki.mcp.server"]
            }
        }
    }

Architecture:
    This module is a thin shell.  The heavy lifting lives in:
    - ``registry.py``  — tool schemas + dispatch
    - ``prompts.py``   — MCP prompt templates
    - ``resources.py`` — MCP resources (wiki catalog, module tree, index status)
    - ``tools/*.py``   — individual tool handlers
"""

import asyncio
import atexit
import faulthandler
import logging
import os
import signal
import sys
import time
from pathlib import Path
from types import FrameType

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from codewiki import __version__
from codewiki.mcp import i18n as _i18n
from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)

# Resolve the process language once, before the Server instance (whose
# instructions payload is built below) is constructed.  stdio MCP has no
# per-request language negotiation, so one resolution per process is enough.
_i18n.init_lang()

# ---------------------------------------------------------------------------
# Global session store (lives for the lifetime of the MCP server process)
# ---------------------------------------------------------------------------
_store = SessionStore()

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

# Session instructions injected on initialize.  Full text lives in
# codewiki/mcp/locales/{zh,en}.yaml under the key `server.instructions`
# (the zh source was lifted verbatim into zh.yaml when i18n landed).
_SERVER_INSTRUCTIONS = _i18n.t("server.instructions")

server = Server(
    "codewiki",
    # Single source of truth: codewiki/__init__.py (kept in sync with
    # pyproject.toml at release time).  Never hardcode here — a stale literal
    # misleads clients that gate capabilities on the initialize handshake.
    version=__version__,
    instructions=_SERVER_INSTRUCTIONS,
)


# ===================================================================
#  Tool definitions + dispatch (delegated to registry)
# ===================================================================


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available CodeWiki MCP tools."""
    from codewiki.mcp.registry import get_all_tools

    return get_all_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to the appropriate handler via the registry."""
    from codewiki.mcp.registry import dispatch

    return await dispatch(name, arguments, _store)


# ===================================================================
#  Prompts + Resources (registered from dedicated modules)
# ===================================================================

from codewiki.mcp.prompts import register as _register_prompts
from codewiki.mcp.resources import register as _register_resources

_register_prompts(server)
_register_resources(server)


# ===================================================================
#  Process lifecycle diagnostics (silent-exit forensics)
# ===================================================================
#
# stdio MCP 服务器可能"静默死亡"：宿主关闭管道、系统在内存压力下
# 终止进程、原生崩溃——宿主侧只会看到连接关闭，没有任何线索。
# 这里装三层探针（仅在 ``__main__`` 入口启用，import 本模块无副作用）：
#   1. faulthandler — 段错误等致命故障时向 stderr 打印全部线程栈
#   2. signal hooks — SIGTERM/SIGINT/SIGBREAK 落盘记录后以 SystemExit 退出
#   3. atexit hook  — 进程正常退出时记录退出原因与运行时长
# 事件追加写入 $CODEWIKI_SERVER_LOG（默认 ~/.codewiki/server-lifecycle.log），
# 并同步回显 stderr（宿主会捕获为 [MCP-codewiki] 行）。
# 诊断方法：日志里只有 starting 而没有任何退出事件 → 进程被外部强杀
# （TerminateProcess / OOM / 断电）；以 reason=eof 收尾 → 宿主关闭了
# stdin 管道；以 reason=signal:N 收尾 → 收到了终止信号。

_LIFECYCLE_LOG = Path(
    os.environ.get("CODEWIKI_SERVER_LOG")
    or (Path.home() / ".codewiki" / "server-lifecycle.log")
)
_START_TIME = time.monotonic()
_EXIT_REASON = "unknown"


def _lifecycle_record(event: str, detail: str = "") -> None:
    """把一条生命周期事件追加到日志文件与 stderr（尽力而为，绝不抛错）。"""
    line = "%s pid=%d event=%s uptime=%.1fs%s" % (
        time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        os.getpid(),
        event,
        time.monotonic() - _START_TIME,
        (" detail=" + detail) if detail else "",
    )
    try:
        _LIFECYCLE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_LIFECYCLE_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stderr.write("[lifecycle] " + line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _handle_termination(signum: int, frame: FrameType | None) -> None:
    global _EXIT_REASON
    _EXIT_REASON = "signal:%d" % signum
    _lifecycle_record("signal-received", "signum=%d" % signum)
    raise SystemExit(128 + signum)


def _atexit_snapshot() -> None:
    _lifecycle_record("process-exit", "reason=%s" % _EXIT_REASON)


def _install_lifecycle_diagnostics() -> None:
    try:
        faulthandler.enable(file=sys.stderr)
    except Exception:
        pass
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_termination)
        except (ValueError, OSError):
            pass
    atexit.register(_atexit_snapshot)


# ===================================================================
#  Entry point
# ===================================================================


async def main():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    _install_lifecycle_diagnostics()
    _lifecycle_record(
        "starting",
        "python=%s ppid=%d argv=%r" % (sys.version.split()[0], os.getppid(), sys.argv),
    )
    try:
        asyncio.run(main())
        # server.run() 正常返回 == stdio 读流结束（宿主关闭了管道）
        _EXIT_REASON = "eof"
        _lifecycle_record("loop-returned", "stdio closed by client")
    except SystemExit as exc:
        if _EXIT_REASON == "unknown":
            _EXIT_REASON = "system-exit:%s" % (exc.code,)
        raise
    except BaseException:
        _EXIT_REASON = "unhandled-exception"
        raise
