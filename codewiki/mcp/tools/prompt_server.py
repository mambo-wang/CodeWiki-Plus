"""MCP tool: get_prompt — serve CodeWiki's prompt templates to the IDE agent.

CodeWiki ships with carefully designed prompt templates for each stage of
the wiki generation pipeline.  This tool lets the IDE agent retrieve them
(with optional variable substitution) so it can follow the same proven
methodology without needing its own copy of the prompts.
"""

from __future__ import annotations

import json, logging
from pathlib import Path
from typing import Any, Dict, Optional

from codewiki.mcp.session import SessionStore, SessionState
from codewiki.mcp.tools.workspace_result import write_result, _FILE_THRESHOLD

logger = logging.getLogger(__name__)
from codewiki.src.be.prompt_template import (
    USER_PROMPT,
    REPO_OVERVIEW_PROMPT,
    MODULE_OVERVIEW_PROMPT,
    format_system_prompt,
    format_leaf_system_prompt,
    format_cluster_prompt,
    format_user_prompt,
)


def _build_schema_constraints(session: Optional[SessionState]) -> str:
    """Read schema.yaml from session output_dir and build constraint text for prompts.

    Extracts required_sections, documentation_dimensions, and line limits
    from schema.yaml to inject into documentation generation prompts.
    Returns empty string if schema is unavailable or unreadable.
    """
    if not session or not session.output_dir:
        return ""
    schema_path = Path(session.output_dir) / "schema.yaml"
    if not schema_path.exists():
        return ""
    try:
        import yaml
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(schema, dict):
        return ""

    parts = []

    # Required sections
    required = schema.get("required_sections", [])
    if required:
        lines = []
        for section in required:
            if isinstance(section, dict):
                title = section.get("title", "")
                mermaid = section.get("mermaid_diagram", False)
                lines.append(f"  - {title}" + (" (must include Mermaid diagram)" if mermaid else ""))
            elif isinstance(section, str):
                lines.append(f"  - {section}")
        if lines:
            parts.append("Required sections in every module doc:\n" + "\n".join(lines))

    # Documentation dimensions
    dims = schema.get("documentation_dimensions", [])
    if dims:
        dim_str = ", ".join(str(d).replace("_", " ") for d in dims)
        parts.append(f"Cover these documentation dimensions: {dim_str}")

    # Line constraints
    conventions = schema.get("conventions", {})
    min_lines = conventions.get("min_leaf_doc_lines")
    max_lines = conventions.get("max_overview_doc_lines")
    if min_lines or max_lines:
        c = []
        if min_lines:
            c.append(f"min {min_lines} lines for leaf module docs")
        if max_lines:
            c.append(f"max {max_lines} lines for overview docs")
        parts.append(f"Documentation length guidance: {', '.join(c)}")

    # OKF frontmatter
    if conventions.get("okf_frontmatter", False):
        parts.append(
            "OKF (Open Knowledge Format) compliance:\n"
            "Every markdown file MUST start with YAML frontmatter between `---` delimiters.\n"
            "Required field:\n"
            "  - type: one of [Module, Architecture, Index, Log] (required)\n"
            "Recommended fields:\n"
            "  - title: concise document title\n"
            "  - description: 1-2 sentence semantic summary of the module's purpose and responsibilities\n"
            "  - resource: primary source file path or directory (e.g., src/auth/)\n"
            "  - tags: list of meaningful semantic tags based on functionality (e.g., [authentication, jwt, session-management])\n"
            "Example:\n"
            "```yaml\n"
            "---\n"
            "type: Module\n"
            "title: Authentication Service\n"
            "description: Handles user authentication, JWT token generation, and session management\n"
            "resource: src/auth/\n"
            "tags: [authentication, jwt, session, security]\n"
            "---\n"
            "```"
        )

    if not parts:
        return ""
    return "\n\n".join(parts)


