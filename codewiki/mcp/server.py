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
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global session store (lives for the lifetime of the MCP server process)
# ---------------------------------------------------------------------------
_store = SessionStore()

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

_SERVER_INSTRUCTIONS = """\
CodeWiki-CN MCP Server — 代码仓库 Wiki 文档生成与 LLM 知识库管理平台。

## 能力概览
- **代码分析**: Tree-sitter AST 解析 → 依赖图 → 组件索引（无需 LLM）
- **Wiki 生成**: 模块化文档生成流水线（分析→聚类→逐模块撰写→总览→质检）
- **LLM Wiki 知识库**: BM25 全文搜索 + wikilink 图谱多跳扩展 + 结构化笔记
- **外部文档管理**: 导入 PDF/MD/DOCX/HTML → 知识抽取 → 实体/概念页面
- **质量保障**: 文档-代码一致性检查（过时引用、断链、覆盖率、循环依赖）
- **工作流指引**: 6 个 Prompt 模板（generate-wiki, extract-knowledge, search-wiki 等）
- **上下文资源**: Wiki 目录 (codewiki://wiki/catalog)、模块树 (codewiki://wiki/module-tree)、搜索索引状态 (codewiki://wiki/index-status)

## 核心工作流

### 1. Wiki 生成（完整流水线）
analyze_repo → get_prompt('cluster') → save_module_tree → get_processing_order → 逐模块: get_prompt('user') + read_code_components → write_doc_file → close_session

### 2. 知识库搜索
query_wiki(query, hop=1) → 查看结果 → query_wiki(query, expand=true) 深度阅读

### 3. 外部文档知识抽取
ingest_source → get_prompt('extraction_scan') → view_repo_file 阅读原文 → write_doc_file(page_type='entity'/'concept'/'source') → [[wikilink]] 建图

### 4. 经验归档
ingest_note(note_type, title, content) → 自动索引 → query_wiki 可检索

## 关键约束
- **大文件传输**: 分析结果（组件索引、源码、依赖图）写入 workspace 文件，通过返回的 file_path 读取，不经 MCP 通道传输
- **会话管理**: analyze_repo 创建会话（2h TTL，最多 10 个），close_session 触发索引重建和清理
- **增量更新**: 若 output_dir 已有 .meta/metadata.json，analyze_repo 返回 changes 字段标识变更
- **Mermaid 校验**: write_doc_file / edit_doc_file 自动校验 Mermaid 图表语法
- **page_type 路由**: module→wiki/modules/, entity→wiki/entities/, concept→wiki/concepts/, source→wiki/sources/

## 推荐使用流程
1. 生成 Wiki: 调用 Prompt "generate-wiki" 获取完整步骤
2. 知识抽取: 调用 Prompt "extract-knowledge" 获取完整步骤
3. 搜索知识库: 调用 Prompt "search-wiki" 获取搜索策略
4. 质量检查: lint_wiki(checks=["all"]) → flag_issue 记录问题
"""

server = Server(
    "codewiki",
    version="5.1.0",
    instructions=_SERVER_INSTRUCTIONS,
)


# ===================================================================
#  Tool definitions
# ===================================================================

