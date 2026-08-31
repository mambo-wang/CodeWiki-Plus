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

# V4 (note_types 权威表): note_type 枚举从声明表生成——一处定义，
# registry inputSchema / distill _VALID_NOTE_TYPES / promotion 路由同源。
# 项目 schema 的自定义类型受 MCP 静态校验所限仍走包内默认表（重启生效），
# 已知约束记录于 docs/OpenViking借鉴详细设计方案-P3四项.md §1.2。
from codewiki.mcp.tools.note_types import DEFAULT_NOTE_TYPES as _NOTE_TYPES
from codewiki.mcp.tools.workspace_layout import VALID_LAYOUTS

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

# note_type 权威表导入移至文件顶部 import 区（E402）；设计说明见顶部注释。
_NOTE_TYPE_ENUM = sorted(_NOTE_TYPES)


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
    mode="thread",  # was "main_thread" — blocked event loop, preventing ping responses
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
            "The filename parameter specifies the plain file name (e.g., 'auth_module.md'). "
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
                    "enum": [
                        "module",
                        "entity",
                        "concept",
                        "source",
                        "comparison",
                        "query",
                        "scenario",
                    ],
                    "description": "LLM Wiki page type. Determines subdirectory routing (default: module → wiki/modules/)",
                },
                "scope": {
                    "description": (
                        "Centralized-layout shared-pool scope for non-module pages. "
                        "Omit to auto-stamp the writing repo; 'global' for product-line "
                        "knowledge applicable to every repo (no provenance tag); or a list "
                        "of repo names (or comma-separated string) to tag exactly those. "
                        "Ignored outside centralized workspaces and for module pages."
                    ),
                },
                "frontmatter_extra": {
                    "type": "object",
                    "description": (
                        "Additional frontmatter fields merged into the doc header. "
                        "Common keys: aliases (list), category (str), domain (str), "
                        "origin (str), severity (str), related_modules (list), "
                        "source_refs (list), chunk_refs (list). "
                        "Do NOT pass component-id lists (components) — they bloat "
                        "frontmatter and no tool reads them back; component_count "
                        "is written automatically when needed. "
                        "OKF v0.2 standard keys (status/tags/description) are written "
                        "at the top level; everything else folds under `metadata:`."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Override the auto-generated page title in frontmatter. If omitted, the title is derived from the filename.",
                },
                "description": {
                    "type": "string",
                    "description": "Override the auto-generated description in frontmatter. If omitted, a description is extracted from the first paragraph of content.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Override the auto-generated tags in frontmatter. If omitted, tags are derived from the module tree and schema conventions.",
                },
                "strict": {
                    "type": "boolean",
                    "description": "Optional, default false. When true, Mermaid validation failure blocks the write and returns an error. When false (default), invalid diagrams are written with a mermaid_warnings field in the response.",
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
            "Edit an existing documentation file. The command parameter accepts three values: "
            "'str_replace' (find-and-replace, requires old_string + new_string), "
            "'insert' (add text at a specific line, requires new_string + insert_line), "
            "'undo' (revert the last edit). "
            "Automatically validates Mermaid diagrams after editing. "
            "For large replacements, use old_string_file/new_string_file instead of inline strings. "
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
                    "enum": [
                        "module",
                        "entity",
                        "concept",
                        "source",
                        "comparison",
                        "query",
                        "scenario",
                    ],
                    "description": "LLM Wiki page type for path resolution (default: module)",
                },
                "old_string": {
                    "type": "string",
                    "description": "String to find (required for str_replace)",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string (for str_replace/insert)",
                },
                "old_string_file": {
                    "type": "string",
                    "description": "Alternative to old_string: absolute path to a text file.",
                },
                "new_string_file": {
                    "type": "string",
                    "description": "Alternative to new_string: absolute path to a text file.",
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
            "Accepts a module tree object (dict, not a JSON string) and persists it to disk. "
            "Computes the leaf-first processing order and writes it to a workspace file. "
            "Returns the file path for the processing order. "
            "Call this after analyze_repo + get_prompt('cluster') to persist your grouping. "
            "The module tree format: each key is a module name, value is a dict "
            "{'components': [component_ids], 'children': {nested module dict}}. "
            "The children field must be a dict/object (not an array). "
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
            "extraction_dedup (deduplication decision rules: related ≠ same), "
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
                        "extraction_dedup",
                        "reflection",
                        "consolidate",
                    ],
                    "description": "Which prompt template to retrieve",
                },
                "variables": {
                    "type": "object",
                    "description": "Optional template variables to fill in",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional bundle directory (contains schema.yaml) — most direct way to enable schema-constraint injection (incl. the OKF v0.2 block)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Optional repository path — derives <repo>/repowiki and enables writing large prompts to workspace files",
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
            "3) optionally injects wiki usage instructions into the target project's AGENTS.md "
            "(enable with update_agents_md=true), "
            "4) cleans up workspace files on disk. "
            "Always call this after finishing documentation work to ensure search indexes "
            "are up-to-date. "
            "If the session was already closed, a normal call returns status='already_closed' "
            "without rebuilding; pass force=true to force a full rebuild anyway."
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
                "force": {
                    "type": "boolean",
                    "description": (
                        "Optional, default false. When true, always perform the full rebuild "
                        "(metadata.json, indexes, reading guide) even if the session was already "
                        "closed. When false and the session is already closed, the call returns "
                        "status='already_closed' and does nothing."
                    ),
                },
                "update_agents_md": {
                    "type": "boolean",
                    "description": (
                        "Optional, default false. When true, inject/update the CodeWiki section in "
                        "the target project's root AGENTS.md. When false, skip the AGENTS.md "
                        "modification entirely. The response reports the outcome via "
                        "'agents_md_updated'."
                    ),
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
        name="analyze_changes",
        description=(
            "Git-diff driven blast-radius analysis: answer 'what does my change affect?' "
            "after editing code. Two input modes: since=<commit range> (e.g. 'HEAD~1' for "
            "git diff <since>..HEAD) or worktree=true (uncommitted staged + unstaged + "
            "untracked changes, default). The diff is parsed at LINE level and matched "
            "against component line spans, so the analysis starts from the exact functions "
            "whose lines changed (not whole files). Then runs transitive impact "
            "(direction='depended_by' answers who calls the changed functions, transitively) "
            "and suggests regression test files by naming convention. "
            "Auto-loads from SQLite cache — no prior analyze_repo needed in current session. "
            "Use analyze_impact for pre-change assessment on a specific function; use "
            "analyze_changes for post-change assessment on a diff."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "since": {
                    "type": "string",
                    "description": "Committed range: git diff <since>..HEAD (e.g. 'HEAD~1', or a commit hash). Mutually exclusive with worktree (takes precedence).",
                },
                "worktree": {
                    "type": "boolean",
                    "description": "Analyze uncommitted changes (staged + unstaged + untracked). Default: true.",
                    "default": True,
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
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.change_analysis:handle_analyze_changes",
    mode="thread",
)

_register(
    Tool(
        name="review_changes",
        description=(
            "Git-diff driven code review evidence assembly: answer 'is my change correct?' "
            "after editing code, against four review axes — spec (SPEC/design docs, explicit "
            "paths or auto-discovered under docs/specs/.scratch/openspec), convention "
            "(project wiki conventions + Doctrine), module_knowledge (pitfall/lesson/decision "
            "notes of the changed module), general (built-in engineering checklist + project "
            "override). Deterministic and LLM-free (Doctrine: reasoning stays with the caller): "
            "mode='prepare' assembles the review context package (diff + annotated changed "
            "sources + four-axis evidence) and writes it to the workspace; the caller agent "
            "reviews it and may archive the structured report with mode='submit'. "
            "Judgment order when axes conflict: spec > convention > module_knowledge > general. "
            "Same input source as analyze_changes (since range or uncommitted worktree) but "
            "analyze_changes answers impact, review_changes answers quality."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["prepare", "submit"],
                    "description": "prepare (default) assembles the review context package; submit validates and archives the caller's report.",
                },
                "since": {
                    "type": "string",
                    "description": "Committed range: git diff <since>..HEAD (e.g. 'HEAD~1', or a commit hash). Omitted = uncommitted changes. In since mode changed sources are read from HEAD so they match the diff exactly.",
                },
                "spec_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit SPEC/design doc paths (relative to repo_path or absolute). Auto-discovery runs only when no explicit path yields a readable file.",
                },
                "focus": {
                    "type": "string",
                    "enum": ["all", "spec", "convention", "module_knowledge", "general"],
                    "description": "Restrict evidence assembly to one axis (default: all).",
                },
                "report": {
                    "type": "object",
                    "description": "Submit only: the review report {title, findings: [{id, axis, severity, file, line, title, evidence, suggestion, rule_ref}], summary}.",
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.review_changes:handle_review_changes",
    mode="thread",
)

_register(
    Tool(
        name="watch_repo",
        description=(
            "Start/stop/query the background graph watcher for a repository. "
            "Keeps the dependency graph in sync with disk without manual "
            "analyze_repo re-runs: a background thread polls for file changes "
            "(fingerprint-based, idempotent) and incrementally re-parses only "
            "the changed files, then swaps the session's component store to the "
            "refreshed graph. Query tools (analyze_impact etc.) attach a "
            "graph_stale flag while watch is active. Saves within one poll "
            "interval are coalesced into a single refresh batch (debounce). "
            "On an unexpected failure the watcher degrades gracefully to manual "
            "mode and logs the error."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository path. Auto-loads from SQLite cache if a previous analysis exists.",
                },
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "status"],
                    "description": "start (default) launches the background poller; stop halts it; status reports state.",
                },
                "interval": {
                    "type": "number",
                    "description": "Poll interval in seconds (default 2.0, minimum 1.0). Changes within one interval are merged into a single refresh.",
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.watch:handle_watch_repo",
    mode="thread",
)

_register(
    Tool(
        name="lint_wiki",
        description=(
            "Check documentation-code consistency. Works with or without an active session. "
            "Runs 21 available checks: stale_refs (docs reference deleted components), "
            "broken_links (markdown links to non-existent pages), "
            "undocumented (high-impact components without docs), "
            "cycles (circular module dependencies), coverage (documentation coverage gaps), "
            "orphan_pages (pages with no inbound links), no_outlinks (pages with no cross-references), "
            "missing_aliases (pages without search aliases), stale_sources (retracted source refs), "
            "superseded_pages (pages marked as superseded), "
            "isolated_components (components with zero dependencies and zero dependents), "
            "overview_stale (overview.md references modules that have changed), "
            "unsupported_claims (business assertions lacking code evidence), "
            "stale_evidence (repo:// code evidence whose content hash drifted or whose "
            "file disappeared — re-verify the fact and re-stamp via stamp_evidence), "
            "stale_notes (stable/confirmed notes whose type-aware stale_after review "
            "deadline has passed without a recent retrieval; confirm_note renews), "
            "note_clusters (modules with 3+ same-type notes suggesting consolidation), "
            "low_adoption (stable notes recalled 5+ times within the recent window yet "
            "never adopted — relevant but not actionable; rewrite with concrete "
            "steps/commands/expected results via the distill/edit flow), "
            "okf_conformance (OKF v0.2 audit: missing type/frontmatter, legacy statuses, "
            "malformed verified, expired stale_after, missing okf_version), "
            "scenario_capacity (L2 scene blocks at/over the consolidation cap — "
            "merge similar scenes before adding more), "
            "scenario_orphan (scene blocks with no source_notes provenance and no "
            "recent retrieval — possibly redundant or outdated). "
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
                            "all",
                            "stale_refs",
                            "undocumented",
                            "broken_links",
                            "cycles",
                            "coverage",
                            "orphan_pages",
                            "no_outlinks",
                            "missing_aliases",
                            "stale_sources",
                            "superseded_pages",
                            "isolated_components",
                            "overview_stale",
                            "unsupported_claims",
                            "stale_evidence",
                            "stale_notes",
                            "note_clusters",
                            "low_adoption",
                            "okf_conformance",
                            "scenario_capacity",
                            "scenario_orphan",
                            "layout_violations",
                        ],
                    },
                    "description": 'Which checks to run (default: ["all"])',
                },
                "severity_filter": {
                    "type": "string",
                    "enum": ["error", "warning", "info"],
                    "description": "Minimum severity to report (default: info)",
                },
                "fix": {
                    "type": "boolean",
                    "description": (
                        "When true, self-heal a stale wiki index: if the only stale_refs "
                        "are references inside wiki/index.md to removed files, rebuild "
                        "the index BEFORE running the checks, so every check (stale_refs, "
                        "broken_links, ...) sees the rebuilt index. Content files are "
                        "never modified. Default: false."
                    ),
                },
            },
        },
    ),
    handler_path="codewiki.mcp.tools.wiki_lint:handle_lint_wiki",
    mode="thread",
)

