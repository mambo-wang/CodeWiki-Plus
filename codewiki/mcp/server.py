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
server = Server("codewiki")


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
                        "description": "Output directory for generated docs (default: <repo>/docs)",
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
                "in the session's sources/ directory. Returns file paths — no truncation."
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
                "Automatically validates Mermaid diagrams after writing."
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
                },
                "required": ["session_id", "filename"],
            },
        ),
        Tool(
            name="edit_doc_file",
            description=(
                "Edit an existing documentation file. Supports str_replace (find-and-replace), "
                "insert (add text at a line), and undo (revert last edit). "
                "Automatically validates Mermaid diagrams after editing."
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
                "Returns the file path for the processing order."
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
                "Returns the file path. Process leaf modules (is_leaf=true) before parent modules."
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
                "Available types: cluster, system_complex, system_leaf, user, "
                "overview_module, overview_repo. Optionally pass variables to "
                "fill in template placeholders. When variables produce content "
                ">4KB and a session_id is provided, the prompt is written to "
                "a workspace file."
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
            description="Close and clean up an analysis session to free memory.",
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
                "Supports component-level and module-level aggregation."
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
                "Check documentation-code consistency. Detects stale references, "
                "broken links, undocumented high-impact components, circular dependencies, "
                "and coverage gaps. Works with or without an active session."
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
                            "enum": ["all", "stale_refs", "undocumented", "broken_links", "cycles", "coverage"],
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
                "File a structured note (decision, lesson learned, architecture rationale) "
                "into the knowledge base. Notes are stored in repowiki/notes/ with "
                "YAML frontmatter and indexed in decisions_index.json."
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
                        "enum": ["decision", "lesson", "architecture", "bug_fix", "general"],
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
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="query_wiki",
            description=(
                "Search across generated documentation and ingested notes. "
                "Returns ranked results with snippets and a context_package summary "
                "for IDE agents to use as development context."
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
                        "description": "Limit search to a specific module",
                    },
                    "include_notes": {
                        "type": "boolean",
                        "description": "Include ingested notes in search (default: true)",
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
                },
                "required": ["query"],
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
                "Use this after analyze_repo to discover components for "
                "clustering or source reading. Supports filtering by "
                "file_prefix and component_type."
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
                "Use this to read already-generated .md docs (for parent module "
                "synthesis) or browse source files for extra context. "
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
                        "description": "Output directory for generated docs (default: ./docs)",
                        "default": "docs",
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
            description="Get the existing module clustering tree for a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory containing generated docs (default: ./docs)",
                        "default": "docs",
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
    output_dir = Path(arguments.get("output_dir", "docs")).expanduser().resolve()

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
    output_dir = Path(arguments.get("output_dir", "docs")).expanduser().resolve()

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
