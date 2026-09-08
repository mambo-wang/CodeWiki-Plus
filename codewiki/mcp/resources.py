"""MCP Resources — read-only context for agents.

This module registers resource and resource-template handlers on the MCP
server instance, providing agents with read-only access to prompt catalogs,
capability overviews, page-type documentation, and per-wiki metadata
(catalog, module tree, index status).
"""

import json
import logging
from pathlib import Path
from typing import Any

from codewiki.mcp import i18n as _i18n

logger = logging.getLogger(__name__)


# ===================================================================
#  Helper functions
# ===================================================================


def _read_wiki_resource(uri_str: str) -> str:
    """Handle parameterized wiki resources like codewiki://wiki/{output_dir}/catalog."""
    from urllib.parse import unquote

    # Parse: codewiki://wiki/<encoded_output_dir>/<resource_type>
    path_part = uri_str[len("codewiki://wiki/") :]
    # The last segment is the resource type
    last_slash = path_part.rfind("/")
    if last_slash == -1:
        return json.dumps(
            {
                "error": "Invalid URI format. Expected: codewiki://wiki/{output_dir}/{catalog|module-tree|index-status}"
            }
        )

    output_dir_encoded = path_part[:last_slash]
    resource_type = path_part[last_slash + 1 :]
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
        return json.dumps(
            {
                "error": f"Unknown resource type: {resource_type}. Available: catalog, module-tree, index-status"
            }
        )


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

    return json.dumps(
        {"output_dir": str(output_path), "page_count": len(pages), "pages": pages},
        ensure_ascii=False,
        indent=2,
    )


def _wiki_module_tree(output_path: Path) -> str:
    """Read the module tree from .meta/module_tree.json."""
    from codewiki.src.config import meta_resolve

    tree_path = Path(meta_resolve(output_path, "module_tree.json"))
    if not tree_path.exists():
        return json.dumps(
            {"error": "Module tree not found. Run analyze_repo + save_module_tree first."}
        )
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))

        # Summarize
        def _summarize(t, depth=0):
            modules = []
            for name, info in t.items():
                modules.append(
                    {
                        "name": name,
                        "components": len(info.get("components", [])),
                        "children": len(info.get("children", {}))
                        if isinstance(info.get("children"), dict)
                        else 0,
                        "is_leaf": not bool(info.get("children")),
                    }
                )
                if isinstance(info.get("children"), dict) and info["children"]:
                    modules.extend(_summarize(info["children"], depth + 1))
            return modules

        summary = _summarize(tree)
        return json.dumps(
            {"output_dir": str(output_path), "total_modules": len(tree), "modules": summary},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": f"Failed to read module tree: {e}"})


def _wiki_index_status(output_path: Path) -> str:
    """Check the search index and link graph status."""
    from codewiki.mcp.tools.wiki_search import _resolve_db_path
    from codewiki.mcp.tools.index_freshness import has_search_index

    index_path = _resolve_db_path(output_path)
    result = {"output_dir": str(output_path), "index_exists": has_search_index(output_path)}

    if index_path is not None and index_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(index_path), timeout=30.0)  # Team-layout Phase 2
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
        result["hint"] = (
            "Search index not built yet. Call close_session or build_search_index to create it."
        )

    return json.dumps(result, ensure_ascii=False, indent=2)


# ===================================================================
#  Registration
# ===================================================================


# ---------------------------------------------------------------------------
# Stable identifiers for the capability/page-type resources.  Only the display
# strings are localized; these identifiers stay the same in every language so
# clients can key off them.
# ---------------------------------------------------------------------------

_TOOL_CATEGORIES: dict[str, list[str]] = {
    "code_analysis": [
        "analyze_repo",
        "analyze_workspace",
        "list_components",
        "list_dependencies",
        "analyze_impact",
        "read_code_components",
        "view_repo_file",
    ],
    "workspace_management": [
        "init_workspace",
        "add_workspace_repo",
        "remove_workspace_repo",
    ],
    "cross_service": ["query_cross_service"],
    "doc_generation": [
        "write_doc_file",
        "edit_doc_file",
        "save_module_tree",
        "get_processing_order",
        "get_prompt",
        "get_module_tree",
        "generate_docs (legacy)",
    ],
    "knowledge_base": [
        "query_wiki",
        "ingest_note",
        "confirm_note",
        "reject_note",
        "ingest_source",
        "retract_source",
        "batch_ingest",
        "skill_creator",
    ],
    "quality": ["lint_wiki", "flag_issue"],
    "session": ["close_session", "init_wiki"],
}