_register(
    Tool(
        name="stamp_evidence",
        description=(
            "Attach content-hashed code evidence to a wiki page's OKF sources list. "
            "Each evidence item names a repo:// code region (e.g. repo://src/x.py#L10-L40, "
            "or a whole file with no #L range); the tool records the region's current "
            "content hash so lint_wiki's stale_evidence check can later flag drifted "
            "facts. Evidence only drives review reminders — it never rewrites content. "
            "Call this after write_doc_file/edit_doc_file when a page asserts facts about "
            "specific code locations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "Page path relative to output_dir (e.g. 'wiki/modules/auth.md').",
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource": {
                                "type": "string",
                                "description": "repo:// resource URI: 'repo://<rel-path>' (whole file) or 'repo://<rel-path>#L<start>-L<end>' (line range).",
                            }
                        },
                        "required": ["resource"],
                    },
                    "description": "Code regions this page's facts are grounded in.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for wiki pages.",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path; evidence resources resolve against this root.",
                },
            },
            "required": ["page", "evidence"],
        },
    ),
    handler_path="codewiki.mcp.tools.evidence:handle_stamp_evidence",
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
                "scope": {
                    "description": (
                        "Centralized-layout shared-pool scope. Omit to auto-stamp the "
                        "writing repo; 'global' for product-line knowledge applicable to "
                        "every repo (no provenance tag); or a list of repo names (or "
                        "comma-separated string) to tag exactly those. Ignored outside "
                        "centralized workspaces."
                    ),
                },
                "note_type": {
                    "type": "string",
                    "enum": _NOTE_TYPE_ENUM,
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
                "status": {
                    "type": "string",
                    "enum": ["draft", "stable"],
                    "description": (
                        "Initial lifecycle status (OKF v0.2 vocabulary, default: draft). "
                        "Use 'stable' only when the knowledge is already human-verified."
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task id to route this note to (surfaced by query_wiki task_id filter and get_task_context).",
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
                "repo": {
                    "type": "string",
                    "description": (
                        "Centralized-layout scope filter: narrow results to the knowledge "
                        "applicable to one business repo = its wiki/modules/<repo>/ partition "
                        "+ shared-pool pages tagged with it + untagged product-line (global) "
                        "pages. Omit for a one-hop search across the whole workspace. "
                        "Combined with output_dir, the filter applies within that corpus. "
                        "Ignored outside centralized workspaces."
                    ),
                },
                "type_filter": {
                    "type": "string",
                    "enum": [
                        "doc",
                        "note",
                        "module",
                        "entity",
                        "concept",
                        "source",
                        "comparison",
                        "query",
                    ],
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
                        "When true, return full page content (up to max_chars, "
                        "default 3000) in a 'content' field instead of just snippets. "
                        "Use for deep reading after identifying relevant pages with "
                        "a normal search."
                    ),
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        "Content budget in characters for expand=true "
                        "(default: 3000, max: 20000). Use 12000-20000 for "
                        "full-page deep reading of complex pages; keep 3000 "
                        "for quick verification."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["overview", "directory", "detail", "check"],
                    "description": (
                        "Progressive reading mode. "
                        "'overview': returns overview.md + page frontmatter list (lightweight orientation). "
                        "'directory': returns Component Constraint Index sections from matching pages. "
                        "'detail': returns full content of a specific page/section (requires 'page' param). "
                        "'check': lightweight relevance pre-check — returns relevant flag, top score "
                        "and top-3 titles WITHOUT snippets or stats recording. Use it before deciding "
                        "whether a full search is worth the tokens. "
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
                "task_id": {
                    "type": "string",
                    "description": "Optional task id to filter notes by (note-scoped; docs/sources are unaffected). Never validates task existence.",
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
            "Confirm a draft note, promoting it to stable domain knowledge (OKF v0.2 lifecycle). "
            "Records a verified event ({by, at}) in the note's frontmatter and renews its stale_after date. "
            "Stable notes are returned by query_wiki without the [unconfirmed] annotation. "
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
                "by": {
                    "type": "string",
                    "description": (
                        "OKF actor id recording who verified the note, e.g. 'human:mambo-wang' "
                        "for a person or 'codewiki/5.2.0' for a tool (default: tool actor id)"
                    ),
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
        name="batch_set_status",
        description=(
            "Batch-promote generated wiki pages and/or notes from draft to stable "
            "(or to deprecated) in one call (OKF v0.2 lifecycle). Scans the output "
            "directory, rewrites the frontmatter status of every matching document, "
            "and — like confirm_note — appends a verified event ({by, at}) and renews "
            "stale_after for stable promotions. "
            "Use after the user has reviewed and approved a batch of generated pages. "
            "Supports dry_run to preview the affected files first, and scope='wiki' "
            "|'notes'|'all' to restrict where to scan."
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
                "status": {
                    "type": "string",
                    "description": "Target status: 'stable' (default) or 'deprecated'.",
                    "default": "stable",
                },
                "scope": {
                    "type": "string",
                    "description": "Which documents to scan: 'all' (default), 'wiki', or 'notes'.",
                    "default": "all",
                },
                "only_draft": {
                    "type": "boolean",
                    "description": "Only promote documents currently in draft status (default true).",
                    "default": True,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview which files would change without writing anything (default false).",
                    "default": False,
                },
                "renew_stale_after": {
                    "type": "boolean",
                    "description": "Renew stale_after on promotion to stable (default true).",
                    "default": True,
                },
                "by": {
                    "type": "string",
                    "description": (
                        "OKF actor id recording who verified the documents, e.g. 'human:mambo-wang' "
                        "for a person or 'codewiki/5.2.0' for a tool (default: tool actor id)"
                    ),
                },
            },
            "required": ["repo_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_batch_set_status",
    mode="thread",
)

_register(
    Tool(
        name="reject_note",
        description=(
            "Reject a draft note, excluding it from future query_wiki results. "
            "The note file is preserved but marked as deprecated (OKF v0.2 lifecycle) "
            "with an optional reason. "
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
                "source_ref": {
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
            "required": ["source_ref"],
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
        name="capture_conversation",
        description=(
            "Store a raw conversation transcript into repowiki/raw/ (team-memory fusion "
            "ingest half). Accepts a 'conversation' list of turns (each with role+content) "
            "or an object with a 'turns' key. Optional 'link_to' ties the capture to a wiki "
            "object, and 'keep_raw' hints that distill_conversation should retain the file. "
            "This tool is pure persistence: no LLM is invoked, and raw/ is excluded from "
            "query_wiki. Distillation to notes is a separate async step (T2)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional active session id (resolves output_dir).",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki).",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path used to derive output_dir when output_dir is absent.",
                },
                "conversation": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "description": "Speaker role, e.g. user / assistant.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Turn text.",
                            },
                        },
                        "required": ["content"],
                    },
                    "description": "List of conversation turns. May also be passed as an object with a 'turns' key.",
                },
                "link_to": {
                    "type": "string",
                    "description": "Optional wiki object id/title this conversation relates to.",
                },
                "keep_raw": {
                    "type": "boolean",
                    "description": (
                        "Hint for distill_conversation to retain the conversation "
                        "even if it yields no knowledge (archived to conversations/; "
                        "conversations that DO produce knowledge are archived by "
                        "default). Default false."
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task id this conversation is bound to. Stored as metadata and used by distill_conversation to route task memories back to the task.",
                },
            },
            "required": ["conversation"],
        },
    ),
    handler_path="codewiki.mcp.tools.capture_conversation:handle_capture_conversation",
    mode="thread",
)

_register(
    Tool(
        name="distill_conversation",
        description=(
            "Distill a raw conversation transcript (repowiki/raw/) into draft wiki notes "
            "(team-memory fusion extract half). Stateless: the LLM is supplied by the caller. "
            "Three modes: (A) pass 'llm' (async callable, direct handler invocation only); "
            "(B) 'run_in_background=true' builds an OpenAI-compatible LLM from "
            "MAIN_MODEL/LLM_BASE_URL/LLM_API_KEY and runs async (progress in "
            "repowiki/distill-jobs.json); (C) agent-driven over MCP JSON: "
            "mode='prepare' returns pending transcripts + the distillation system prompt, "
            "the host agent extracts knowledge with its own model, then mode='submit' with "
            "distilled={conversation_id: <notes JSON>} runs the deterministic half. "
            "Produces status='draft' notes that must be promoted via confirm_note. "
            "Raw retention (L0 archive): a conversation that produced knowledge is "
            "ARCHIVED to repowiki/conversations/ after distillation and the notes' "
            "source_ref is repointed there (link-first provenance, not indexed for "
            "search); no_knowledge noise is deleted; pass drop_raw=true to delete "
            "explicitly (privacy opt-out)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional active session id (resolves output_dir).",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki).",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path used to derive output_dir when output_dir is absent.",
                },
                "raw_path": {
                    "type": "string",
                    "description": "Path to a specific raw conversation file to distill.",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Conversation id (conv-<id>) to distill a single capture.",
                },
                "task_id": {
                    "type": "string",
                    "description": (
                        "Only distill pending raw conversations bound to this task "
                        "(sessionStart catch-up path). Applies to prepare/submit/batch/Mode B. "
                        "Returns status=noop when nothing pending belongs to the task."
                    ),
                },
                "preview_chars": {
                    "type": "integer",
                    "description": (
                        "Mode prepare only: max chars of the short 'preview' per capture. "
                        "The full transcript is NOT inlined (file-side-channel); read it via "
                        "read_file(full_path)."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "prepare", "submit"],
                    "description": (
                        "auto (default): Mode A/B below. prepare: return pending captures as "
                        "full_path + metadata + short preview (no full transcript inlined, "
                        "file-side-channel) + system prompt, without any LLM. "
                        "submit: run the deterministic half on agent-produced results in 'distilled'."
                    ),
                },
                "distilled": {
                    "type": "object",
                    "description": (
                        "Mode submit only: mapping of conversation_id (e.g. 'conv-20260808T113515Z') "
                        'to the extraction JSON shaped {"notes": [{title, note_type, related_modules, '
                        "tags, content, priority?, scene?}]}. Optional per-note fields: "
                        "priority (0-100; <70 is dropped deterministically), scene (short work-context "
                        "label stored as metadata.scene), and — to resolve conflicts_pending from a "
                        "previous submit — dedup_action (store|skip|update|merge) plus target "
                        "(candidate note file for update/merge). Values may be JSON strings or objects. "
                        "For large multi-note payloads prefer distilled_file (file-side-channel) "
                        "over inlining here."
                    ),
                },
                "distilled_file": {
                    "type": "string",
                    "description": (
                        "Mode submit only, alternative to 'distilled': path to a JSON file "
                        "containing the extraction mapping. File-side-channel symmetric to "
                        "prepare's full_path — the host agent writes the large extraction JSON "
                        "with write_to_file and passes only this small path, avoiding oversized "
                        "MCP arguments. Accepted shapes: mapping {conversation_id: {notes, "
                        "memories}}, or a bare {notes, memories} object bound to the "
                        "conversation_id argument (single-target submit). Relative paths are "
                        "resolved against output_dir, then the process CWD. If both distilled "
                        "and distilled_file are given, they are merged with the inline "
                        "distilled taking precedence on key collisions."
                    ),
                },
                "drop_raw": {
                    "type": "boolean",
                    "description": (
                        "Privacy opt-out: delete the raw conversation after "
                        "distillation instead of archiving it to conversations/. "
                        "Default false (archive). Applies to mode=submit."
                    ),
                },
                "llm": {
                    "description": "Async callable llm(prompt, system) -> str. Only usable via direct handler invocation (not over MCP JSON).",
                    "type": "object",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Build the LLM from MAIN_MODEL env and run distillation in a daemon thread (Mode B).",
                },
                "note_type": {
                    "type": "string",
                    "description": "Force note_type for all produced notes (decision/lesson/pitfall/architecture/workaround).",
                },
                "related_modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Force related_modules for all produced notes.",
                },
            },
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.distill_conversation:handle_distill_conversation",
    mode="thread",
)

