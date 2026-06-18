"""
CodeWiki MCP Server.

Provides two sets of tools:

**Fine-grained tools (IDE-driven, zero LLM config):**
  - ``analyze_repo``      — Parse a repo and build a dependency graph (session-based)
  - ``read_code_components`` — Read source code for given component IDs
  - ``view_repo_file``    — Read-only file/directory browsing
  - ``write_doc_file``    — Create a documentation .md file with Mermaid validation
  - ``edit_doc_file``     — Edit a documentation file (str_replace / insert / undo)
  - ``save_module_tree``  — Persist IDE agent's module clustering
  - ``get_processing_order`` — Get leaf-first documentation order
  - ``get_prompt``        — Retrieve CodeWiki's prompt templates
  - ``close_session``     — Clean up a session

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

from codewiki.mcp.session import SessionStore

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
                "using Tree-sitter AST parsing. Returns a component index and leaf nodes. "
                "No LLM required. This is the entry point for the wiki generation pipeline. "
                "After calling this, use get_prompt('cluster') to learn clustering rules, "
                "then save_module_tree to persist your grouping."
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
                "Read the source code for a list of component IDs. "
                "Component IDs have the form 'file_path::ComponentName'. "
                "Returns the source code with language-aware code fences."
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
            name="view_repo_file",
            description=(
                "Read-only view of a file or directory inside the analyzed repository. "
                "Use this to explore code that isn't in the component index."
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
                        "description": "Relative path within the repository",
                    },
                    "view_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional [start_line, end_line] (1-indexed, -1 for end)",
                    },
                },
                "required": ["session_id", "path"],
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
                },
                "required": ["session_id", "filename", "content"],
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
                "Returns the recommended leaf-first processing order."
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
                },
                "required": ["session_id", "module_tree"],
            },
        ),
        Tool(
            name="get_processing_order",
            description=(
                "Get the leaf-first processing order for documentation generation. "
                "Process leaf modules (is_leaf=true) before parent modules."
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
                "fill in template placeholders."
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
                        ],
                        "description": "Which prompt template to retrieve",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Optional template variables to fill in",
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
                        "enum": ["api", "architecture", "user-guide", "developer"],
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
        if name == "analyze_repo":
            from codewiki.mcp.tools.analysis import handle_analyze_repo
            return [_text(handle_analyze_repo(arguments, _store))]

        elif name == "read_code_components":
            from codewiki.mcp.tools.code_reader import handle_read_code_components
            return [_text(handle_read_code_components(arguments, _store))]

        elif name == "view_repo_file":
            from codewiki.mcp.tools.code_reader import handle_view_repo_file
            return [_text(handle_view_repo_file(arguments, _store))]

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
            return [_text(handle_save_module_tree(arguments, _store))]

        elif name == "get_processing_order":
            from codewiki.mcp.tools.module_tree import handle_get_processing_order
            return [_text(handle_get_processing_order(arguments, _store))]

        elif name == "get_prompt":
            from codewiki.mcp.tools.prompt_server import handle_get_prompt
            return [_text(handle_get_prompt(arguments, _store))]

        elif name == "close_session":
            sid = arguments["session_id"]
            removed = _store.remove(sid)
            return [_text(json.dumps({
                "status": "closed" if removed else "not_found",
                "session_id": sid,
            }))]

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

    from codewiki.src.be.documentation_generator import DocumentationGenerator
    doc_gen = DocumentationGenerator(backend_config)
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

    module_tree_path = output_dir / "module_tree.json"
    if not module_tree_path.exists():
        return [_text(json.dumps({
            "error": f"Module tree not found at {module_tree_path}. Run 'codewiki generate' first."
        }))]

    module_tree = json.loads(module_tree_path.read_text())

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