# Prompt catalog: maps prompt_type to (raw_template, usage_hint, variables_doc)
_PROMPT_CATALOG: Dict[str, Dict[str, str]] = {
    "cluster": {
        "description": "Prompt for grouping components into modules. The LLM receives a component list and returns a JSON module tree.",
        "usage_hint": (
            "Use this prompt to cluster components into logical modules. "
            "The response should contain <GROUPED_COMPONENTS> JSON. "
            "Pass the component list from analyze_repo's component_index."
        ),
    },
    "system_complex": {
        "description": "System prompt for documenting a complex (multi-file, parent) module. Includes sub-module delegation instructions.",
        "usage_hint": (
            "Use as the system prompt when generating docs for a parent module. "
            "The agent should create {module_name}.md with architecture overview "
            "and cross-references to sub-module docs."
        ),
    },
    "system_leaf": {
        "description": "System prompt for documenting a leaf (single-file or simple) module.",
        "usage_hint": (
            "Use as the system prompt when generating docs for a leaf module. "
            "The agent should create {module_name}.md with detailed documentation "
            "including Mermaid diagrams."
        ),
    },
    "user": {
        "description": "User prompt template that provides the module tree and core component source code.",
        "usage_hint": (
            "Use as the user/assistant prompt alongside system_leaf or system_complex. "
            "It provides the module tree context and the actual source code of core components."
        ),
    },
    "overview_module": {
        "description": "Prompt for generating a parent module overview from its children's documentation.",
        "usage_hint": (
            "Use this after all child modules are documented. "
            "Provide the module tree with children's docs embedded. "
            "The response should be wrapped in <OVERVIEW> tags."
        ),
    },
    "overview_repo": {
        "description": "Prompt for generating the final repository overview.",
        "usage_hint": (
            "Use this as the LAST step after all modules are documented. "
            "Provide the full module tree with child docs. "
            "Save the result as overview.md."
        ),
    },
    # --- LLM Wiki prompts ---
    "wiki_query": {
        "description": "Guidance for using query_wiki results as development context.",
        "usage_hint": (
            "Call this BEFORE starting a new feature to learn how to use "
            "query_wiki results effectively. Use query_wiki with a natural "
            "language query about the area you're about to work on."
        ),
    },
    "wiki_ingest": {
        "description": "Guidance for creating knowledge notes after completing a task.",
        "usage_hint": (
            "Call this AFTER finishing a feature or bug fix to learn how to "
            "distill key decisions into ingest_note calls."
        ),
    },
    "wiki_lint_report": {
        "description": "Guidance for interpreting lint_wiki results and planning fixes.",
        "usage_hint": (
            "Call this after running lint_wiki to understand the results "
            "and create a prioritized fix plan."
        ),
    },
}