_register(
    Tool(
        name="consolidate_notes",
        description=(
            "Consolidate CONFIRMED (stable) notes into L2 work-method scene blocks "
            "under wiki/scenarios/ (team-memory fusion P2). Mode C protocol — the "
            "host agent does the consolidation reasoning, the tool does deterministic "
            "bookkeeping. mode='prepare': returns pending confirmed notes (not yet "
            "absorbed), the current scenarios index (file/title/summary/heat), a "
            "graded capacity warning (red=merge first / orange=update only / "
            "yellow=prefer update) and the consolidation system prompt. The agent "
            "then writes scene blocks via write_doc_file(page_type='scenario'), "
            "retires fully-absorbed source notes via reject_note, and calls "
            "mode='submit' with report.scenarios=[{file, action, source_notes, "
            "summary?, heat?}] (action: created|updated|merged|deleted). Submit "
            "validates files, stamps summary/heat, records provenance "
            "(source_notes ⇄ consolidated_into), cleans [DELETED] markers, enforces "
            "the capacity cap and resets the aggregation counter. NEVER runs "
            "automatically — only on explicit request; when triggered by an "
            "aggregation_hint reminder, ask the user first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional active session id (resolves output_dir).",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki).",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path used to derive output_dir when output_dir is absent.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["prepare", "submit"],
                    "description": (
                        "prepare: return pending notes + scenarios index + capacity "
                        "warning + system prompt. submit: record the consolidation "
                        "report produced by the agent."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "prepare only: max pending notes to return (default 50).",
                },
                "report": {
                    "type": "object",
                    "description": (
                        "submit only: {scenarios: [{file, action, source_notes, "
                        "summary?, heat?}]} — file relative to output_dir "
                        "(wiki/scenarios/...md), action in created|updated|merged|"
                        "deleted, source_notes the absorbed note files. deleted "
                        "requires the file body to be exactly [DELETED]."
                    ),
                },
            },
            "required": ["mode"],
        },
    ),
    handler_path="codewiki.mcp.tools.note_consolidation:handle_consolidate_notes",
    mode="thread",
)

