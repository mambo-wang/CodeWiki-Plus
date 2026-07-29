"""MCP tool: close_session — close and clean up an analysis session.

On close the server automatically:
1. Rebuilds wiki index.md and log.md
2. Builds the BM25 search index + wikilink graph (enables query_wiki)
3. Injects wiki usage instructions into the target project's AGENTS.md
4. Cleans up workspace files on disk
5. Writes generation metadata (git commit baseline) for incremental updates
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.types import Tool

if TYPE_CHECKING:
    from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Tool schema
# ------------------------------------------------------------------

TOOLS = [
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
]


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _resolve_path(raw: str) -> str:
    """Resolve a path: if relative, join with cwd; always return absolute."""
    p = raw.strip()
    if not p or p in (".", "./"):
        return os.getcwd()
    if os.path.isabs(p):
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(os.getcwd(), p))


def _write_generation_metadata_from_disk(output_dir: str, repo_path: str) -> None:
    """Write ``metadata.json`` with git commit baseline for incremental updates."""
    _write_metadata_json(output_dir, repo_path, None)


def _write_metadata_json(output_dir: str, repo_path: str, commit_id: str | None) -> None:
    """Core metadata writing shared by both paths.

    Records the current git commit and timestamp so that
    ``_detect_changes`` can diff against this baseline on the next
    ``analyze_repo`` call, enabling incremental updates.
    """
    try:
        # Baseline on the commit analyze_repo saw, NOT the current HEAD
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


# ------------------------------------------------------------------
# Handler
# ------------------------------------------------------------------

def handle_close_session(arguments: dict, store: "SessionStore") -> str:
    """Close and clean up an analysis session, returning a JSON status string."""
    repo_path = arguments.get("repo_path")
    if not repo_path:
        return json.dumps({"error": "repo_path is required."})

    rp = _resolve_path(repo_path)

    # Try to find active session for caching (optional)
    session = store.find_or_restore(rp)

    # Resolve output_dir: explicit arg > session > convention
    od_arg = arguments.get("output_dir")
    if od_arg:
        output_dir = str(Path(_resolve_path(od_arg)))
    elif session is not None and session.output_dir:
        output_dir = session.output_dir
    else:
        output_dir = str(Path(rp) / "repowiki")

    # Determine if docs were written
    docs_generated = False
    from codewiki.src.config import meta_join
    if os.path.exists(meta_join(output_dir, "metadata.json")):
        docs_generated = True
    elif session is not None and session.docs_written > 0:
        docs_generated = True

    if docs_generated:
        _write_generation_metadata_from_disk(output_dir, rp)
    else:
        logger.info("No docs written; skipping metadata.json baseline update")

    # Rebuild wiki index.md, log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(output_dir, "close_session", "会话关闭")
        rebuild_index(output_dir)
    except Exception:
        pass

    # Build final BM25 search index
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index
        build_full_index(output_dir, session=session)
    except Exception:
        pass

    # Auto-generate reading guide (PageRank) + optional HTML export
    if docs_generated and session is not None and session.components:
        try:
            from codewiki.mcp.tools.reading_guide import generate_reading_guide
            generate_reading_guide(
                session.components,
                session.module_tree or None,
                output_dir,
            )
        except Exception:
            logger.debug("Failed to generate reading guide", exc_info=True)

        # HTML export is opt-in via schema.yaml → export.html: true
        try:
            import yaml
            from codewiki.src.config import SCHEMA_FILENAME
            schema_path = Path(output_dir) / SCHEMA_FILENAME
            html_enabled = False
            if schema_path.exists():
                schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
                html_enabled = schema.get("export", {}).get("html", False)
            if html_enabled:
                from codewiki.mcp.tools.html_export import generate_html_export
                generate_html_export(output_dir)
        except Exception:
            logger.debug("Failed to generate HTML export", exc_info=True)

    # Inject AGENTS.md
    if docs_generated:
        try:
            from codewiki.mcp.tools.agents_md import write_agents_md
            write_agents_md(repo_path=rp, output_dir=output_dir)
        except Exception:
            logger.debug("Failed to update AGENTS.md", exc_info=True)

    # Clean up workspace files
    from codewiki.mcp.workspace import SessionWorkspace
    ws = SessionWorkspace(Path(rp), "cleanup")
    ws.cleanup()

    # Remove session from store if exists
    if session is not None:
        store.remove(session.session_id)

    return json.dumps({
        "status": "closed",
        "output_dir": output_dir,
    })