_KEY_PATTERNS = [
    "workspace_file",
    "session_lifecycle",
    "page_type_routing",
    "search_layers",
    "cross_service",
]

_PAGE_TYPE_PATHS: dict[str, str] = {
    "module": "wiki/modules/",
    "entity": "wiki/entities/",
    "concept": "wiki/concepts/",
    "source": "wiki/sources/",
    "comparison": "wiki/comparisons/",
    "query": "wiki/queries/",
}

_WIKILINK_RULES = ["syntax", "graph_build", "multi_hop", "aliases"]


def register(server):
    """Register resource and resource-template handlers on the MCP server."""
    @server.list_resources()
    async def list_resources() -> list:
        """List available static resources."""
        from mcp.types import Resource

        def _res(uri: str, key: str) -> Resource:
            return Resource(
                uri=uri,
                name=_i18n.t(f"resources.static.{key}.name"),
                title=_i18n.t(f"resources.static.{key}.title"),
                description=_i18n.t(f"resources.static.{key}.description"),
                mimeType="application/json",
            )

        return [
            _res("codewiki://prompts/catalog", "prompts_catalog"),
            _res("codewiki://capabilities", "capabilities"),
            _res("codewiki://page-types", "page_types"),
        ]

    @server.list_resource_templates()
    async def list_resource_templates() -> list:
        """List available resource templates (parameterized URIs)."""
        from mcp.types import ResourceTemplate

        def _tmpl(uri_template: str, key: str) -> ResourceTemplate:
            return ResourceTemplate(
                uriTemplate=uri_template,
                name=_i18n.t(f"resources.template.{key}.name"),
                title=_i18n.t(f"resources.template.{key}.title"),
                description=_i18n.t(f"resources.template.{key}.description"),
                mimeType="application/json",
            )

        return [
            _tmpl("codewiki://wiki/{output_dir}/catalog", "catalog"),
            _tmpl("codewiki://wiki/{output_dir}/module-tree", "module_tree"),
            _tmpl("codewiki://wiki/{output_dir}/index-status", "index_status"),
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> str:
        """Read a resource by URI."""
        uri_str = str(uri)

        if uri_str == "codewiki://prompts/catalog":
            # Derived from the prompt registry (single source of truth).  The
            # previous hand-maintained copy had drifted to 15 of 22 prompts.
            from codewiki.mcp.prompts import prompt_catalog

            return json.dumps(
                {
                    "prompts": prompt_catalog(),
                    "usage": _i18n.t("resources.catalog.usage"),
                },
                ensure_ascii=False,
                indent=2,
            )

        elif uri_str == "codewiki://capabilities":
            from codewiki import __version__
            from codewiki.mcp.registry import get_all_tools

            return json.dumps(
                {
                    # Derived, not hard-coded: the literal version and tool
                    # count used to go stale (v5.5.0 / 49).
                    "server": "CodeWiki-CN MCP Server v" + __version__,
                    "tool_count": len(get_all_tools()),
                    "tool_categories": {
                        cat: {
                            "label": _i18n.t("resources.capabilities.category." + cat),
                            "tools": tools,
                        }
                        for cat, tools in _TOOL_CATEGORIES.items()
                    },
                    "key_patterns": {
                        key: _i18n.t("resources.capabilities.pattern." + key)
                        for key in _KEY_PATTERNS
                    },
                },
                ensure_ascii=False,
                indent=2,
            )

        elif uri_str == "codewiki://page-types":
            return json.dumps(
                {
                    "page_types": {
                        page_type: {
                            "path": path,
                            "description": _i18n.t(
                                "resources.page_types." + page_type + ".description"
                            ),
                            # Section lists are stored pipe-separated so the
                            # catalog stays a flat string map.
                            "typical_sections": _i18n.t(
                                "resources.page_types." + page_type + ".sections"
                            ).split("|"),
                        }
                        for page_type, path in _PAGE_TYPE_PATHS.items()
                    },
                    "wikilink_rules": {
                        rule: _i18n.t("resources.wikilink." + rule)
                        for rule in _WIKILINK_RULES
                    },
                },
                ensure_ascii=False,
                indent=2,
            )

        # Resource templates: codewiki://wiki/{output_dir}/...
        elif uri_str.startswith("codewiki://wiki/"):
            return _read_wiki_resource(uri_str)

        return json.dumps({"error": f"Unknown resource: {uri_str}"})