_register(
    Tool(
        name="refresh_doctrine",
        description=(
            "Regenerate the L3 Project Operating Doctrine at wiki/doctrine.md "
            "(team-memory fusion P3) — one highly-refined (<=1200 chars) "
            "document of cross-scenario SOPs, principles, decision logic, "
            "boundaries, anti-patterns and agent rules. Mode C protocol: "
            "mode='prepare' returns the current doctrine, changed scene blocks "
            "(updated since last refresh), statistics and the doctrine system "
            "prompt (six dimensions / five filters / five incremental "
            "strategies / hard prohibitions). The agent compresses the changed "
            "scenes, then mode='submit' with content=<final doctrine Markdown>: "
            "the tool rejects over-cap content, backs up the previous version "
            "(rolling keep-3), writes OKF frontmatter with source_scenarios "
            "provenance, resets the doctrine counter and rebuilds the index. "
            "The new doctrine lands as status=draft (promote via confirm_note). "
            "Once present, query_wiki(mode='overview') injects it automatically. "
            "NEVER runs automatically; when prompted by an aggregation_hint or "
            "doctrine_hint reminder, ask the user first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional active session id (resolves output_dir).",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki).",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path used to derive output_dir when output_dir is absent.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["prepare", "submit"],
                    "description": (
                        "prepare: return current doctrine + changed scenes + stats "
                        "+ system prompt. submit: write the final doctrine."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "submit only: the FINAL doctrine Markdown. Must be within "
                        "the char cap (default 1200; schema.yaml "
                        "conventions.aggregation.doctrine_max_chars overrides)."
                    ),
                },
                "by": {
                    "type": "string",
                    "description": "Optional actor id for the OKF generated.by field (default codewiki/<version>).",
                },
            },
            "required": ["mode"],
        },
    ),
    handler_path="codewiki.mcp.tools.doctrine:handle_refresh_doctrine",
    mode="thread",
)

