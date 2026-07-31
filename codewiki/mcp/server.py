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
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global session store (lives for the lifetime of the MCP server process)
# ---------------------------------------------------------------------------
_store = SessionStore()

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

_SERVER_INSTRUCTIONS = """\
CodeWiki-CN MCP Server — 代码结构分析 + Wiki 文档生成 + LLM 知识库管理平台。

## 能力概览
- **代码分析**: Tree-sitter AST 解析 → 函数级调用图 → 依赖索引 → 传递性影响分析（无需 LLM）
- **Wiki 生成**: 模块化文档生成流水线（分析→聚类→逐模块撰写→总览→质检）
- **LLM Wiki 知识库**: BM25 全文搜索 + wikilink 图谱多跳扩展 + 结构化笔记
- **外部文档管理**: 导入 PDF/MD/DOCX/HTML → 知识抽取 → 实体/概念页面
- **质量保障**: 文档-代码一致性检查（过时引用、断链、覆盖率、循环依赖）
- **工作流指引**: 11 个 Prompt 模板（generate-wiki, extract-knowledge, search-wiki, ingest-note 等）
- **上下文资源**: Wiki 目录 (codewiki://wiki/catalog)、模块树 (codewiki://wiki/module-tree)、搜索索引状态 (codewiki://wiki/index-status)

## 核心工作流

### 1. 代码分析（独立使用，无需生成 Wiki）
analyze_repo → list_components / list_dependencies / analyze_impact / read_code_components

典型场景：
- 调用链查询: list_dependencies(component_ids, direction="both") 查看直接调用关系
- 修改影响评估: analyze_impact(component_ids 或 file_paths, direction="depended_by") 查看传递性影响范围（谁依赖我）、模块级聚合、高风险组件
- 依赖全景: analyze_impact(direction="both", include_paths=true) 获取完整调用链路径
- 代码阅读: read_code_components(component_ids) 读取源码

分析结果持久化在 SQLite 中。用户可以只做分析不生成文档，之后随时基于缓存数据继续生成 Wiki（增量模式自动复用已有分析）。

### 2. Wiki 生成（完整流水线）
analyze_repo → get_prompt('cluster') → save_module_tree → get_processing_order → 逐模块: get_prompt('user') + read_code_components → write_doc_file → close_session

若已有分析缓存，analyze_repo 增量模式自动跳过未变更文件，直接进入文档生成。

### 3. 知识库搜索
query_wiki(query, hop=1) → 查看结果 → query_wiki(query, expand=true) 深度阅读

### 4. 外部文档知识抽取
ingest_source → get_prompt('extraction_scan') → view_repo_file 阅读原文 → write_doc_file(page_type='entity'/'concept'/'source') → [[wikilink]] 建图

### 5. 经验归档
ingest_note(note_type, title, content) → 自动索引 → query_wiki 可检索

## 关键约束
- **大文件传输**: 分析结果（组件索引、源码、依赖图）写入 workspace 文件，通过返回的 file_path 读取，不经 MCP 通道传输
- **会话管理**: analyze_repo 创建会话（2h TTL，最多 10 个），close_session 触发索引重建和清理
- **增量更新**: 若 output_dir 已有 .meta/metadata.json，analyze_repo 返回 changes 字段标识变更
- **Mermaid 校验**: write_doc_file / edit_doc_file 自动校验 Mermaid 图表语法
- **page_type 路由**: module→wiki/modules/, entity→wiki/entities/, concept→wiki/concepts/, source→wiki/sources/
- **filename 规则**: write_doc_file 的 filename 参数只传纯文件名（如 "UserService.md"），禁止包含目录路径。目录由 page_type 自动路由，传 "entities/X.md" 会导致路径错误

## 推荐使用流程
1. 代码分析: analyze_repo → analyze_impact / list_dependencies（无需后续 Wiki 步骤）
2. 生成 Wiki: 调用 Prompt "generate-wiki" 获取完整步骤
3. 知识抽取: 调用 Prompt "extract-knowledge" 获取完整步骤
4. 知识归档: 调用 Prompt "ingest-note" 归档设计决策和经验教训
5. 搜索知识库: 调用 Prompt "search-wiki" 获取搜索策略
6. 质量检查: lint_wiki(checks=["all"]) → flag_issue 记录问题
"""

server = Server(
    "codewiki",
    version="5.1.4",
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
    asyncio.run(main())
