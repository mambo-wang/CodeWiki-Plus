"""MCP tool: analyze_repo — parse a repository and build the dependency graph.

This is the entry-point tool for the IDE-driven wiki generation pipeline.
It runs CodeWiki's Tree-sitter-based dependency analyzer (no LLM needed),
caches the results in a new session, and returns a component index the IDE
agent can use for clustering and documentation.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


def _build_component_index(components: Dict[str, Any], max_items: int = 500) -> Tuple[list, bool]:
    """Build a lightweight component index for the MCP response.

    Returns (index_list, truncated) where *truncated* is True when the
    index was capped at *max_items*.
    """
    index: list[dict] = []
    for comp_id, node in list(components.items())[:max_items]:
        index.append({
            "id": comp_id,
            "type": getattr(node, "component_type", "unknown"),
            "file": getattr(node, "relative_path", ""),
            "depends_on": list(getattr(node, "depends_on", []))[:20],
        })
    return index, len(components) > max_items


def handle_analyze_repo(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Run the dependency analysis and return the session + component index."""
    repo_path = Path(arguments["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        return json.dumps({"error": f"Repository not found: {repo_path}"})

    output_dir = Path(arguments.get("output_dir", str(repo_path / "docs"))).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build a minimal Config for the dependency analyzer (no LLM fields used)
    from codewiki.src.config import Config
    config = Config(
        repo_path=str(repo_path),
        output_dir=str(output_dir / "temp"),
        dependency_graph_dir=str(output_dir / "temp" / "dependency_graphs"),
        docs_dir=str(output_dir),
        max_depth=2,
        llm_base_url="not-needed",
        llm_api_key="not-needed",
        main_model="unused",
        cluster_model="unused",
    )

    # Apply optional include/exclude patterns
    include = arguments.get("include_patterns")
    exclude = arguments.get("exclude_patterns")
    if include or exclude:
        agent_instructions: Dict[str, Any] = {}
        if include:
            agent_instructions["include_patterns"] = [p.strip() for p in include.split(",")]
        if exclude:
            agent_instructions["exclude_patterns"] = [p.strip() for p in exclude.split(",")]
        config.agent_instructions = agent_instructions

    from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
    builder = DependencyGraphBuilder(config)
    components, leaf_nodes = builder.build_dependency_graph()

    session = store.create(
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        components=components,
        leaf_nodes=leaf_nodes,
    )

    index, truncated = _build_component_index(components)

    # Language stats
    languages: Dict[str, int] = {}
    for node in components.values():
        lang = getattr(node, "language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1

    result = {
        "session_id": session.session_id,
        "repo_name": repo_path.name,
        "repo_path": str(repo_path),
        "output_dir": str(output_dir),
        "languages": languages,
        "total_components": len(components),
        "total_leaf_nodes": len(leaf_nodes),
        "leaf_nodes": leaf_nodes[:100],
        "component_index": index,
        "component_index_truncated": truncated,
        "hint": (
            "Use read_code_components(session_id, component_ids) to read source code. "
            "Use save_module_tree(session_id, module_tree) after clustering. "
            "Call get_prompt('cluster') for clustering rules."
        ),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)