_register(
    Tool(
        name="batch_ingest",
        description=(
            "Bulk-import multiple notes and/or source documents in one call. "
            "Accepts an inline items list or an items_file path (for large batches). "
            "Each item must have a 'kind' field: 'note' or 'source' ('type' is accepted "
            "as an alias for 'kind'), plus the fields "
            "for that tool (e.g., kind='note' needs title+content, kind='source' needs source_ref). "
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
                        "orphan_page",
                        "no_outlinks",
                        "missing_aliases",
                        "stale_source",
                        "broken_link",
                        "outdated_content",
                        "missing_section",
                        "low_coverage",
                        "custom",
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
            "Incremental by default (per-repo three-tier dispatch on the persisted "
            "anchor, metadata.json generation_info.commit_id): unchanged repos are "
            "skipped (the cross-service matcher reuses their cached routes), changed "
            "repos are re-analyzed and return changes/affected_modules to scope "
            "incremental doc rewrites (incremental-update prompt), repos without a "
            "prior analysis run full. Per-repo entries carry a mode field "
            "(skipped/incremental/full/deferred). "
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
                    "description": "Output directory for workspace overview (default: <workspace>/repowiki)",
                },
                "exclude_dirs": {
                    "type": "string",
                    "description": "Comma-separated directory names to skip (default: node_modules,.venv,__pycache__)",
                },
                "generate_repo_wikis": {
                    "type": "boolean",
                    "description": (
                        "Centralized layout only: also run the heavy per-repo analysis to "
                        "populate each repo's knowledge partition (default: false — only the "
                        "workspace topology/overview is produced). Ignored for colocated "
                        "workspaces, which always analyze every repo."
                    ),
                },
            },
            "required": ["workspace_path"],
        },
    ),
    handler_path="codewiki.mcp.tools.workspace_analyzer:handle_analyze_workspace",
    mode="thread",  # was "main_thread" — same ping-blocking issue as analyze_repo
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
            "Set leaf_only=true to return only leaf components (no outgoing dependencies). "
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
                "leaf_only": {
                    "type": "boolean",
                    "description": "If true, only return leaf components (components with no outgoing dependencies in the call graph).",
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
            "(e.g., file_path='repowiki/wiki/modules/auth.md'), "
            "2) Browse source files for extra context during documentation, "
            "3) Read imported source documents after ingest_source "
            "(e.g., file_path='raw/sources/rfc793.txt'). "
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
                "file_path": {
                    "type": "string",
                    "description": "Relative path from repo root (e.g. 'repowiki/overview.md' or 'backend/src/...')",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Optional. Maximum number of lines to return from the file. If the file has more lines, only the first max_lines are returned with truncated=true and total_lines showing the original count. Useful for previewing large files without consuming excessive context.",
                },
            },
            "required": ["repo_path", "file_path"],
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
            "Pass workspace_path to specify the workspace root (multi-repo) or repo root "
            "(monorepo single-repo). "
            "Matches HTTP routes (server declarations vs client calls) and MQ "
            "producer/consumer (Kafka/RabbitMQ/RocketMQ/Celery) across repos in a "
            "multi-repo workspace, or across sub-services within a monorepo. "
            "Languages covered: Python (FastAPI/Flask/Django + "
            "requests/httpx/aiohttp), Java (Spring MVC/JAX-RS + Feign/RestTemplate/"
            "WebClient), JS/TS (Express/NestJS + axios/fetch/got), Go (Gin/Chi/Echo/"
            "net/http). Path parameters (:id/{id}/<id>) are canonicalized to {} for "
            "framework-agnostic matching. "
            "Supports filter_type: 'all' (default, every link), 'by_service' (one repo's "
            "inbound/outbound links), 'by_method' (HTTP method), 'by_path' (URL path "
            "prefix match — pass a full path prefix like '/api/v1/chat', not a keyword), "
            "'trace' (transitive call chain from a root service). "
            "Reads results persisted under <workspace_path>/repowiki/.meta/ "
            "(analyze_workspace multi-repo or analyze_repo monorepo). "
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
                    "description": "Value for the filter: service name substring, case-insensitive (for by_service — e.g. 'order' matches 'order-service'), HTTP method (for by_method), path prefix case-insensitive (for by_path — prefix match, not substring), or root service (for trace). Note: for by_service, 'repo_name' is accepted as an alias for backward compatibility.",
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
    takes_store=True,
)