def handle_get_prompt(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Return a prompt template, optionally with variables filled in.

    When variables are provided and the filled content exceeds 4KB, the
    prompt is written to a workspace file and only the file path is
    returned through MCP stdio.
    """
    prompt_type = arguments["prompt_type"]
    variables = arguments.get("variables", {})
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None

    if prompt_type not in _PROMPT_CATALOG:
        available = list(_PROMPT_CATALOG.keys())
        return json.dumps({
            "error": f"Unknown prompt_type: {prompt_type}",
            "available_types": available,
        })

    catalog_entry = _PROMPT_CATALOG[prompt_type]

    # Inject schema constraints from schema.yaml into variables for _resolve_prompt
    schema_constraints = _build_schema_constraints(session)
    variables['_has_caller_ci'] = "custom_instructions" in variables and variables["custom_instructions"]
    if schema_constraints:
        caller_ci = variables.get("custom_instructions")
        if caller_ci:
            variables["custom_instructions"] = caller_ci + "\n\n" + schema_constraints
        else:
            variables["custom_instructions"] = schema_constraints

    # Resolve the prompt content
    content = _resolve_prompt(prompt_type, variables)

    result = {
        "prompt_type": prompt_type,
        "description": catalog_entry["description"],
        "usage_hint": catalog_entry["usage_hint"],
        "content": content,
    }

    # Write to file when content is large and session is available
    if (session and getattr(session, "workspace", None)
            and len(content.encode("utf-8")) > _FILE_THRESHOLD):
        file_path = session.workspace.write_text(
            f"prompt_{prompt_type}.txt", content
        )
        return json.dumps({
            "prompt_type": prompt_type,
            "description": catalog_entry["description"],
            "usage_hint": catalog_entry["usage_hint"],
            "file": str(file_path),
            "content_length": len(content),
            "hint": "Read the file for the full prompt content.",
        }, indent=2, ensure_ascii=False)

    return json.dumps(result, indent=2, ensure_ascii=False)


def _resolve_prompt(prompt_type: str, variables: Dict[str, Any]) -> str:
    """Resolve a prompt template with optional variable substitution."""

    if prompt_type == "cluster":
        potential_core_components = variables.get("potential_core_components", "<POTENTIAL_CORE_COMPONENTS placeholder>")
        module_tree = variables.get("module_tree", {})
        module_name = variables.get("module_name", None)
        return format_cluster_prompt(
            potential_core_components=potential_core_components,
            module_tree=module_tree,
            module_name=module_name,
        )

    elif prompt_type == "system_complex":
        module_name = variables.get("module_name", "MODULE_NAME")
        custom_instructions = variables.get("custom_instructions", None)
        doc_type = variables.get("doc_type", "design")
        if not variables.get("_has_caller_ci") and doc_type:
            _doc_type_hints = {
                'api': "Focus on API documentation: endpoints, parameters, return types, and usage examples.",
                'architecture': "Focus on architecture documentation: system design, component relationships, and data flow.",
                'user-guide': "Focus on user guide documentation: how to use features, step-by-step tutorials.",
                'developer': "Focus on developer documentation: code structure, contribution guidelines, and implementation details.",
                'business': "Focus on business logic documentation: describe business workflows, processing pipelines, state transitions, and domain rules. Emphasize WHAT the system does for users and WHY, trace end-to-end business scenarios through the code, and document domain-specific terminology. De-emphasize infrastructure and deployment details.",
                'design': "Generate technical design documentation optimized for AI comprehension. For each module, describe in depth: (1) module responsibilities and boundaries, (2) detailed implementation logic and business rules, (3) data flow within and through the module, (4) interface contracts — inputs, outputs, and side effects, (5) internal layered design and component collaboration patterns, (6) relationships and dependencies with other modules, (7) constraints, assumptions, and edge cases. Use precise technical language. Include Mermaid diagrams for complex flows and interactions. Do not limit documentation length — let the content depth match the module's complexity.",
            }
            doc_type_hint = _doc_type_hints.get(doc_type.lower(), f"Focus on generating {doc_type} documentation.")
            if custom_instructions:
                custom_instructions = doc_type_hint + "\n\n" + custom_instructions
            else:
                custom_instructions = doc_type_hint
        return format_system_prompt(module_name, custom_instructions)

    elif prompt_type == "system_leaf":
        module_name = variables.get("module_name", "MODULE_NAME")
        custom_instructions = variables.get("custom_instructions", None)
        doc_type = variables.get("doc_type", "design")
        if not variables.get("_has_caller_ci") and doc_type:
            _doc_type_hints = {
                'api': "Focus on API documentation: endpoints, parameters, return types, and usage examples.",
                'architecture': "Focus on architecture documentation: system design, component relationships, and data flow.",
                'user-guide': "Focus on user guide documentation: how to use features, step-by-step tutorials.",
                'developer': "Focus on developer documentation: code structure, contribution guidelines, and implementation details.",
                'business': "Focus on business logic documentation: describe business workflows, processing pipelines, state transitions, and domain rules. Emphasize WHAT the system does for users and WHY, trace end-to-end business scenarios through the code, and document domain-specific terminology. De-emphasize infrastructure and deployment details.",
                'design': "Generate technical design documentation optimized for AI comprehension. For each module, describe in depth: (1) module responsibilities and boundaries, (2) detailed implementation logic and business rules, (3) data flow within and through the module, (4) interface contracts — inputs, outputs, and side effects, (5) internal layered design and component collaboration patterns, (6) relationships and dependencies with other modules, (7) constraints, assumptions, and edge cases. Use precise technical language. Include Mermaid diagrams for complex flows and interactions. Do not limit documentation length — let the content depth match the module's complexity.",
            }
            doc_type_hint = _doc_type_hints.get(doc_type.lower(), f"Focus on generating {doc_type} documentation.")
            if custom_instructions:
                custom_instructions = doc_type_hint + "\n\n" + custom_instructions
            else:
                custom_instructions = doc_type_hint
        return format_leaf_system_prompt(module_name, custom_instructions)

    elif prompt_type == "user":
        module_name = variables.get("module_name", "MODULE_NAME")
        module_tree = variables.get("module_tree", {})

        # Return the template with placeholders filled as possible
        return USER_PROMPT.format(
            module_name=module_name,
            module_tree=json.dumps(module_tree, indent=2) if module_tree else "<MODULE_TREE placeholder>",
            formatted_core_component_codes=variables.get(
                "formatted_core_component_codes",
                "<CORE_COMPONENT_CODES placeholder — use read_code_components to get source code>"
            ),
        )

    elif prompt_type == "overview_module":
        module_name = variables.get("module_name", "MODULE_NAME")
        repo_structure = variables.get("repo_structure", "<REPO_STRUCTURE placeholder>")
        custom_instructions = variables.get("custom_instructions", None)
        doc_type = variables.get("doc_type", "design")
        if not variables.get("_has_caller_ci") and doc_type:
            _overview_hints = {
                'architecture': "Focus on system-level architecture: show how modules relate, data flows between components, and the overall layered design. Include a high-level Mermaid architecture diagram.",
                'design': "Focus on system-level architecture: show how modules relate to each other, data flows between components, overall layered design, and key architectural decisions. Provide a high-level view that helps readers understand the system's structural blueprint. Include Mermaid diagrams for the architecture overview.",
            }
            doc_type_hint = _overview_hints.get(doc_type.lower())
            if doc_type_hint:
                if custom_instructions:
                    custom_instructions = doc_type_hint + "\n\n" + custom_instructions
                else:
                    custom_instructions = doc_type_hint
        custom_section = ""
        if custom_instructions:
            custom_section = f"\n<CUSTOM_INSTRUCTIONS>\n{custom_instructions}\n</CUSTOM_INSTRUCTIONS>"
        return MODULE_OVERVIEW_PROMPT.format(
            module_name=module_name,
            repo_structure=repo_structure if isinstance(repo_structure, str) else json.dumps(repo_structure, indent=4),
            custom_instructions=custom_section,
        )

    elif prompt_type == "overview_repo":
        repo_name = variables.get("repo_name", "REPO_NAME")
        repo_structure = variables.get("repo_structure", "<REPO_STRUCTURE placeholder>")
        custom_instructions = variables.get("custom_instructions", None)
        doc_type = variables.get("doc_type", "design")
        if not variables.get("_has_caller_ci") and doc_type:
            _overview_hints = {
                'architecture': "Focus on system-level architecture: show how modules relate, data flows between components, and the overall layered design. Include a high-level Mermaid architecture diagram.",
                'design': "Focus on system-level architecture: show how modules relate to each other, data flows between components, overall layered design, and key architectural decisions. Provide a high-level view that helps readers understand the system's structural blueprint. Include Mermaid diagrams for the architecture overview.",
            }
            doc_type_hint = _overview_hints.get(doc_type.lower())
            if doc_type_hint:
                if custom_instructions:
                    custom_instructions = doc_type_hint + "\n\n" + custom_instructions
                else:
                    custom_instructions = doc_type_hint
        custom_section = ""
        if custom_instructions:
            custom_section = f"\n<CUSTOM_INSTRUCTIONS>\n{custom_instructions}\n</CUSTOM_INSTRUCTIONS>"
        return REPO_OVERVIEW_PROMPT.format(
            repo_name=repo_name,
            repo_structure=repo_structure if isinstance(repo_structure, str) else json.dumps(repo_structure, indent=4),
            custom_instructions=custom_section,
        )

    # --- LLM Wiki static prompts ---
    elif prompt_type == "wiki_query":
        return (
            "## Wiki Query Guide\n\n"
            "1. Call `query_wiki` with a natural language query about the area you plan to work on.\n"
            "2. Review the `results` array — each result has a `source` (doc/note), `snippet`, and `relevance_score`.\n"
            "3. Use `related_components` to identify which code components are involved.\n"
            "4. Read the referenced doc/note files via `view_repo_file` for full context.\n"
            "5. If `scope` is specified, results are limited to that module's docs.\n"
            "6. The `context_package` field provides a ready-to-use summary for your planning.\n\n"
            "**Tip**: Query before coding to avoid repeating past mistakes. "
            "Use `list_dependencies` with `module_level: true` to understand the dependency graph."
        )

    elif prompt_type == "wiki_ingest":
        return (
            "## Knowledge Ingestion Guide\n\n"
            "After completing a task, distill key decisions into a note:\n\n"
            "1. **Title**: What decision was made? (e.g., 'Choose JWT over Session auth')\n"
            "2. **Content** should include:\n"
            "   - **Background**: Why was this needed?\n"
            "   - **Decision**: What was chosen and why?\n"
            "   - **Alternatives considered**: What else was evaluated?\n"
            "   - **Impact**: Which modules/components are affected?\n"
            "3. Call `ingest_note` with `note_type: 'decision'` (or 'lesson', 'architecture', 'bug_fix').\n"
            "4. If `related_modules` is omitted, the system auto-matches from content.\n"
            "5. Notes are stored in `repowiki/notes/` and searchable via `query_wiki`.\n\n"
            "**Tip**: Keep notes concise (200-500 words). Focus on the 'why', not the 'what'."
        )

    elif prompt_type == "wiki_lint_report":
        return (
            "## Lint Report Interpretation Guide\n\n"
            "After running `lint_wiki`, review the results by priority:\n\n"
            "1. **Errors** (fix first): Stale references to deleted modules, broken links.\n"
            "   - Use `edit_doc_file` with `str_replace` to update or remove references.\n"
            "2. **Warnings**: Undocumented high-impact components.\n"
            "   - Consider adding these to an existing module or creating a new doc.\n"
            "3. **Info**: Circular dependencies, coverage statistics.\n"
            "   - Cycles may be intentional; coverage below 50% indicates gaps.\n\n"
            "**Workflow**: Run `lint_wiki` after each documentation update cycle. "
            "Fix errors before closing the session. Use `get_prompt('wiki_lint_report')` "
            "to share this guide with team members."
        )

    return f"Unknown prompt type: {prompt_type}"
