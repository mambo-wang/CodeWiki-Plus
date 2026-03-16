"""
CodeWiki MCP Server.

Exposes documentation generation as MCP tools:
  - generate_docs: Generate full documentation for a repository
  - analyze_repo: Analyze repository structure and dependencies
  - get_module_tree: Get the module clustering for a repository

Usage:
    # Run as standalone MCP server (stdio transport)
    python -m codewiki.mcp.server

    # Or register in your MCP client config:
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
from mcp.types import (
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

# Create the MCP server
server = Server("codewiki")


def _load_config():
    """Load CodeWiki configuration from ~/.codewiki/config.json + keyring."""
    from codewiki.cli.config_manager import ConfigManager
    manager = ConfigManager()
    if not manager.load():
        raise RuntimeError(
            "CodeWiki not configured. Run 'codewiki config set' first."
        )
    return manager


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available CodeWiki MCP tools."""
    return [
        Tool(
            name="generate_docs",
            description=(
                "Generate comprehensive AI-powered documentation for a code repository. "
                "Analyzes dependencies, clusters modules, and generates markdown documentation."
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
            name="analyze_repo",
            description=(
                "Analyze a repository's structure, dependencies, and component hierarchy "
                "without generating full documentation. Returns file counts, languages, "
                "and dependency information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to analyze",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="get_module_tree",
            description=(
                "Get the module clustering tree for a repository. "
                "Shows how source files are grouped into logical modules."
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
                        "description": "Directory containing generated docs (default: ./docs)",
                        "default": "docs",
                    },
                },
                "required": ["repo_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle MCP tool calls."""
    try:
        if name == "generate_docs":
            return await _handle_generate_docs(arguments)
        elif name == "analyze_repo":
            return await _handle_analyze_repo(arguments)
        elif name == "get_module_tree":
            return await _handle_get_module_tree(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return [TextContent(type="text", text=f"Error: {e}")]


async def _handle_generate_docs(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle generate_docs tool call."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    output_dir = Path(arguments.get("output_dir", "docs")).expanduser().resolve()

    if not repo_path.exists():
        return [TextContent(type="text", text=f"Repository not found: {repo_path}")]

    # Load config
    manager = _load_config()
    config = manager.get_config()
    api_key = manager.get_api_key()

    if not api_key:
        return [TextContent(type="text", text="API key not configured. Run 'codewiki config set --api-key <key>'")]

    # Build agent instructions from arguments
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

    # Run generation
    await doc_gen.run()

    # Collect results
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
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_analyze_repo(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle analyze_repo tool call — lightweight dependency analysis only."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()

    if not repo_path.exists():
        return [TextContent(type="text", text=f"Repository not found: {repo_path}")]

    manager = _load_config()
    config = manager.get_config()
    api_key = manager.get_api_key()

    from codewiki.src.config import Config as BackendConfig, set_cli_context
    set_cli_context(True)

    # Create a minimal backend config (no LLM calls needed for analysis)
    backend_config = BackendConfig.from_cli(
        repo_path=str(repo_path),
        output_dir=str(repo_path / ".codewiki_temp"),
        llm_base_url=config.base_url or "http://localhost",
        llm_api_key=api_key or "not-needed",
        main_model=config.main_model or "unused",
        cluster_model=config.cluster_model or "unused",
        fallback_model=config.fallback_model or "unused",
    )

    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    graph_builder = DependencyGraphBuilder(backend_config)
    components, leaf_nodes = graph_builder.build_dependency_graph()

    # Aggregate statistics
    languages = {}
    files = set()
    for comp in components.values():
        lang = getattr(comp, "language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1
        files.add(getattr(comp, "relative_path", ""))

    result = {
        "status": "success",
        "repo_path": str(repo_path),
        "total_components": len(components),
        "total_files": len(files),
        "leaf_nodes": len(leaf_nodes),
        "languages": languages,
        "sample_components": sorted(list(components.keys()))[:20],
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_get_module_tree(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_module_tree tool call — returns existing module tree."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    output_dir = Path(arguments.get("output_dir", "docs")).expanduser().resolve()

    module_tree_path = output_dir / "module_tree.json"
    if not module_tree_path.exists():
        return [TextContent(
            type="text",
            text=f"Module tree not found at {module_tree_path}. Run 'codewiki generate' first."
        )]

    module_tree = json.loads(module_tree_path.read_text())

    def _summarize_tree(tree, depth=0):
        """Create a readable summary of the module tree."""
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
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