_register(
    Tool(
        name="init_wiki",
        description=(
            "Initialize a Wiki workspace for a project (zero-config bootstrap). "
            "Creates the output directory structure (wiki/modules, wiki/entities, "
            "wiki/concepts, wiki/sources, wiki/comparisons, wiki/queries, notes/), "
            "copies the annotated schema.yaml template (preserving comments), "
            "the ontology.yaml template and the review_checklist.yaml override "
            "template (both skipped when already present), and "
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

_register(
    Tool(
        name="init_workspace",
        description=(
            "Initialize (or re-sync) a multi-repo harness workspace in the current "
            "working directory: the directory becomes the product-level workbench "
            "hosting business repos as independent git clones in subdirectories "
            "(excluded via .gitignore, not submodules). Generates bootstrap.sh / "
            "bootstrap.ps1 clone scripts with a registration table, a .gitignore that "
            "keeps business repos out of the harness git, a repo-map.md navigation "
            "skeleton, workspace conventions (retrieval routing per layout, commit "
            "discipline) as a marked section in AGENTS.md, and the standard "
            "product-level repowiki. FIRST init requires an explicit knowledge-layout "
            "decision: ask the user whether knowledge should be colocated (each "
            "business repo keeps its own repowiki, two-hop retrieval) or centralized "
            "(one workspace repowiki, one-hop retrieval), then pass layout=<choice>; "
            "without layout the tool writes nothing and returns "
            "status='needs_layout_decision'. The chosen layout is persisted to "
            "repowiki/.meta/workspace.json for BOTH layouts. Re-runs are zero-config "
            "and idempotent with two modes: when every init trace is present "
            "(bootstrap scripts with a parseable registration table, .gitignore, "
            "repowiki skeleton) the re-run is clone-only — it adopts the workspace, "
            "fetches just the registered business repos not yet cloned, backfills a "
            "missing layout config, and touches nothing else (in that state running "
            "the workspace's bootstrap script directly achieves the same clone sync; "
            "the tool mode is a safety net); otherwise it runs the full sync flow: "
            "adopts the persisted knowledge layout, creates missing artifacts, "
            "force-refreshes the conventions block, and clones uncloned repos (a "
            "failed clone only warns; ./bootstrap.sh retries later). Register new "
            "business repos with add_workspace_repo(url); follow up with init_wiki / "
            "analyze_repo per repo, then analyze_workspace for cross-repo analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Product-level repowiki directory (default: <workspace>/repowiki).",
                },
                "layout": {
                    "type": "string",
                    "enum": list(VALID_LAYOUTS),
                    "description": (
                        "Knowledge layout. Required on FIRST init — ask the user to "
                        "choose before calling: colocated (each business repo keeps "
                        "its own repowiki, two-hop retrieval) or centralized (all "
                        "knowledge in the workspace repowiki, one-hop retrieval). "
                        "Omit on re-runs: the persisted layout "
                        "(repowiki/.meta/workspace.json) is adopted automatically; a "
                        "conflicting value is an error."
                    ),
                },
            },
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.workspace_bootstrap:handle_init_workspace",
    mode="thread",
    takes_store=False,
)

_register(
    Tool(
        name="add_workspace_repo",
        description=(
            "Register a business repo into an initialized harness workspace. The "
            "directory name is derived from the repository URL (last path segment, "
            ".git stripped), so only the URL is required. Transactionally updates "
            "four files: the bootstrap.sh and bootstrap.ps1 registration tables, "
            ".gitignore (adds /<name>/ so the harness git never tracks the clone) and "
            "repowiki/wiki/repo-map.md (nav-table row + detail section). All preflight "
            "checks run before any write — a conflict (same directory name, different "
            "URL) or a broken script table aborts with no partial changes. "
            "Re-registering the same name+URL is a no-op, so the call is safe to "
            "retry. By default the repo is git-cloned afterwards; a clone failure "
            "never rolls back the registration. Works on hand-built workspaces too, "
            "as long as the scripts keep the `declare -A repos=(` / "
            "`$repos = [ordered]@{` skeleton lines."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Workspace root (default: current working directory).",
                },
                "url": {
                    "type": "string",
                    "description": "Git clone URL of the business repo; the subdirectory name is derived from the repository name.",
                },
                "clone": {
                    "type": "boolean",
                    "description": "Clone immediately after registration (default: true).",
                },
                "clone_timeout": {
                    "type": "integer",
                    "description": "Seconds allowed for the git clone (default: 600).",
                },
            },
            "required": ["url"],
        },
    ),
    handler_path="codewiki.mcp.tools.workspace_bootstrap:handle_add_workspace_repo",
    mode="thread",
    takes_store=False,
)

_register(
    Tool(
        name="remove_workspace_repo",
        description=(
            "Deregister a business repo from an initialized harness workspace by its "
            "subdirectory name. Transactionally removes the entry from the "
            "bootstrap.sh and bootstrap.ps1 registration tables, the /<name>/ line "
            "from .gitignore and the nav row + section from repo-map.md, scrubs the "
            "repo from analyze_workspace artifacts (workspace_routes.json / "
            "cross_service_links.json / infra_services.json under repowiki/.meta/ "
            "and the generated overview.md), then deletes the local clone directory "
            "(irreversible). Removing a name that is not registered is a safe no-op "
            "error. Never touches AGENTS.md or the other registered repos."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Workspace root (default: current working directory).",
                },
                "name": {
                    "type": "string",
                    "description": "Registered subdirectory name of the business repo to remove.",
                },
            },
            "required": ["name"],
        },
    ),
    handler_path="codewiki.mcp.tools.workspace_bootstrap:handle_remove_workspace_repo",
    mode="thread",
    takes_store=False,
)