def _fine_grained_tools() -> list[Tool]:
    """Return the zero-config, IDE-driven tool set."""
    return [
        Tool(
            name="analyze_repo",
            description=(
                "Analyze a code repository's structure, dependencies, and components "
                "using Tree-sitter AST parsing. No LLM required. "
                "Writes the full component index, leaf nodes, and language stats to "
                "workspace files on disk, and returns file paths plus a compact summary. "
                "Read the workspace files for complete data. "
                "This is the entry point for the wiki generation pipeline. "
                "After calling this, use get_prompt('cluster') to learn clustering rules, "
                "then save_module_tree to persist your grouping. "
                "INCREMENTAL UPDATE: If docs already exist in output_dir (.meta/metadata.json + "
                ".meta/module_tree.json), the response includes a 'changes' field showing which "
                "files changed and which modules need updating."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to analyze",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory for generated docs (default: <repo>/repowiki)",
                    },
                    "include_patterns": {
                        "type": "string",
                        "description": "Comma-separated file patterns to include (e.g., '*.py,*.js')",
                    },
                    "exclude_patterns": {
                        "type": "string",
                        "description": "Comma-separated patterns to exclude (e.g., '*test*,*spec*')",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="read_code_components",
            description=(
                "Write the source code for a list of component IDs to workspace files. "
                "Component IDs have the form 'file_path::ComponentName'. "
                "Each component's full source is written to an individual .src file "
                "in the session's sources/ directory. Returns file paths — no truncation. "
                "Use this after analyze_repo to read source code for documentation writing. "
                "Pair with list_dependencies to understand the component's call graph."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "component_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of component IDs to read",
                    },
                },
                "required": ["session_id", "component_ids"],
            },
        ),
        Tool(
            name="write_doc_file",
            description=(
                "Create a new markdown documentation file in the output directory. "
                "Automatically validates Mermaid diagrams after writing (node IDs must be alphanumeric, "
                "labels in square brackets, no interactive syntax like 'click'). "
                "Supports LLM Wiki page types with structured routing: "
                "module → wiki/modules/, entity → wiki/entities/, concept → wiki/concepts/, "
                "source → wiki/sources/, comparison → wiki/comparisons/, query → wiki/queries/. "
                "Use [[wikilinks]] in content to reference other pages — these are automatically "
                "parsed into a graph for multi-hop search (query_wiki with hop parameter). "
                "For large docs (>200 lines), use content_file instead of inline content. "
                "Supports sessionless mode: provide output_dir instead of session_id for "
                "knowledge extraction workflows (no analyze_repo needed)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo (optional if output_dir is provided)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory for wiki pages (alternative to session_id, for sessionless mode like knowledge extraction)",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename for the doc (e.g., 'auth_module.md')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content to write",
                    },
                    "content_file": {
                        "type": "string",
                        "description": "Alternative to content: absolute path to a text file. Use for large docs (>200 lines).",
                    },
                    "page_type": {
                        "type": "string",
                        "enum": ["module", "entity", "concept", "source", "comparison", "query"],
                        "description": "LLM Wiki page type. Determines subdirectory routing (default: module → wiki/modules/)",
                    },
                    "frontmatter_extra": {
                        "type": "object",
                        "description": (
                            "Additional frontmatter fields merged into the doc header. "
                            "Common keys: aliases (list), category (str), domain (str), "
                            "origin (str), severity (str), source_refs (list), chunk_refs (list)."
                        ),
                    },
                },
                "required": ["filename"],
            },
        ),
        Tool(
            name="edit_doc_file",
            description=(
                "Edit an existing documentation file. Supports three commands: "
                "'str_replace' (find-and-replace, requires old_str + new_str), "
                "'insert' (add text at a specific line, requires new_str + insert_line), "
                "'undo' (revert the last edit). "
                "Automatically validates Mermaid diagrams after editing. "
                "For large replacements, use old_str_file/new_str_file instead of inline strings. "
                "IMPORTANT: After write_doc_file injects cross-links, the file content changes — "
                "always use view_repo_file to read the current content before editing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename of the doc to edit",
                    },
                    "command": {
                        "type": "string",
                        "enum": ["str_replace", "insert", "undo"],
                        "description": "Edit command to run",
                    },
                    "page_type": {
                        "type": "string",
                        "enum": ["module", "entity", "concept", "source", "comparison", "query"],
                        "description": "LLM Wiki page type for path resolution (default: module)",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "String to find (required for str_replace)",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Replacement string (for str_replace/insert)",
                    },
                    "old_str_file": {
                        "type": "string",
                        "description": "Alternative to old_str: absolute path to a text file.",
                    },
                    "new_str_file": {
                        "type": "string",
                        "description": "Alternative to new_str: absolute path to a text file.",
                    },
                    "insert_line": {
                        "type": "integer",
                        "description": "Line number for insert (0-indexed)",
                    },
                },
                "required": ["session_id", "filename", "command"],
            },
        ),
        Tool(
            name="save_module_tree",
            description=(
                "Save the IDE agent's module clustering result. "
                "Accepts a JSON module tree and persists it to disk. "
                "Computes the leaf-first processing order and writes it to a workspace file. "
                "Returns the file path for the processing order. "
                "Call this after analyze_repo + get_prompt('cluster') to persist your grouping. "
                "The module tree format: each key is a module name, value is "
                "{'components': [component_ids], 'children': {nested modules}}. "
                "For large trees (>50 components), use module_tree_file instead of inline JSON."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "module_tree": {
                        "type": "object",
                        "description": (
                            "Module tree dict. Each key is a module name with value "
                            "{'components': [component_ids], 'children': {nested modules}}"
                        ),
                    },
                    "module_tree_file": {
                        "type": "string",
                        "description": "Alternative to module_tree: absolute path to a JSON file. Use for large trees (>50 components).",
                    },
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="get_processing_order",
            description=(
                "Compute and write the leaf-first processing order to a workspace file. "
                "Returns the file path. Process leaf modules (is_leaf=true) before parent modules, "
                "so that parent module docs can reference already-written child module docs. "
                "Call this after save_module_tree to get the documentation writing order."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="get_prompt",
            description=(
                "Retrieve CodeWiki's prompt templates for each pipeline stage. "
                "Available prompt types and their purposes: "
                "Wiki generation: cluster (clustering rules), system_complex (parent module doc), "
                "system_leaf (leaf module doc), user (module doc writing guide), "
                "overview_module (module overview), overview_repo (repo overview). "
                "Knowledge extraction: extraction_scan (entity/concept identification rules), "
                "entity_page (entity page template), concept_page (concept page template), "
                "source_summary (source document summary template). "
                "Wiki management: wiki_query (search query template), "
                "wiki_ingest (note ingestion guide), wiki_lint_report (quality report format). "
                "Advanced: comparison_page (comparison template), query_page (query result template), "
                "taxonomy_plan (knowledge taxonomy planning). "
                "Optionally pass variables to fill in template placeholders. "
                "When variables produce content >4KB and a session_id is provided, "
                "the prompt is written to a workspace file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_type": {
                        "type": "string",
                        "enum": [
                            "cluster",
                            "system_complex",
                            "system_leaf",
                            "user",
                            "overview_module",
                            "overview_repo",
                            "wiki_query",
                            "wiki_ingest",
                            "wiki_lint_report",
                            "entity_page",
                            "concept_page",
                            "source_summary",
                            "comparison_page",
                            "query_page",
                            "taxonomy_plan",
                            "extraction_scan",
                        ],
                        "description": "Which prompt template to retrieve",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Optional template variables to fill in",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session ID for writing large prompts to workspace files",
                    },
                },
                "required": ["prompt_type"],
            },
        ),
        Tool(
            name="close_session",
            description=(
                "Close and clean up an analysis session to free memory. "
                "IMPORTANT: This is the final step of any wiki generation workflow. On close, "
                "the server automatically: 1) rebuilds wiki index.md and log.md, "
                "2) builds the BM25 search index + wikilink graph (enables query_wiki), "
                "3) injects wiki usage instructions into the target project's AGENTS.md, "
                "4) cleans up workspace files on disk. "
                "Always call this after finishing documentation work to ensure search indexes "
                "are up-to-date. Sessions auto-expire after 2 hours if not closed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to close",
                    },
                },
                "required": ["session_id"],
            },
        ),
        # --- LLM Wiki tools ---
        Tool(
            name="list_dependencies",
            description=(
                "Write the full dependency graph to a workspace file. "
                "Returns a compact summary with the file path, total counts, "
                "and high-impact components. "
                "Exposes depends_on / depended_by data from the dependency graph. "
                "Supports component-level and module-level aggregation. "
                "Use this during module documentation to understand call relationships "
                "and identify key dependencies to highlight in architecture diagrams. "
                "Set module_level=true to see inter-module dependencies instead of component-level."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "component_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: filter to specific component IDs",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["depends_on", "depended_by", "both"],
                        "description": "Dependency direction (default: both)",
                    },
                    "module_level": {
                        "type": "boolean",
                        "description": "Include module-level dependency graph (default: false)",
                    },
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="lint_wiki",
            description=(
                "Check documentation-code consistency. Works with or without an active session. "
                "Available checks: stale_refs (docs reference deleted components), "
                "broken_links (markdown links to non-existent pages), "
                "undocumented (high-impact components without docs), "
                "cycles (circular module dependencies), coverage (documentation coverage gaps), "
                "orphan_pages (pages with no inbound links), no_outlinks (pages with no cross-references), "
                "missing_aliases (pages without search aliases), stale_sources (retracted source refs), "
                "superseded_pages (pages marked as superseded). "
                "Run checks=['all'] for a comprehensive audit. "
                "After fixing issues, use flag_issue to track remaining problems."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "checks": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "all", "stale_refs", "undocumented", "broken_links",
                                "cycles", "coverage", "orphan_pages", "no_outlinks",
                                "missing_aliases", "stale_sources", "superseded_pages",
                            ],
                        },
                        "description": "Which checks to run (default: [\"all\"])",
                    },
                    "severity_filter": {
                        "type": "string",
                        "enum": ["error", "warning", "info"],
                        "description": "Minimum severity to report (default: info)",
                    },
                },
            },
        ),
        Tool(
            name="ingest_note",
            description=(
                "File a structured note into the knowledge base for future retrieval via query_wiki. "
                "Notes capture knowledge that doesn't exist in code: design decisions, lessons learned, "
                "architecture rationales, pitfalls, known issues, and workarounds. "
                "Stored in notes/ with YAML frontmatter. Automatically indexed by BM25 search. "
                "Use aliases to boost search relevance (3x weight). "
                "Note types: decision (why we chose X), lesson (what went wrong), "
                "architecture (system design rationale), bug_fix (how we fixed Y), "
                "pitfall (gotcha with root cause), known_issue (tracked problem), "
                "workaround (temporary solution), general (free-form knowledge). "
                "Can be used with or without an active session — just provide output_dir."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": [
                            "decision", "lesson", "architecture", "bug_fix", "general",
                            "pitfall", "known_issue", "workaround",
                        ],
                        "description": "Type of note (default: general)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title",
                    },
                    "content": {
                        "type": "string",
                        "description": "Note body (markdown)",
                    },
                    "related_modules": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Related module names (auto-detected if omitted)",
                    },
                    "related_components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Related component IDs",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Severity level (for pitfall/known_issue notes)",
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Root cause description (for pitfall/bug_fix notes)",
                    },
                    "source_ref": {
                        "type": "string",
                        "description": "Reference to external source document (e.g., 'RFC-793', 'api-docs-v2')",
                    },
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alternative names for this note (boosted 3x in search)",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="query_wiki",
            description=(
                "Search across generated documentation and ingested notes. "
                "Returns ranked results with snippets and a context_package summary "
                "for IDE agents to use as development context. "
                "Three-layer search strategy: "
                "1) BM25 full-text search (default) — returns snippets, "
                "2) Graph expansion (hop=1-3) — follows wikilinks to find related pages "
                "with score decay (0.5x per hop), "
                "3) Deep reading (expand=true) — returns full page content (up to 3000 chars). "
                "Supports filtering by page type (type_filter) and scope directory prefixes. "
                "Best for: why decisions were made, lessons learned, architecture rationale. "
                "For code implementation details (function signatures, call chains), use grep instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query in natural language",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Limit search to a module name or directory prefix (e.g. 'modules', 'entities', 'notes')",
                    },
                    "type_filter": {
                        "type": "string",
                        "enum": ["doc", "note", "module", "entity", "concept", "source", "comparison", "query"],
                        "description": "Filter results by page type (default: all types)",
                    },
                    "include_notes": {
                        "type": "boolean",
                        "description": "Include ingested notes in search (default: true)",
                    },
                    "include_sources": {
                        "type": "boolean",
                        "description": "Include imported source documents in search (default: true)",
                    },
                    "include_code_refs": {
                        "type": "boolean",
                        "description": "Return related component IDs (default: true)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 10, max: 20)",
                    },
                    "expand_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional synonym/expansion terms to broaden the search. "
                            "E.g., ['鉴权', '授权'] when searching for '认证'. "
                            "The IDE agent can use this for semantic query expansion."
                        ),
                    },
                    "hop": {
                        "type": "integer",
                        "description": (
                            "Graph expansion hops (0-3, default: 0). When >0, after BM25 "
                            "scoring, expands results along the wiki link graph (wikilinks "
                            "and markdown cross-references). Each hop decays score by 0.5x. "
                            "Use 1-2 for discovering related pages the query didn't directly match."
                        ),
                    },
                    "expand": {
                        "type": "boolean",
                        "description": (
                            "When true, return full page content (up to 3000 chars) in a "
                            "'content' field instead of just snippets. Use for deep reading "
                            "after identifying relevant pages with a normal search."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        # --- LLM Wiki: third-party source management ---
        Tool(
            name="ingest_source",
            description=(
                "Import a third-party document (PDF, MD, DOCX, HTML) into the "
                "knowledge base. The file is stored in raw/sources/ and registered "
                "in source_registry.json for tracking and search indexing. "
                "IMPORTANT: This tool only stores and indexes the document. To extract "
                "structured knowledge (entities, concepts) from it, follow this workflow: "
                "1) Call get_prompt(prompt_type='extraction_scan') for extraction guidance. "
                "2) Read the imported source via view_repo_file. "
                "3) Identify key entities and concepts in the document. "
                "4) Create pages: write_doc_file(page_type='source') for a summary page, "
                "write_doc_file(page_type='entity') for each significant entity, "
                "write_doc_file(page_type='concept') for each abstract concept. "
                "5) Use [[wikilinks]] between pages to build the knowledge graph."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "source_path": {
                        "type": "string",
                        "description": "Absolute path to the source file to import",
                    },
                    "name": {
                        "type": "string",
                        "description": "Identifier for this source (default: filename stem)",
                    },
                    "source_type": {
                        "type": "string",
                        "description": "Document type (default: auto-detected from extension)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of the source document",
                    },
                    "version": {
                        "type": "string",
                        "description": "Version or revision of the source",
                    },
                    "related_pages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Wiki pages that reference this source",
                    },
                },
                "required": ["source_path"],
            },
        ),
        Tool(
            name="retract_source",
            description=(
                "Remove a previously imported source document from the knowledge base. "
                "Two modes: 'flag_stale' (default) marks the source as retracted in "
                "source_registry.json but keeps the file — use when the document is outdated "
                "but you want to preserve history. 'remove_refs' deletes the file and cleans "
                "source_refs frontmatter from all wiki pages that reference it — use when "
                "the source is completely wrong or replaced. "
                "Always run with dry_run=true first to preview changes before remove_refs mode."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Source identifier (as registered via ingest_source)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["flag_stale", "remove_refs"],
                        "description": "Retraction mode (default: flag_stale)",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview changes without mutating files (recommended before remove_refs). Default: false.",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="batch_ingest",
            description=(
                "Bulk-import multiple notes and/or source documents in one call. "
                "Accepts an inline items list or an items_file path (for large batches). "
                "Each item must have a 'kind' field: 'note' or 'source', plus the fields "
                "for that tool (e.g., kind='note' needs title+content, kind='source' needs source_path). "
                "Performs a single index rebuild at the end for efficiency. "
                "Use this when importing many documents at once instead of calling "
                "ingest_note/ingest_source repeatedly. "
                "NOTE: After batch source import, you still need to extract knowledge "
                "from each source individually (see ingest_source description for the workflow)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "items": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of items to ingest. Each must have 'kind' (note|source) plus the fields for that tool.",
                    },
                    "items_file": {
                        "type": "string",
                        "description": "Alternative to items: absolute path to a JSON file containing the items list.",
                    },
                },
            },
        ),
        Tool(
            name="flag_issue",
            description=(
                "Flag a documentation quality issue for tracking. Issues are stored in .meta/issues.json "
                "with stable FNV-1a hash IDs. Duplicate flags are idempotent (same type + page = same ID). "
                "Use this after lint_wiki to track issues that cannot be fixed immediately. "
                "Issue types: orphan_page (no inbound links), no_outlinks (no cross-references), "
                "missing_aliases (no search aliases), stale_source (retracted source ref), "
                "broken_link (link to non-existent page), outdated_content (content doesn't match code), "
                "missing_section (required section absent), low_coverage (component not documented), "
                "custom (free-form issue). Severity: error (must fix), warning (should fix), info (nice to have)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional; can use output_dir instead)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (alternative to session_id)",
                    },
                    "issue_type": {
                        "type": "string",
                        "enum": [
                            "orphan_page", "no_outlinks", "missing_aliases",
                            "stale_source", "broken_link", "outdated_content",
                            "missing_section", "low_coverage", "custom",
                        ],
                        "description": "Type of quality issue",
                    },
                    "page_path": {
                        "type": "string",
                        "description": "Relative path to the affected wiki page",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of the issue",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["error", "warning", "info"],
                        "description": "Issue severity (default: warning)",
                    },
                },
                "required": ["issue_type"],
            },
        ),
        Tool(
            name="analyze_workspace",
            description=(
                "Scan a parent directory for git repositories and analyze each one "
                "independently. Each sub-repo gets its own repowiki at <repo>/repowiki/. "
                "A lightweight overview.md is generated at the workspace level with "
                "service descriptions, cross-service relationships, and links to each "
                "sub-repo's wiki. Design principle: one .git = one repowiki. "
                "Use this for multi-repo workspaces where multiple projects are cloned "
                "into a single folder. A lightweight workspace session is created for "
                "cross-service ingest_note / query_wiki at the parent level."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Absolute path to the parent directory containing git repos",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory for workspace overview (default: <workspace>/workspace-wiki)",
                    },
                    "exclude_dirs": {
                        "type": "string",
                        "description": "Comma-separated directory names to skip (default: node_modules,.venv,__pycache__)",
                    },
                },
                "required": ["workspace_path"],
            },
        ),
        Tool(
            name="list_components",
            description=(
                "Write the full component index to a workspace file. "
                "Returns a compact summary with the file path. "
                "A 'component' is a code element extracted by Tree-sitter: classes, functions, "
                "interfaces, methods, etc. Each component has an ID like 'file_path::ComponentName'. "
                "Use this after analyze_repo to discover components for clustering (save_module_tree) "
                "or source reading (read_code_components). "
                "Supports filtering by file_prefix (e.g., 'src/auth/') and component_type "
                "(e.g., 'class', 'function', 'interface')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "file_prefix": {
                        "type": "string",
                        "description": "Only return components whose file starts with this prefix",
                    },
                    "component_type": {
                        "type": "string",
                        "description": "Filter by type: class, function, interface, etc.",
                    },
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="view_repo_file",
            description=(
                "Read a file or list a directory within the analyzed repository. "
                "Common use cases: "
                "1) Read already-generated .md docs for parent module synthesis "
                "(e.g., path='repowiki/wiki/modules/auth.md'), "
                "2) Browse source files for extra context during documentation, "
                "3) Read imported source documents after ingest_source "
                "(e.g., path='raw/sources/rfc793.txt'). "
                "All paths are relative to repo_path with traversal protection. "
                "Directories return a listing; files return content. "
                "Large files (>50KB) are written to the session workspace."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from analyze_repo",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path from repo root (e.g. 'repowiki/overview.md' or 'backend/src/...')",
                    },
                },
                "required": ["session_id", "path"],
            },
        ),
    ]


