"""
Centralized tool schema registry and dispatch for the CodeWiki MCP server.

This module defines all Tool() schemas in one place and provides a unified
dispatch mechanism that dynamically imports and invokes the appropriate handler
based on the tool's execution mode.

Execution modes:
  - "main_thread": handler is called synchronously on the event loop thread
    (used for Tree-sitter operations that are not thread-safe).
  - "thread": handler is wrapped in asyncio.to_thread() to avoid blocking
    the event loop (most tools).
  - "async": handler is an async coroutine awaited directly.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)


# ===================================================================
#  ToolDef dataclass
# ===================================================================


@dataclasses.dataclass
class ToolDef:
    """Definition of a single MCP tool: its schema, handler location, and execution mode."""

    schema: Tool  # mcp.types.Tool
    handler_path: str  # e.g. "codewiki.mcp.tools.analysis:handle_analyze_repo"
    mode: str  # "main_thread", "thread", or "async"
    takes_store: bool = True  # whether the handler accepts a `store` parameter


# ===================================================================
#  REGISTRY — all tool definitions
# ===================================================================

REGISTRY: dict[str, ToolDef] = {}


def _register(schema: Tool, handler_path: str, mode: str, takes_store: bool = True) -> None:
    """Register a tool definition in the global REGISTRY."""
    REGISTRY[schema.name] = ToolDef(
        schema=schema,
        handler_path=handler_path,
        mode=mode,
        takes_store=takes_store,
    )


# -------------------------------------------------------------------
#  Fine-grained tools (no LLM config needed)
# -------------------------------------------------------------------

_register(
    Tool(
        name="analyze_repo",
        description=(
            "Analyze a code repository: Tree-sitter AST parsing → function-level call graph → "
            "dependency index. No LLM required. "
            "Results persist in SQLite and can be used in two independent workflows: "
            "(1) CODE ANALYSIS ONLY: follow up with list_dependencies, analyze_impact, "
            "list_components, read_code_components for call chain queries, blast-radius "
            "assessment, and code exploration — no wiki generation needed. "
            "(2) WIKI GENERATION: follow up with get_prompt('cluster') → save_module_tree → "
            "get_processing_order → write_doc_file. "
            "Both workflows share the same cached analysis; users can analyze first and "
            "generate docs later (incremental mode auto-reuses the cache). "
            "INCREMENTAL UPDATE: If docs already exist in output_dir (.meta/metadata.json + "
            ".meta/module_tree.json), the response includes a 'changes' field showing which "
            "files changed and which modules need updating. "
            "MONOREPO CROSS-SERVICE: automatically detects sub-services within a single "
            "repo (via docker-compose, Dockerfiles, build manifests, convention directories) "
            "and runs intra-repo cross-service matching (HTTP + MQ). Results appear in the "
            "'cross_service' response field and are persisted to <output_dir>/.meta/. "
            "Follow up with query_cross_service for filtered views."
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
                "detect_services": {
                    "type": "boolean",
                    "description": "Detect sub-services in monorepo and run intra-repo cross-service analysis (default: true).",
                    "default": True,
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.analysis:handle_analyze_repo",
    mode="main_thread",
)

_register(
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
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "component_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of component IDs to read",
                },
            },
            "required": ["repo_path", "component_ids"],
        },
    ),
    handler_path="codewiki.mcp.tools.code_reader:handle_read_code_components",
    mode="thread",
)

_register(
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
            "Provide output_dir or derive it from repo_path. "
            "MANDATORY FINAL STEP: after writing the LAST module doc, you MUST call "
            "close_session(repo_path=...) to build the BM25 search index + wikilink graph. "
            "query_wiki returns NOTHING until close_session runs — skipping it leaves the wiki unsearchable."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Derives output_dir = repo_path/repowiki.",
                },
                "filename": {
                    "type": "string",
                    "description": "Plain filename only (e.g., 'auth_module.md' or 'UserService.md'). Do NOT include directory paths — the page_type parameter handles routing automatically (entity → wiki/entities/, module → wiki/modules/, etc.).",
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
    handler_path="codewiki.mcp.tools.doc_writer:handle_write_doc_file",
    mode="async",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Derives output_dir = repo_path/repowiki.",
                },
                "filename": {
                    "type": "string",
                    "description": "Plain filename of the doc to edit (e.g., 'auth_module.md'). Do NOT include directory paths — page_type handles routing.",
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
            "required": ["filename", "command"],
        },
    ),
    handler_path="codewiki.mcp.tools.doc_writer:handle_edit_doc_file",
    mode="async",
)

_register(
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
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Derives output_dir = repo_path/repowiki.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for the module tree (default: repo_path/repowiki). Overrides repo_path-based default.",
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
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.module_tree:handle_save_module_tree",
    mode="thread",
)

_register(
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
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Derives output_dir = repo_path/repowiki.",
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.module_tree:handle_get_processing_order",
    mode="thread",
)

_register(
    Tool(
        name="get_prompt",
        description=(
            "Retrieve CodeWiki's prompt templates for each pipeline stage. "
            "Available prompt types and their purposes: "
            "Code analysis (standalone, no wiki): code_analysis (full analysis workflow), "
            "impact_review (interpret analyze_impact results + risk assessment), "
            "architecture_review (layer/hotspot/boundary analysis). "
            "Wiki generation: cluster (clustering rules), system_complex (parent module doc), "
            "system_leaf (leaf module doc), user (module doc writing guide), "
            "overview_module (module overview), overview_repo (repo overview), "
            "overview_workspace (multi-repo workspace architectural overview). "
            "Knowledge extraction: extraction_scan (entity/concept identification rules), "
            "entity_page (entity page template), concept_page (concept page template), "
            "source_summary (source document summary template). "
            "Wiki management: wiki_query (search query template), "
            "wiki_ingest (note ingestion guide), wiki_lint_report (quality report format). "
            "Advanced: comparison_page (comparison template), query_page (query result template), "
            "taxonomy_plan (knowledge taxonomy planning), "
            "reflection (proactive knowledge extraction from conversations). "
            "Optionally pass variables to fill in template placeholders. "
            "When variables produce content >4KB and a repo_path is provided, "
            "the prompt is written to a workspace file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt_type": {
                    "type": "string",
                    "enum": [
                        "code_analysis",
                        "impact_review",
                        "architecture_review",
                        "cluster",
                        "system_complex",
                        "system_leaf",
                        "user",
                        "overview_module",
                        "overview_repo",
                        "overview_workspace",
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
                        "reflection",
                    ],
                    "description": "Which prompt template to retrieve",
                },
                "variables": {
                    "type": "object",
                    "description": "Optional template variables to fill in",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Optional repository path — enables writing large prompts to workspace files",
                },
            },
            "required": ["prompt_type"],
        },
    ),
    handler_path="codewiki.mcp.tools.prompt_server:handle_get_prompt",
    mode="thread",
)

_register(
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
            "are up-to-date."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. output_dir is resolved from the session or cache, falling back to repo_path/repowiki.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional. Documentation output directory; overrides the session/cache-resolved value.",
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.close_session:handle_close_session",
    mode="thread",
)

# -------------------------------------------------------------------
#  LLM Wiki tools (zero LLM config, IDE-driven)
# -------------------------------------------------------------------

_register(
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
            "Set module_level=true to see inter-module dependencies instead of component-level. "
            "Auto-loads from SQLite cache if a previous analysis exists."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
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
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.crosslink:handle_list_dependencies",
    mode="thread",
)

_register(
    Tool(
        name="analyze_impact",
        description=(
            "Transitive dependency impact analysis. "
            "Given components (by ID or file path), traverse the dependency graph "
            "to find all transitively affected components. "
            "direction='depended_by' answers 'who depends on me, transitively?'; "
            "direction='depends_on' answers 'what do I depend on, transitively?'; "
            "direction='both' gives the union. "
            "Set include_paths=true to get shortest call-chain paths. "
            "Results include per-component depth, module-level aggregation, "
            "and high-risk components (many direct dependents). "
            "Use this to assess the blast radius of a code change. "
            "Auto-loads from SQLite cache — no prior analyze_repo needed in current session."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "component_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Component IDs to analyze (e.g. 'src/utils.py::parse_config')",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Source file paths; resolved to component IDs automatically",
                },
                "direction": {
                    "type": "string",
                    "enum": ["depended_by", "depends_on", "both"],
                    "description": "Traversal direction (default: depended_by)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum BFS depth in hops (default: 10, max: 50)",
                },
                "include_paths": {
                    "type": "boolean",
                    "description": "Include shortest call-chain paths in output (default: false)",
                },
            },
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.impact:handle_analyze_impact",
    mode="thread",
)

_register(
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
            "After fixing issues, use flag_issue to track remaining problems. "
            "MANDATORY FINAL STEP: after lint passes (or issues are tracked), you MUST call "
            "close_session(repo_path=...) — it builds the BM25 search index + wikilink graph "
            "that makes query_wiki work. The wiki is unsearchable until close_session runs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
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
    handler_path="codewiki.mcp.tools.wiki_lint:handle_lint_wiki",
    mode="thread",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
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
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_ingest_note",
    mode="thread",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
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
                "mode": {
                    "type": "string",
                    "enum": ["overview", "directory", "detail"],
                    "description": (
                        "Progressive reading mode. "
                        "'overview': returns overview.md + page frontmatter list (lightweight orientation). "
                        "'directory': returns Component Constraint Index sections from matching pages. "
                        "'detail': returns full content of a specific page/section (requires 'page' param). "
                        "Omit for standard BM25 search."
                    ),
                },
                "page": {
                    "type": "string",
                    "description": "Page path for mode=detail (relative to output_dir, e.g. 'wiki/modules/auth.md')",
                },
                "section": {
                    "type": "string",
                    "description": "Section heading for mode=detail (e.g. 'Business Constraints'). Omit for full page.",
                },
            },
            "required": ["query"],
        },
    ),
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_query_wiki",
    mode="thread",
)

# -------------------------------------------------------------------
#  LLM Wiki: knowledge flywheel (Roadmap 2.2)
# -------------------------------------------------------------------

_register(
    Tool(
        name="confirm_note",
        description=(
            "Confirm a candidate note, promoting it to verified domain knowledge. "
            "Confirmed notes are returned by query_wiki without the [unconfirmed] annotation. "
            "Use after a developer reviews and validates an LLM-generated note."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
                },
                "note_file": {
                    "type": "string",
                    "description": "Note filename relative to notes/ directory (e.g. '2026-07-26-jwt-decision.md')",
                },
            },
            "required": ["note_file"],
        },
    ),
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_confirm_note",
    mode="thread",
)

_register(
    Tool(
        name="reject_note",
        description=(
            "Reject a candidate note, excluding it from future query_wiki results. "
            "The note file is preserved but marked as rejected with an optional reason. "
            "Use when an LLM-generated note contains incorrect or duplicate information."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
                },
                "note_file": {
                    "type": "string",
                    "description": "Note filename relative to notes/ directory",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for rejection",
                },
            },
            "required": ["note_file"],
        },
    ),
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_reject_note",
    mode="thread",
)

# -------------------------------------------------------------------
#  LLM Wiki: third-party source management
# -------------------------------------------------------------------

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
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
    handler_path="codewiki.mcp.tools.source_ingest:handle_ingest_source",
    mode="thread",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
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
    handler_path="codewiki.mcp.tools.source_ingest:handle_retract_source",
    mode="thread",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
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
    handler_path="codewiki.mcp.tools.batch_ingest:handle_batch_ingest",
    mode="thread",
)

_register(
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
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-derives output_dir = repo_path/repowiki when not provided.",
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
    handler_path="codewiki.mcp.tools.issue_tracker:handle_flag_issue",
    mode="thread",
)

_register(
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
            "cross-service ingest_note / query_wiki at the parent level. "
            "\U0001f310 CROSS-SERVICE AUTO-ANALYSIS: after each repo is analyzed, runs "
            "RouteNode-based cross-service matching across Python/Java/JS/TS/Go + MQ "
            "(Kafka/RabbitMQ/RocketMQ/Celery), generates a Mermaid service topology "
            "flowchart + matched/unmatched route tables in overview.md, and scans "
            "docker-compose.yml/.env/application.yml to discover service names and ports. "
            "Persisted artifacts under <output_dir>/.meta/: cross_service_links.json, "
            "workspace_routes.json, infra_services.json. Follow up with query_cross_service "
            "for filtered views (by service/method/path/trace). "
            "\U0001f9e0 CBM ENHANCEMENT (if codebase-memory-mcp is available): use trace_path "
            "(mode='cross_service') on top of the local matches to get multi-hop semantic "
            "call chains across services."
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
    handler_path="codewiki.mcp.tools.workspace_analyzer:handle_analyze_workspace",
    mode="main_thread",
)

_register(
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
            "(e.g., 'class', 'function', 'interface'). "
            "Auto-loads from SQLite cache if a previous analysis exists."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
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
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.component_list:handle_list_components",
    mode="thread",
)

_register(
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
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "path": {
                    "type": "string",
                    "description": "Relative path from repo root (e.g. 'repowiki/overview.md' or 'backend/src/...')",
                },
            },
            "required": ["repo_path", "path"],
        },
    ),
    handler_path="codewiki.mcp.tools.file_viewer:handle_view_repo_file",
    mode="thread",
)

_register(
    Tool(
        name="query_cross_service",
        description=(
            "Query cross-service call relationships discovered during analyze_workspace "
            "or analyze_repo (monorepo mode). "
            "Matches HTTP routes (server declarations vs client calls) and MQ "
            "producer/consumer (Kafka/RabbitMQ/RocketMQ/Celery) across repos in a "
            "multi-repo workspace, or across sub-services within a monorepo. "
            "Languages covered: Python (FastAPI/Flask/Django + "
            "requests/httpx/aiohttp), Java (Spring MVC/JAX-RS + Feign/RestTemplate/"
            "WebClient), JS/TS (Express/NestJS + axios/fetch/got), Go (Gin/Chi/Echo/"
            "net/http). Path parameters (:id/{id}/<id>) are canonicalized to {} for "
            "framework-agnostic matching. "
            "Supports filter_type: 'all' (default, every link), 'by_service' (one repo's "
            "inbound/outbound links), 'by_method' (HTTP method), 'by_path' (URL "
            "substring), 'trace' (transitive call chain from a root service). "
            "Reads results persisted under <workspace>/workspace-wiki/.meta/ (multi-repo) "
            "or <repo>/repowiki/.meta/ (monorepo single-repo). "
            "\U0001f9e0 CBM ENHANCEMENT: pair with codebase-memory-mcp's trace_path "
            "(mode='cross_service') to extend the static RouteNode matches into multi-hop "
            "semantic call chains that traverse through internal functions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root (for analyze_workspace) or repo root (for analyze_repo monorepo mode). Auto-derives output_dir when omitted.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for workspace analysis .meta/ files. Overrides auto-derived path from workspace_path.",
                },
                "filter_type": {
                    "type": "string",
                    "enum": ["all", "by_service", "by_method", "by_path", "trace"],
                    "description": "Kind of query to run. Default 'all'.",
                    "default": "all",
                },
                "filter_value": {
                    "type": "string",
                    "description": "Value for the filter: service name, HTTP method, path substring, or root service for trace.",
                },
            },
            "required": ["workspace_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.cross_service:handle_query_cross_service",
    mode="thread",
    takes_store=False,
)

# -------------------------------------------------------------------
#  Legacy tools (require CodeWiki LLM config)
# -------------------------------------------------------------------

_register(
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
                    "description": "Type of documentation to generate. Valid values defined in schema.yaml doc_types.types (default: design)",
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
    handler_path="codewiki.mcp.tools.legacy_tools:handle_generate_docs",
    mode="async",
    takes_store=False,
)

_register(
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
    handler_path="codewiki.mcp.tools.legacy_tools:handle_get_module_tree",
    mode="async",
    takes_store=False,
)


_register(
    Tool(
        name="init_wiki",
        description=(
            "Initialize a Wiki workspace for a project (zero-config bootstrap). "
            "Creates the output directory structure (wiki/modules, wiki/entities, "
            "wiki/concepts, wiki/sources, wiki/comparisons, wiki/queries, notes/), "
            "copies the annotated schema.yaml template (preserving comments), and "
            "injects wiki usage instructions + self-reflection protocols into the "
            "project's AGENTS.md. Run this ONCE before starting any wiki generation "
            "or knowledge ingestion workflow. Idempotent: safe to re-run — existing "
            "AGENTS.md content outside the CodeWiki markers is preserved."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository root path. AGENTS.md is written here. Default: current working directory.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki). Created if it does not exist.",
                },
            },
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.init_wiki:handle_init_wiki",
    mode="thread",
    takes_store=False,
)


# ===================================================================
#  Public API
# ===================================================================


def get_all_tools() -> list[Tool]:
    """Return all registered tool schemas."""
    return [tool_def.schema for tool_def in REGISTRY.values()]


# ===================================================================
#  CBM enrichment (post-dispatch hook)
# ===================================================================

# Tools eligible for CBM enrichment and their enrichment strategy
_CBM_ENRICHABLE = {"query_cross_service", "analyze_impact", "analyze_repo"}


async def _try_cbm_enrichment(
    tool_name: str,
    arguments: dict[str, Any],
    result: Any,
) -> Any:
    """Attempt to enrich a tool result with CBM data.

    Only applies to specific tools (query_cross_service, analyze_impact).
    Returns the original result unchanged if:
      - CBM is not installed/enabled
      - The tool is not enrichable
      - CBM call fails for any reason
      - The result is not a JSON string (e.g. TextContent passthrough)
    """
    if tool_name not in _CBM_ENRICHABLE:
        return result

    # Only enrich JSON string results
    if not isinstance(result, str):
        return result

    try:
        from codewiki.mcp.cbm_client import is_cbm_enabled
        if not is_cbm_enabled():
            return result

        from codewiki.mcp.tools.cbm_integration import (
            cbm_detect_changes,
            cbm_get_architecture,
            cbm_trace_cross_service,
            merge_cbm_and_local_results,
        )

        parsed = json.loads(result)

        # Skip if the handler returned an error
        if "error" in parsed:
            return result

        if tool_name == "query_cross_service":
            # Enrich trace queries with CBM cross-service paths
            filter_type = arguments.get("filter_type", "all")
            if filter_type == "trace":
                filter_value = arguments.get("filter_value", "")
                if filter_value:
                    cbm_result = await cbm_trace_cross_service(
                        function_name=filter_value,
                        repo_path=arguments.get("workspace_path", ""),
                    )
                    if cbm_result:
                        parsed = merge_cbm_and_local_results(parsed, cbm_result)
                        parsed["_cbm_enriched"] = True

        elif tool_name == "analyze_impact":
            # Enrich with CBM architecture data (clusters for module context)
            repo_path = arguments.get("repo_path", "")
            if not repo_path:
                # Try to get from session — skip if not available
                return result
            cbm_arch = await cbm_get_architecture(
                repo_path=repo_path,
                aspects=["clusters", "hotspots"],
            )
            if cbm_arch:
                parsed["cbm_architecture"] = cbm_arch
                parsed["_cbm_enriched"] = True

            # Enrich with git-diff blast radius (symbol-level risk grading)
            cbm_changes = await cbm_detect_changes(
                repo_path=repo_path,
                scope="impact",
                direction="inbound",
                depth=2,
                since="HEAD~5",
            )
            if cbm_changes:
                parsed["cbm_change_impact"] = cbm_changes
                parsed["_cbm_enriched"] = True

        elif tool_name == "analyze_repo":
            # Enrich incremental updates with CBM risk grading
            changes = parsed.get("changes")
            if not changes or changes.get("no_changes"):
                return result
            repo_path = arguments.get("repo_path", "")
            if not repo_path:
                return result
            cbm_risk = await cbm_detect_changes(
                repo_path=repo_path,
                scope="impact",
                direction="inbound",
                depth=2,
                since="HEAD~1",
            )
            if cbm_risk:
                changes["cbm_risk"] = cbm_risk
                parsed["_cbm_enriched"] = True

        if parsed.get("_cbm_enriched"):
            return json.dumps(parsed, ensure_ascii=False)

    except Exception as e:
        # Never let CBM enrichment break the main tool
        logger.debug("CBM enrichment skipped for %s: %s", tool_name, e)

    return result


async def dispatch(name: str, arguments: dict[str, Any], store: Any) -> list[TextContent]:
    """Look up a tool by name, dynamically import its handler, and invoke it.

    Args:
        name: The MCP tool name (must exist in REGISTRY).
        arguments: The tool arguments dict from the MCP request.
        store: The SessionStore instance (passed to handlers that need it).

    Returns:
        A list containing a single TextContent with the JSON result.

    Raises:
        No exceptions propagate — errors are caught and returned as JSON error payloads,
        matching the behavior of the original call_tool in server.py.
    """
    try:
        tool_def = REGISTRY.get(name)
        if tool_def is None:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        # Dynamically import the handler function
        module_path, func_name = tool_def.handler_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)

        # Invoke according to execution mode
        if tool_def.mode == "main_thread":
            # Called directly on the event loop thread (Tree-sitter is not thread-safe)
            if tool_def.takes_store:
                result = handler(arguments, store)
            else:
                result = handler(arguments)

        elif tool_def.mode == "thread":
            # Wrapped in asyncio.to_thread to avoid blocking the event loop
            if tool_def.takes_store:
                result = await asyncio.to_thread(handler, arguments, store)
            else:
                result = await asyncio.to_thread(handler, arguments)

        elif tool_def.mode == "async":
            # Handler is an async coroutine — await directly
            if tool_def.takes_store:
                result = await handler(arguments, store)
            else:
                result = await handler(arguments)

        else:
            return [TextContent(type="text", text=json.dumps({
                "error": f"Invalid mode '{tool_def.mode}' for tool '{name}'"
            }))]

        # --- CBM enrichment (best-effort, async) ---
        result = await _try_cbm_enrichment(name, arguments, result)

        # Wrap result in TextContent
        if isinstance(result, list) and result and isinstance(result[0], TextContent):
            # Handler already returned list[TextContent] (e.g. legacy tools)
            return result
        if isinstance(result, TextContent):
            return [result]
        return [TextContent(type="text", text=result if isinstance(result, str) else json.dumps(result))]

    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