_register(
    Tool(
        name="wiki_stats",
        description=(
            "Return per-document retrieval statistics (hit count ranking). "
            "Shows which wiki pages and notes are most frequently returned by "
            "query_wiki, and which are never retrieved. Use this to identify "
            "low-value or stale documentation that no query ever surfaces. "
            "Stats are automatically recorded every time query_wiki runs; "
            "this tool reads them back. "
            "The response also carries a ``freshness`` block (due/fresh counts of "
            "stable/confirmed notes plus up to 20 due note paths), computed with the "
            "same type-aware judgment as the lint stale_notes check. "
            "Parameters: sort_by (hit_count|last_hit|first_hit|file_path), "
            "order (desc|asc), limit (1-200), include_zero_hit (cross-reference "
            "with the file system to find documents never returned), "
            "min_hits (filter to files with at least N hits)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Repository root path. If output_dir is not given, stats are read from <repo_path>/repowiki/.meta/retrieval_stats.db.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki). Use this if the wiki was generated to a custom location.",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["hit_count", "last_hit", "first_hit", "file_path"],
                    "description": "Sort column. Default: hit_count.",
                    "default": "hit_count",
                },
                "order": {
                    "type": "string",
                    "enum": ["desc", "asc"],
                    "description": "Sort direction. Default: desc.",
                    "default": "desc",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return (1-200). Default: 50.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
                "include_zero_hit": {
                    "type": "boolean",
                    "description": "If true, also list wiki/notes files that exist on disk but were never returned by any query_wiki call. Useful for finding dead documentation.",
                    "default": False,
                },
                "min_hits": {
                    "type": "integer",
                    "description": "Only include files with at least this many hits. Default: 0.",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "required": [],
        },
    ),
    handler_path="codewiki.mcp.tools.knowledge_loop:handle_wiki_stats",
    mode="thread",
    takes_store=True,
)


# -------------------------------------------------------------------
#  Task memory layer (task_manager.py)
# -------------------------------------------------------------------

_register(
    Tool(
        name="create_task",
        description=(
            "Create a new task in the task memory layer (repowiki/tasks/). A task "
            "is a long-running unit of work that accumulates distilled memories across "
            "sessions. The task id is derived from the title and is immutable; duplicate "
            "titles are rejected and there is no rename (delete then recreate instead)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title (unique; also determines the task id).",
                },
                "description": {
                    "type": "string",
                    "description": "Optional task description (markdown).",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional active session id (resolves output_dir).",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Wiki output directory (default: <repo_path>/repowiki).",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path used to derive output_dir when output_dir is absent.",
                },
            },
            "required": ["title"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_create_task",
    mode="thread",
)

_register(
    Tool(
        name="list_tasks",
        description=(
            "List tasks from the task memory layer, optionally filtered by status "
            "('active' or 'completed'). New sessions should only surface active tasks. "
            "The .index.json is a rebuildable cache over the tasks/ directory: entries "
            "lost to a git merge (or a corrupt index) are silently recovered from "
            "tasks/*/task.md on the next read."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional status filter: 'active' or 'completed'.",
                },
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_list_tasks",
    mode="thread",
)

_register(
    Tool(
        name="get_task",
        description=(
            "Return a single task's details (description) plus its most recent "
            "memories (default 5 entries). memories_total / memories_truncated "
            "indicate whether older entries exist — pass a larger max_memories "
            "to page back through them. For full-history context restoration "
            "use get_task_context."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "max_memories": {
                    "type": "integer",
                    "description": (
                        "Max most-recent memory entries to return (default 5). "
                        "Non-positive or invalid values mean no limit."
                    ),
                },
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_get_task",
    mode="thread",
)

_register(
    Tool(
        name="complete_task",
        description=(
            "Mark an active task as completed. Completed tasks are hidden from new "
            "sessions' task pickers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_complete_task",
    mode="thread",
)

_register(
    Tool(
        name="delete_task",
        description=(
            "Delete a task, its directory (task.md + memories.md), and any session "
            "bindings pointing at it. Notes stamped with the task_id are NOT deleted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_delete_task",
    mode="thread",
)

_register(
    Tool(
        name="set_session_task",
        description=(
            "Bind a source (IDE) session id to a task id. The binding is consumed by "
            "capture_conversation (stamps task_id into raw frontmatter). Binding files "
            "live under repowiki/.meta/task_bindings/."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_session_id": {
                    "type": "string",
                    "description": "The IDE/source session id to bind.",
                },
                "task_id": {"type": "string", "description": "Task id to bind to."},
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["source_session_id", "task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_set_session_task",
    mode="thread",
)

_register(
    Tool(
        name="add_task_memory",
        description=(
            "Append a memory entry to the CURRENT USER's per-user memory file "
            "memories/<user_id>.md (atomic, append-only; each user writes only "
            "their own file — git-level conflict isolation). Task memories are "
            "task-scoped progress knowledge, distinct from wiki notes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "content": {"type": "string", "description": "Memory text (markdown)."},
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id", "content"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_add_task_memory",
    mode="thread",
)

_register(
    Tool(
        name="get_task_context",
        description=(
            "Aggregate a task's full context: task.md description, layered "
            "memories, and related notes. Memories are LAYERED (multi-user split): "
            "hot layer = the current user's per-user file (+ legacy memories.md) "
            "with the most recent max_memories entries in full (default 20; "
            "memories_total / memories_truncated indicate older entries); warm "
            "layer = each other teammate's summary section + their 2 most recent "
            "entries, degraded to one-line hints past the budget. Also returns "
            "related notes (notes whose frontmatter carries the matching task_id, "
            "each with its status: draft = unconfirmed, stable = confirmed) and "
            "pending_raw_count / pending_raws — the number of un-distilled raw "
            "captures bound to this task. If pending_raw_count > 0, run "
            "distill_conversation(mode='prepare', task_id=<this task>) to catch up "
            "BEFORE answering the user's question. compaction_due=true means the "
            "HOT layer exceeded the compaction thresholds (40 entries / 24KB) "
            "with entries beyond the keep window — run compact_task_memories to "
            "compress old entries into a summary. Use this at session start to "
            "resume a task."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "max_memories": {
                    "type": "integer",
                    "description": (
                        "Max most-recent memory entries to return (default 20). "
                        "Non-positive or invalid values mean no limit."
                    ),
                },
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_get_task_context",
    mode="thread",
)

_register(
    Tool(
        name="compact_task_memories",
        description=(
            "Compress the CALLER's old memories into a '## 早期记忆（摘要）' "
            "summary section, keeping the most recent 20 entries in full. "
            "File-domain and author-exclusive: the compaction unit is the current "
            "user's memories/<user_id>.md PLUS the legacy memories.md (which "
            "converges into the user's file and is then removed); other users' "
            "files are never touched. Two-phase stateless design (no LLM inside): "
            "mode='prepare' (default) returns the entries to compress + summary "
            "instructions — the CALLER writes the summary; mode='submit' with that "
            "summary performs the rewrite. Compacted entries' originals are "
            "appended verbatim to memories-archive/<owner>.md per origin owner "
            "(append-only, never auto-loaded). Direct write, no confirm gate — the "
            "operation is reversible via the archive. No-op "
            "(compaction_needed=false) when below the thresholds (40 entries "
            "/ 24KB) or when nothing lies beyond the keep window. Trigger signal: "
            "get_task_context returns compaction_due=true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id."},
                "mode": {
                    "type": "string",
                    "enum": ["prepare", "submit"],
                    "description": (
                        "'prepare' (default): return entries to compress + "
                        "instructions. 'submit': apply the caller-authored summary."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "The caller-written summary (required for mode='submit', "
                        "max 2048 chars). Covers key facts, settled decisions, open "
                        "items, and context still relevant to future work."
                    ),
                },
                "session_id": {"type": "string", "description": "Optional active session id."},
                "output_dir": {"type": "string", "description": "Wiki output directory."},
                "repo_path": {"type": "string", "description": "Repository path."},
            },
            "required": ["task_id"],
        },
    ),
    handler_path="codewiki.mcp.tools.task_manager:handle_compact_task_memories",
    mode="thread",
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
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Invalid mode '{tool_def.mode}' for tool '{name}'"}),
                )
            ]

        # --- CBM enrichment (best-effort, async) ---
        result = await _try_cbm_enrichment(name, arguments, result)

        # Wrap result in TextContent
        if isinstance(result, list) and result and isinstance(result[0], TextContent):
            # Handler already returned list[TextContent] (e.g. legacy tools)
            return result
        if isinstance(result, TextContent):
            return [result]
        return [
            TextContent(type="text", text=result if isinstance(result, str) else json.dumps(result))
        ]

    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