def _legacy_tools() -> list[Tool]:
    """Return the legacy tools that require CodeWiki LLM configuration."""
    return [
        Tool(
            name="generate_docs",
            description=(
                "[LEGACY — requires 'codewiki config set' first] "
                "Generate full documentation for a repository in one shot. "
                "For IDE-driven generation, use the fine-grained tools instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to document",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory for generated docs (default: ./repowiki)",
                        "default": "repowiki",
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["api", "architecture", "user-guide", "developer", "business", "design"],
                        "description": "Type of documentation to generate",
                    },
                    "include_patterns": {
                        "type": "string",
                        "description": "Comma-separated file patterns to include",
                    },
                    "exclude_patterns": {
                        "type": "string",
                        "description": "Comma-separated patterns to exclude",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="get_module_tree",
            description=(
                "[LEGACY] Get the existing module clustering tree for a repository. "
                "Returns the tree structure previously saved via save_module_tree or "
                "generated by 'codewiki generate'. Use this to inspect an existing "
                "clustering before deciding whether to re-cluster. "
                "For new sessions, use save_module_tree to persist your clustering instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory containing generated docs (default: ./repowiki)",
                        "default": "repowiki",
                    },
                },
                "required": ["repo_path"],
            },
        ),
    ]


# ===================================================================
#  Tool dispatch
# ===================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available CodeWiki MCP tools."""
    return _fine_grained_tools() + _legacy_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to the appropriate handler."""
    try:
        # --- Fine-grained tools (no LLM config needed) ---
        # Synchronous handlers run via asyncio.to_thread() so they never
        # block the event loop (which would hang the MCP stdio server).
        if name == "analyze_repo":
            from codewiki.mcp.tools.analysis import handle_analyze_repo
            # NOTE: Tree-sitter C extensions are not thread-safe, so this
            # must run on the main thread (blocking the event loop is
            # acceptable for this one-time heavy operation).
            return [_text(handle_analyze_repo(arguments, _store))]

        elif name == "analyze_workspace":
            from codewiki.mcp.tools.workspace_analyzer import handle_analyze_workspace
            # Runs on main thread because it calls analyze_repo internally
            return [_text(handle_analyze_workspace(arguments, _store))]

        elif name == "read_code_components":
            from codewiki.mcp.tools.code_reader import handle_read_code_components
            return [_text(await asyncio.to_thread(handle_read_code_components, arguments, _store))]

        elif name == "write_doc_file":
            from codewiki.mcp.tools.doc_writer import handle_write_doc_file
            result = await handle_write_doc_file(arguments, _store)
            return [_text(result)]

        elif name == "edit_doc_file":
            from codewiki.mcp.tools.doc_writer import handle_edit_doc_file
            result = await handle_edit_doc_file(arguments, _store)
            return [_text(result)]

        elif name == "save_module_tree":
            from codewiki.mcp.tools.module_tree import handle_save_module_tree
            return [_text(await asyncio.to_thread(handle_save_module_tree, arguments, _store))]

        elif name == "get_processing_order":
            from codewiki.mcp.tools.module_tree import handle_get_processing_order
            return [_text(await asyncio.to_thread(handle_get_processing_order, arguments, _store))]

        elif name == "get_prompt":
            from codewiki.mcp.tools.prompt_server import handle_get_prompt
            return [_text(await asyncio.to_thread(handle_get_prompt, arguments, _store))]

        elif name == "close_session":
            sid = arguments["session_id"]
            session = _store.get(sid)
            if session:
                # Only stamp the incremental-update baseline when this
                # session actually produced docs — otherwise an aborted
                # session would make the next analyze_repo report
                # "Documentation is up to date" over missing/stale docs.
                if session.docs_written > 0:
                    _write_generation_metadata(session)
                else:
                    logger.info(
                        "Session %s wrote no docs; skipping metadata.json baseline update", sid
                    )
                # LLM Wiki: update index.md, log.md, and search index before cleanup
                try:
                    from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
                    append_log(session.output_dir, "close_session",
                               f"会话 {sid} 关闭")
                    rebuild_index(session.output_dir)
                except Exception:
                    pass
                # Build final BM25 search index (SQLite-backed when session available)
                try:
                    from codewiki.mcp.tools.wiki_search import build_full_index
                    build_full_index(session.output_dir, session=session)
                except Exception:
                    pass
                # Inject wiki usage instructions into target project's AGENTS.md
                if session.docs_written > 0:
                    try:
                        from codewiki.mcp.tools.agents_md import write_agents_md
                        write_agents_md(session)
                    except Exception:
                        logger.debug("Failed to update AGENTS.md", exc_info=True)
                # Clean up workspace files on disk
                if session.workspace is not None:
                    session.workspace.cleanup()
            removed = _store.remove(sid)
            return [_text(json.dumps({
                "status": "closed" if removed else "not_found",
                "session_id": sid,
            }))]

        # --- LLM Wiki tools (zero LLM config, IDE-driven) ---
        elif name == "list_dependencies":
            from codewiki.mcp.tools.crosslink import handle_list_dependencies
            return [_text(await asyncio.to_thread(handle_list_dependencies, arguments, _store))]

        elif name == "lint_wiki":
            from codewiki.mcp.tools.wiki_lint import handle_lint_wiki
            return [_text(await asyncio.to_thread(handle_lint_wiki, arguments, _store))]

        elif name == "ingest_note":
            from codewiki.mcp.tools.knowledge_loop import handle_ingest_note
            return [_text(await asyncio.to_thread(handle_ingest_note, arguments, _store))]

        elif name == "query_wiki":
            from codewiki.mcp.tools.knowledge_loop import handle_query_wiki
            return [_text(await asyncio.to_thread(handle_query_wiki, arguments, _store))]

        elif name == "ingest_source":
            from codewiki.mcp.tools.source_ingest import handle_ingest_source
            return [_text(await asyncio.to_thread(handle_ingest_source, arguments, _store))]

        elif name == "retract_source":
            from codewiki.mcp.tools.source_ingest import handle_retract_source
            return [_text(await asyncio.to_thread(handle_retract_source, arguments, _store))]

        elif name == "batch_ingest":
            from codewiki.mcp.tools.batch_ingest import handle_batch_ingest
            return [_text(await asyncio.to_thread(handle_batch_ingest, arguments, _store))]

        elif name == "flag_issue":
            from codewiki.mcp.tools.issue_tracker import handle_flag_issue
            return [_text(await asyncio.to_thread(handle_flag_issue, arguments, _store))]

        elif name == "list_components":
            from codewiki.mcp.tools.component_list import handle_list_components
            return [_text(await asyncio.to_thread(handle_list_components, arguments, _store))]

        elif name == "view_repo_file":
            from codewiki.mcp.tools.file_viewer import handle_view_repo_file
            return [_text(await asyncio.to_thread(handle_view_repo_file, arguments, _store))]

        # --- Legacy tools (require CodeWiki LLM config) ---
        elif name == "generate_docs":
            return await _legacy_generate_docs(arguments)

        elif name == "get_module_tree":
            return await _legacy_get_module_tree(arguments)

        else:
            return [_text(json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return [_text(json.dumps({"error": str(e)}))]


# ===================================================================
#  MCP Prompts — workflow templates that guide agents
# ===================================================================

@server.list_prompts()
async def list_prompts() -> list:
    """List available workflow prompt templates."""
    from mcp.types import Prompt, PromptArgument
    return [
        Prompt(
            name="generate-wiki",
            title="生成代码 Wiki",
            description="完整的代码仓库 Wiki 生成流水线：分析→聚类→逐模块撰写→总览→质检→关闭会话",
            arguments=[
                PromptArgument(
                    name="repo_path",
                    description="要分析的代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                    required=False,
                ),
                PromptArgument(
                    name="output_dir",
                    description="Wiki 输出目录（默认: <repo>/repowiki）",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="extract-knowledge",
            title="外部文档知识抽取",
            description="导入外部文档并从中抽取实体和概念，生成结构化知识页面并构建 wikilink 图谱。一步完成导入+提取。",
            arguments=[
                PromptArgument(
                    name="source_path",
                    description="要导入并提取知识的外部文档的绝对路径（支持 PDF/MD/DOCX/HTML）",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="search-wiki",
            title="知识库搜索策略",
            description="高效搜索 Wiki 知识库的策略指引：BM25 搜索、图谱扩展、深度阅读",
            arguments=[
                PromptArgument(
                    name="query",
                    description="搜索关键词或自然语言问题",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="quality-check",
            title="文档质量审计",
            description="对已生成的 Wiki 执行全面质量检查：过时引用、断链、覆盖率、循环依赖",
            arguments=[
                PromptArgument(
                    name="output_dir",
                    description="Wiki 输出目录",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="incremental-update",
            title="增量更新 Wiki",
            description="检测代码变更并增量更新受影响的 Wiki 模块文档",
            arguments=[
                PromptArgument(
                    name="repo_path",
                    description="代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="workspace-analysis",
            title="多仓库工作区分析",
            description="扫描父目录下的多个 git 仓库，为每个生成独立 Wiki 并创建跨服务总览",
            arguments=[
                PromptArgument(
                    name="workspace_path",
                    description="包含多个 git 仓库的父目录路径（相对路径基于当前工作目录，默认当前目录）",
                    required=False,
                ),
            ],
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None) -> Any:
    """Return a workflow prompt template with step-by-step agent instructions."""
    from mcp.types import GetPromptResult, PromptMessage, TextContent as PromptTextContent
    args = arguments or {}

    prompts_map = {
        "generate-wiki": _prompt_generate_wiki,
        "extract-knowledge": _prompt_extract_knowledge,
        "search-wiki": _prompt_search_wiki,
        "quality-check": _prompt_quality_check,
        "incremental-update": _prompt_incremental_update,
        "workspace-analysis": _prompt_workspace_analysis,
    }

    handler = prompts_map.get(name)
    if not handler:
        return GetPromptResult(
            description=f"Unknown prompt: {name}",
            messages=[PromptMessage(
                role="user",
                content=PromptTextContent(type="text", text=f"未知的 Prompt 模板: {name}。可用模板: {', '.join(prompts_map.keys())}"),
            )],
        )

    text = handler(args)
    return GetPromptResult(
        description=f"CodeWiki 工作流指引: {name}",
        messages=[PromptMessage(
            role="user",
            content=PromptTextContent(type="text", text=text),
        )],
    )


def _resolve_path(raw: str) -> str:
    """Resolve a path: if relative, join with cwd; always return absolute."""
    import os
    p = raw.strip()
    if not p or p in (".", "./"):
        return os.getcwd()
    if os.path.isabs(p):
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(os.getcwd(), p))


def _prompt_generate_wiki(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    output_dir = args.get("output_dir", "")
    od_note = f'，output_dir="{output_dir}"' if output_dir else ""
    return f"""请为代码仓库生成完整的 Wiki 文档。按以下步骤执行：

## 步骤 1: 分析仓库
调用 analyze_repo(repo_path="{repo_path}"{od_note})
- 返回 session_id、组件数量、语言统计
- 大文件结果写入 workspace 文件，通过返回的 file_path 读取

## 步骤 2: 模块聚类
调用 get_prompt(prompt_type="cluster", session_id=<session_id>)
- 获取聚类规则（按目录结构、依赖关系、功能内聚性分组）
- 根据规则将组件分为模块，构建 module_tree JSON
- 调用 save_module_tree(session_id, module_tree) 保存

## 步骤 3: 获取处理顺序
调用 get_processing_order(session_id)
- 返回叶优先顺序：先写叶模块，再写父模块（父模块可引用子模块文档）

## 步骤 4: 逐模块撰写文档
对每个模块（按处理顺序）：
1. 调用 get_prompt(prompt_type="user", session_id, variables={{"module_name": "<模块名>"}}) 获取撰写指引
2. 调用 read_code_components(session_id, component_ids) 读取源码
3. 调用 list_dependencies(session_id, component_ids) 获取依赖关系
4. 撰写 Markdown 文档（200-500 行叶模块，含 Mermaid 架构图）
5. 调用 write_doc_file(session_id, filename="modules/<模块名>.md", content=...) 写入

## 步骤 5: 仓库总览
调用 get_prompt(prompt_type="overview_repo", session_id) 获取总览模板
撰写 overview.md（80-200 行），链接所有模块文档

## 步骤 6: 质检与关闭
- 调用 lint_wiki(session_id) 检查一致性
- 修复发现的问题（edit_doc_file）
- 调用 close_session(session_id) 完成（触发索引重建、AGENTS.md 注入）

## 注意事项
- 每个叶模块至少 1 个 Mermaid 图（graph TD 或 graph LR）
- 使用 [模块名](模块名.md) 交叉引用
- 节点 ID 仅用字母和数字，标签用方括号
- 文档语言默认中文"""


def _prompt_extract_knowledge(args: dict[str, str]) -> str:
    source_path = args.get("source_path", "")
    if not source_path:
        source_path = "<source_path>"
    else:
        source_path = _resolve_path(source_path)
    # Derive a name from the file stem
    from pathlib import Path as _Path
    source_name = _Path(source_path).stem
    # output_dir defaults to cwd/repowiki (not next to the source file)
    output_dir = args.get("output_dir", "") or str(_Path(_resolve_path("")) / "repowiki")
    return f"""请导入外部文档并从中抽取结构化知识。按以下步骤执行：

## 步骤 1: 导入文档
调用 ingest_source(output_dir="{output_dir}", source_path="{source_path}")
- 文档会被复制到 {output_dir}/raw/sources/ 并注册到 source_registry.json
- 此步骤不需要 session_id，不需要 analyze_repo

## 步骤 2: 获取抽取方法论
调用 get_prompt(prompt_type="extraction_scan")
- 返回实体/概念识别规则和粒度指引

## 步骤 3: 阅读源文档
直接读取文件 "{source_path}"（使用 Read 工具或文件系统读取）
- 通读全文，标记关键实体和抽象概念
- 注意：不需要调用 view_repo_file，直接读取原始文件即可

## 步骤 4: 识别知识单元
从文档中提取：
- **实体**（entity）：具体的人物、系统、服务、组件、API、数据库
- **概念**（concept）：抽象的模式、算法、协议、架构决策、设计原则

## 步骤 5: 生成知识页面
为每个知识单元创建页面（使用 output_dir="{output_dir}"）：
1. 源文档摘要: write_doc_file(output_dir="{output_dir}", filename="sources/{source_name}.md", page_type="source", content=...)
   - 调用 get_prompt(prompt_type="source_summary") 获取模板
2. 实体页面: write_doc_file(output_dir="{output_dir}", filename="entities/<实体名>.md", page_type="entity", content=...)
   - 调用 get_prompt(prompt_type="entity_page") 获取模板
3. 概念页面: write_doc_file(output_dir="{output_dir}", filename="concepts/<概念名>.md", page_type="concept", content=...)
   - 调用 get_prompt(prompt_type="concept_page") 获取模板

## 步骤 6: 构建知识图谱
- 页面间使用 [[wikilink]] 互相引用（如 [[认证服务]]、[[OAuth2]]）
- build_search_index 会自动解析 wikilink 为图谱边
- 之后可通过 query_wiki(output_dir="{output_dir}", query, hop=1) 进行多跳关联搜索

## 注意事项
- 整个流程不需要 analyze_repo，不需要 session_id
- write_doc_file 支持直接传 output_dir 参数（无需 session_id）
- ingest_source 只负责存储，不会自动生成 entity/concept 页面
- 每个页面应包含：定义、关键属性、与其他实体的关系、来源引用
- 使用 frontmatter_extra 添加 aliases（搜索加权 3x）和 source_refs"""


def _prompt_search_wiki(args: dict[str, str]) -> str:
    query = args.get("query", "<query>")
    return f"""请搜索 Wiki 知识库回答: "{query}"

## 搜索策略

### 第一层：BM25 全文搜索
调用 query_wiki(query="{query}", include_notes=true)
- 返回按相关性排序的结果，含 snippet 和 context_package
- 如果结果不理想，尝试 expand_terms 添加同义词

### 第二层：图谱扩展
调用 query_wiki(query="{query}", hop=1)
- 沿 wikilink 图谱 BFS 扩展，发现相关但未直接匹配的页面
- hop=2 可进一步扩展（分数衰减 0.5x/hop）

### 第三层：深度阅读
对感兴趣的结果调用 query_wiki(query="<精确标题>", expand=true)
- 返回完整页面内容（截断至 3000 字符）
- 适合需要详细了解某个主题时

### 过滤技巧
- scope="modules" 限定搜索模块文档
- scope="entities" 限定搜索实体页面
- scope="notes" 限定搜索经验笔记
- type_filter="entity" 按页面类型过滤

## 注意事项
- 代码实现细节（函数签名、调用链）应使用 grep/代码搜索，不用 query_wiki
- query_wiki 擅长回答 why（设计决策）、lesson（踩坑经验）、architecture（架构约定）
- 搜索无结果时考虑：同义词、上位概念、相关模块名"""


def _prompt_quality_check(args: dict[str, str]) -> str:
    output_dir = args.get("output_dir", "")
    od_param = f'output_dir="{output_dir}"' if output_dir else 'session_id=<session_id>'
    return f"""请对 Wiki 文档执行全面质量审计。按以下步骤执行：

## 步骤 1: 运行全量检查
调用 lint_wiki({od_param}, checks=["all"])
- stale_refs: 文档引用了已不存在的代码组件
- broken_links: Markdown 链接指向不存在的页面
- undocumented: 高影响组件缺少文档
- cycles: 模块间存在循环依赖
- coverage: 文档覆盖率不足
- orphan_pages: 无入链的孤立页面
- no_outlinks: 无出链的页面（缺少交叉引用）

## 步骤 2: 按严重度处理
- error: 必须修复（断链、过时引用）
- warning: 建议修复（孤立页面、缺少别名）
- info: 可选优化（覆盖率提升）

## 步骤 3: 修复问题
- 断链: edit_doc_file 修正链接路径
- 过时引用: 重新阅读代码，更新文档内容
- 孤立页面: 在相关页面添加 [[wikilink]] 引用
- 缺少文档: write_doc_file 补充模块文档

## 步骤 4: 记录问题
对暂时无法修复的问题调用 flag_issue(issue_type, page_path, description)
- 问题追踪在 .meta/issues.json，支持后续批量处理

## 步骤 5: 验证修复
再次调用 lint_wiki 确认问题已解决"""


def _prompt_incremental_update(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    return f"""请增量更新代码仓库的 Wiki 文档。按以下步骤执行：

## 步骤 1: 检测变更
调用 analyze_repo(repo_path="{repo_path}")
- 如果 output_dir 已有 .meta/metadata.json，返回 changes 字段
- changes 包含: added_files, modified_files, deleted_files, affected_modules

## 步骤 2: 评估影响范围
- 阅读 changes.affected_modules 确定需要更新的模块
- 如果变更较小（<3 个模块），直接更新
- 如果变更较大，考虑重新聚类（save_module_tree）

## 步骤 3: 更新受影响模块
对每个 affected_module：
1. read_code_components 读取最新源码
2. view_repo_file 读取现有文档
3. edit_doc_file(str_replace) 更新变更部分
4. 或 write_doc_file 重写整个模块文档

## 步骤 4: 处理删除的文件
- 如果组件被删除，更新引用它的文档
- lint_wiki(checks=["stale_refs"]) 检查过时引用

## 步骤 5: 重建索引
调用 close_session(session_id) 触发索引重建

## 注意事项
- 增量更新只修改受影响的模块，不重写整个 Wiki
- 如果 metadata.json 不存在，会执行全量分析"""


def _prompt_workspace_analysis(args: dict[str, str]) -> str:
    workspace_path = _resolve_path(args.get("workspace_path", ""))
    return f"""请分析多仓库工作区并生成跨服务文档。按以下步骤执行：

## 步骤 1: 扫描工作区
调用 analyze_workspace(workspace_path="{workspace_path}")
- 自动发现所有 git 仓库（一个 .git = 一个 repowiki）
- 为每个子仓库独立执行 analyze_repo
- 生成 workspace 级别的 overview.md

## 步骤 2: 逐仓库生成 Wiki
对每个子仓库执行标准 Wiki 生成流程：
- analyze_repo → 聚类 → 逐模块撰写 → close_session
- 每个仓库的 Wiki 位于 <repo>/repowiki/

## 步骤 3: 跨服务文档
- 在 workspace-wiki/ 目录创建跨服务文档
- 使用 ingest_note(note_type="architecture") 记录跨服务架构决策
- 记录服务间调用关系、共享数据模型、API 契约

## 步骤 4: 工作区总览
- overview.md 包含：服务列表、职责描述、交互关系图
- 链接到各子仓库的 repowiki/overview.md

## 注意事项
- 每个子仓库独立管理自己的 Wiki
- workspace 级别只存放跨服务关注点
- 使用 query_wiki 在 workspace 级别搜索跨服务知识"""


# ===================================================================
#  MCP Resources — read-only context for agents
# ===================================================================

@server.list_resources()
async def list_resources() -> list:
    """List available static resources."""
    from mcp.types import Resource
    return [
        Resource(
            uri="codewiki://prompts/catalog",
            name="Prompt 模板目录",
            title="CodeWiki Prompt 模板目录",
            description="所有可用的 Prompt 模板列表及其用途说明，帮助 agent 了解可用的工作流指引",
            mimeType="application/json",
        ),
        Resource(
            uri="codewiki://capabilities",
            name="服务能力概览",
            title="CodeWiki 服务能力与工具清单",
            description="完整的工具列表、参数速查、工作流说明，agent 可据此规划任务",
            mimeType="application/json",
        ),
        Resource(
            uri="codewiki://page-types",
            name="页面类型说明",
            title="Wiki 页面类型与路由规则",
            description="各 page_type 的用途、存储路径、frontmatter 规范和 wikilink 建图规则",
            mimeType="application/json",
        ),
    ]


@server.list_resource_templates()
async def list_resource_templates() -> list:
    """List available resource templates (parameterized URIs)."""
    from mcp.types import ResourceTemplate
    return [
        ResourceTemplate(
            uriTemplate="codewiki://wiki/{output_dir}/catalog",
            name="Wiki 页面目录",
            title="指定 Wiki 的页面目录",
            description="获取指定输出目录下所有 Wiki 页面的目录（标题、类型、路径），URI 中 output_dir 使用 URL 编码的绝对路径",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate="codewiki://wiki/{output_dir}/module-tree",
            name="模块聚类树",
            title="指定 Wiki 的模块聚类树",
            description="获取指定 Wiki 的模块聚类结构（模块名、组件数、层级关系）",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate="codewiki://wiki/{output_dir}/index-status",
            name="搜索索引状态",
            title="指定 Wiki 的搜索索引状态",
            description="获取 BM25 搜索索引和 wikilink 图谱的构建状态（页面数、token 数、边数）",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: Any) -> str:
    """Read a resource by URI."""
    uri_str = str(uri)

    if uri_str == "codewiki://prompts/catalog":
        return json.dumps({
            "prompts": [
                {"name": "generate-wiki", "title": "生成代码 Wiki", "description": "完整的代码仓库 Wiki 生成流水线", "arguments": ["repo_path (optional, 默认当前目录)", "output_dir (optional)"]},
                {"name": "extract-knowledge", "title": "外部文档知识抽取", "description": "导入外部文档并从中抽取实体/概念，一步完成导入+提取", "arguments": ["source_path (required, 文档绝对路径)"]},
                {"name": "search-wiki", "title": "知识库搜索策略", "description": "BM25 + 图谱扩展 + 深度阅读的分层搜索策略", "arguments": ["query (required)"]},
                {"name": "quality-check", "title": "文档质量审计", "description": "全面质量检查：过时引用、断链、覆盖率、循环依赖", "arguments": ["output_dir (optional)"]},
                {"name": "incremental-update", "title": "增量更新 Wiki", "description": "检测代码变更并增量更新受影响的模块文档", "arguments": ["repo_path (optional, 默认当前目录)"]},
                {"name": "workspace-analysis", "title": "多仓库工作区分析", "description": "扫描多 git 仓库，生成独立 Wiki 和跨服务总览", "arguments": ["workspace_path (optional, 默认当前目录)"]},
            ],
            "usage": "通过 MCP prompts/get 协议获取完整工作流指引，或调用 get_prompt 工具获取代码生成阶段的 prompt 模板",
        }, ensure_ascii=False, indent=2)

    elif uri_str == "codewiki://capabilities":
        return json.dumps({
            "server": "CodeWiki-CN MCP Server v5.1.0",
            "tool_count": 21,
            "tool_categories": {
                "代码分析": ["analyze_repo", "analyze_workspace", "list_components", "list_dependencies", "read_code_components", "view_repo_file"],
                "文档生成": ["write_doc_file", "edit_doc_file", "save_module_tree", "get_processing_order", "get_prompt", "generate_docs (legacy)"],
                "知识库管理": ["query_wiki", "ingest_note", "ingest_source", "retract_source", "batch_ingest"],
                "质量保障": ["lint_wiki", "flag_issue"],
                "会话管理": ["close_session", "get_module_tree (legacy)"],
            },
            "key_patterns": {
                "workspace_file": "大结果写入 .codewiki/sessions/{id}/ 目录，通过 file_path 读取",
                "session_lifecycle": "analyze_repo 创建 → 工具调用 → close_session 清理（2h TTL）",
                "page_type_routing": "module→wiki/modules/, entity→wiki/entities/, concept→wiki/concepts/, source→wiki/sources/",
                "search_layers": "BM25 全文 → hop 图谱扩展 → expand 深度阅读",
            },
        }, ensure_ascii=False, indent=2)

    elif uri_str == "codewiki://page-types":
        return json.dumps({
            "page_types": {
                "module": {"path": "wiki/modules/", "description": "代码模块文档（由 analyze_repo 流水线生成）", "typical_sections": ["概述", "架构图", "核心组件", "依赖关系", "使用示例"]},
                "entity": {"path": "wiki/entities/", "description": "实体页面（人物/系统/服务/组件/API）", "typical_sections": ["定义", "关键属性", "关系", "来源引用"]},
                "concept": {"path": "wiki/concepts/", "description": "概念页面（模式/算法/协议/架构决策）", "typical_sections": ["定义", "原理", "应用场景", "相关概念"]},
                "source": {"path": "wiki/sources/", "description": "外部源文档摘要页", "typical_sections": ["来源信息", "核心内容", "抽取的实体/概念", "引用"]},
                "comparison": {"path": "wiki/comparisons/", "description": "对比分析页面", "typical_sections": ["对比维度", "各方案优劣", "结论"]},
                "query": {"path": "wiki/queries/", "description": "查询结果归档页面", "typical_sections": ["问题", "答案", "参考来源"]},
            },
            "wikilink_rules": {
                "syntax": "[[页面名]] 或 [显示文本](相对路径.md)",
                "graph_build": "build_search_index 自动解析所有 wikilink 为 wiki_links 表中的有向边",
                "multi_hop": "query_wiki(hop=N) 沿图谱边 BFS 扩展，每跳分数衰减 0.5x",
                "aliases": "frontmatter_extra.aliases 中的别名也参与 wikilink 解析",
            },
        }, ensure_ascii=False, indent=2)

    # Resource templates: codewiki://wiki/{output_dir}/...
    elif uri_str.startswith("codewiki://wiki/"):
        return _read_wiki_resource(uri_str)

    return json.dumps({"error": f"Unknown resource: {uri_str}"})


def _read_wiki_resource(uri_str: str) -> str:
    """Handle parameterized wiki resources like codewiki://wiki/{output_dir}/catalog."""
    from urllib.parse import unquote
    # Parse: codewiki://wiki/<encoded_output_dir>/<resource_type>
    path_part = uri_str[len("codewiki://wiki/"):]
    # The last segment is the resource type
    last_slash = path_part.rfind("/")
    if last_slash == -1:
        return json.dumps({"error": "Invalid URI format. Expected: codewiki://wiki/{output_dir}/{catalog|module-tree|index-status}"})

    output_dir_encoded = path_part[:last_slash]
    resource_type = path_part[last_slash + 1:]
    output_dir = unquote(output_dir_encoded)

    output_path = Path(output_dir)
    if not output_path.exists():
        return json.dumps({"error": f"Output directory not found: {output_dir}"})

    if resource_type == "catalog":
        return _wiki_catalog(output_path)
    elif resource_type == "module-tree":
        return _wiki_module_tree(output_path)
    elif resource_type == "index-status":
        return _wiki_index_status(output_path)
    else:
        return json.dumps({"error": f"Unknown resource type: {resource_type}. Available: catalog, module-tree, index-status"})


def _wiki_catalog(output_path: Path) -> str:
    """Build a catalog of all wiki pages."""
    pages = []
    wiki_dir = output_path / "wiki"
    search_dirs = [wiki_dir, output_path / "notes"]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            rel = md_file.relative_to(output_path)
            # Read first heading as title
            title = md_file.stem
            try:
                for line in md_file.read_text(encoding="utf-8").splitlines()[:10]:
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except Exception:
                pass
            # Determine page type from directory
            parts = rel.parts
            page_type = parts[1] if len(parts) > 2 and parts[0] == "wiki" else "note"
            pages.append({"path": str(rel).replace("\\", "/"), "title": title, "type": page_type})

    return json.dumps({"output_dir": str(output_path), "page_count": len(pages), "pages": pages}, ensure_ascii=False, indent=2)


def _wiki_module_tree(output_path: Path) -> str:
    """Read the module tree from .meta/module_tree.json."""
    from codewiki.src.config import meta_resolve
    tree_path = Path(meta_resolve(output_path, "module_tree.json"))
    if not tree_path.exists():
        return json.dumps({"error": "Module tree not found. Run analyze_repo + save_module_tree first."})
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        # Summarize
        def _summarize(t, depth=0):
            modules = []
            for name, info in t.items():
                modules.append({
                    "name": name,
                    "components": len(info.get("components", [])),
                    "children": len(info.get("children", {})) if isinstance(info.get("children"), dict) else 0,
                    "is_leaf": not bool(info.get("children")),
                })
                if isinstance(info.get("children"), dict) and info["children"]:
                    modules.extend(_summarize(info["children"], depth + 1))
            return modules
        summary = _summarize(tree)
        return json.dumps({"output_dir": str(output_path), "total_modules": len(tree), "modules": summary}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to read module tree: {e}"})


def _wiki_index_status(output_path: Path) -> str:
    """Check the search index and link graph status."""
    from codewiki.src.config import meta_resolve
    index_path = Path(meta_resolve(output_path, "search_index.db"))
    result = {"output_dir": str(output_path), "index_exists": index_path.exists()}

    if index_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(index_path))
            cur = conn.cursor()
            # Count indexed pages
            try:
                cur.execute("SELECT COUNT(*) FROM search_index")
                result["indexed_pages"] = cur.fetchone()[0]
            except Exception:
                result["indexed_pages"] = 0
            # Count tokens
            try:
                cur.execute("SELECT COUNT(*) FROM search_token_index")
                result["token_entries"] = cur.fetchone()[0]
            except Exception:
                result["token_entries"] = 0
            # Count graph edges
            try:
                cur.execute("SELECT COUNT(*) FROM wiki_links")
                result["graph_edges"] = cur.fetchone()[0]
            except Exception:
                result["graph_edges"] = 0
            conn.close()
        except Exception as e:
            result["error"] = str(e)
    else:
        result["hint"] = "Search index not built yet. Call close_session or build_search_index to create it."

    return json.dumps(result, ensure_ascii=False, indent=2)


# ===================================================================
#  Legacy tool handlers (require _load_config)
# ===================================================================

def _load_config():
    """Load CodeWiki configuration from ~/.codewiki/config.json + keyring."""
    from codewiki.cli.config_manager import ConfigManager
    manager = ConfigManager()
    if not manager.load():
        raise RuntimeError(
            "CodeWiki not configured. Run 'codewiki config set' first."
        )
    return manager


async def _legacy_generate_docs(arguments: dict[str, Any]) -> list[TextContent]:
    """Legacy generate_docs — requires CodeWiki LLM configuration."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    raw_od = Path(arguments.get("output_dir", "repowiki")).expanduser()
    output_dir = raw_od.resolve() if raw_od.is_absolute() else (repo_path / raw_od).resolve()

    if not repo_path.exists():
        return [_text(json.dumps({"error": f"Repository not found: {repo_path}"}))]

    manager = _load_config()
    config = manager.get_config()
    api_key = manager.get_api_key()

    from codewiki.src.be.backend import is_caw_provider
    caw_mode = bool(config) and is_caw_provider(getattr(config, "provider", ""))
    if not api_key and not caw_mode:
        return [_text(json.dumps({"error": "API key not configured. Run 'codewiki config set --api-key <key>'"}))]

    agent_instructions = {}
    if arguments.get("doc_type"):
        agent_instructions["doc_type"] = arguments["doc_type"]
    if arguments.get("include_patterns"):
        agent_instructions["include_patterns"] = [p.strip() for p in arguments["include_patterns"].split(",")]
    if arguments.get("exclude_patterns"):
        agent_instructions["exclude_patterns"] = [p.strip() for p in arguments["exclude_patterns"].split(",")]

    from codewiki.src.config import Config as BackendConfig, set_cli_context
    set_cli_context(True)

    backend_config = BackendConfig.from_cli(
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        llm_base_url=config.base_url,
        llm_api_key=api_key,
        main_model=config.main_model,
        cluster_model=config.cluster_model,
        fallback_model=config.fallback_model,
        provider=getattr(config, "provider", "openai-compatible"),
        aws_region=getattr(config, "aws_region", "us-east-1"),
        max_tokens=config.max_tokens,
        agent_instructions=agent_instructions or None,
    )

    from codewiki.cli.utils.repo_validator import get_git_commit_hash
    from codewiki.src.be.documentation_generator import DocumentationGenerator
    doc_gen = DocumentationGenerator(backend_config, commit_id=get_git_commit_hash(repo_path) or None)
    await doc_gen.run()

    generated_files = []
    for f in output_dir.iterdir():
        if f.suffix in (".md", ".json", ".html"):
            generated_files.append(f.name)

    result = {
        "status": "success",
        "output_dir": str(output_dir),
        "files_generated": sorted(generated_files),
        "file_count": len(generated_files),
    }
    return [_text(json.dumps(result, indent=2))]


async def _legacy_get_module_tree(arguments: dict[str, Any]) -> list[TextContent]:
    """Legacy get_module_tree."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    raw_od = Path(arguments.get("output_dir", "repowiki")).expanduser()
    output_dir = raw_od.resolve() if raw_od.is_absolute() else (repo_path / raw_od).resolve()

    from codewiki.src.config import meta_resolve
    module_tree_path = Path(meta_resolve(output_dir, "module_tree.json"))
    if not module_tree_path.exists():
        return [_text(json.dumps({
            "error": f"Module tree not found at {module_tree_path}. Run 'codewiki generate' first."
        }))]

    module_tree = json.loads(module_tree_path.read_text(encoding="utf-8"))

    def _summarize_tree(tree, depth=0):
        lines = []
        for name, info in tree.items():
            indent = "  " * depth
            comp_count = len(info.get("components", []))
            children = info.get("children", {})
            child_count = len(children) if isinstance(children, dict) else 0
            lines.append(f"{indent}- {name} ({comp_count} components, {child_count} children)")
            if isinstance(children, dict) and children:
                lines.extend(_summarize_tree(children, depth + 1))
        return lines

    summary = "\n".join(_summarize_tree(module_tree))
    result = {
        "status": "success",
        "module_tree_path": str(module_tree_path),
        "total_modules": len(module_tree),
        "tree_summary": summary,
    }
    return [_text(json.dumps(result, indent=2))]


# ===================================================================
#  Helpers
# ===================================================================

def _text(content: str) -> TextContent:
    return TextContent(type="text", text=content)


def _write_generation_metadata(session: SessionState) -> None:
    """Write ``metadata.json`` to the session's output directory.

    Records the current git commit and timestamp so that
    :func:`_detect_changes` can diff against this baseline on the next
    ``analyze_repo`` call, enabling incremental updates.
    """
    try:
        output_dir = Path(session.output_dir)
        repo_path = Path(session.repo_path)

        # Baseline on the commit analyze_repo saw, NOT the current HEAD:
        # commits made mid-session were never analyzed, and recording HEAD
        # here would silently exclude them from the next incremental run.
        commit_id: str | None = session.analyzed_commit
        if not commit_id:
            from codewiki.cli.utils.repo_validator import get_git_commit_hash
            commit_id = get_git_commit_hash(repo_path) or None

        from datetime import datetime
        metadata = {
            "generation_info": {
                "commit_id": commit_id,
                "timestamp": datetime.now().isoformat(),
            },
        }
        from codewiki.src.config import meta_join
        meta_dir = Path(meta_join(output_dir, ""))
        meta_dir.mkdir(parents=True, exist_ok=True)
        Path(meta_join(output_dir, "metadata.json")).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Failed to write metadata.json: %s", e)


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
