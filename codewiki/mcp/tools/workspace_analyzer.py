"""MCP tool: analyze_workspace — scan a parent directory for git repos,
analyze each independently, and generate a workspace-level overview.md.

Design principle: one .git = one repowiki.
- Monorepo (single .git): analyze as one repo via analyze_repo directly.
- Multi-repo (multiple .git): each sub-repo gets its own repowiki,
  parent gets a lightweight overview.md with service descriptions,
  cross-service relationships, and links to sub-repikis.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from codewiki.mcp.session import SessionStore
from codewiki.mcp.workspace import SessionWorkspace

logger = logging.getLogger(__name__)

# Directories to skip during workspace scanning
_DEFAULT_EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__",
    ".codewiki", ".git", ".idea", ".vscode", "dist", "build",
}


def _scan_git_repos(workspace_path: Path, exclude_dirs: set) -> List[Path]:
    """Find immediate child directories that are git repositories."""
    repos = []
    try:
        for child in sorted(workspace_path.iterdir()):
            if not child.is_dir():
                continue
            # Skip hidden directories and excluded dirs
            if child.name.startswith(".") or child.name in exclude_dirs:
                continue
            if (child / ".git").exists():
                repos.append(child)
    except PermissionError:
        logger.warning("Permission denied scanning %s", workspace_path)
    return repos


def _generate_overview(
    workspace_name: str,
    output_dir: Path,
    repo_results: List[Dict[str, Any]],
) -> Path:
    """Generate workspace overview.md with service table and links."""
    overview_path = output_dir / "overview.md"

    lines = [
        f"# {workspace_name} — Workspace Overview",
        "",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Services",
        "",
        "| Service | Path | Languages | Components | Leaf Nodes | Wiki |",
        "|---------|------|-----------|------------|------------|------|",
    ]

    for r in repo_results:
        name = r["name"]
        rel_path = r["relative_path"]
        languages = ", ".join(r.get("languages", {}).keys()) or "—"
        components = r.get("total_components", 0)
        leaf_nodes = r.get("total_leaf_nodes", 0)
        wiki_link = f"[wiki]({r['output_dir']}/wiki/)" if r.get("has_overview") else f"[wiki]({r['output_dir']}/)"
        lines.append(
            f"| {name} | `{rel_path}` | {languages} | {components} | {leaf_nodes} | {wiki_link} |"
        )

    lines.extend([
        "",
        "## Cross-Service Relationships",
        "",
        "_Add cross-service call relationships using `ingest_note` with the workspace session._",
        "",
        "```",
        "# Example:",
        "# ingest_note(session_id='<workspace_session_id>',",
        "#   note='Service A calls Service B via HTTP GET /api/users/:id',",
        "#   tags=['cross-repo', 'api-contract'],",
        "#   decisions=['Service A depends on Service B user query API'])",
        "```",
        "",
        "## Service Overviews",
        "",
    ])

    for r in repo_results:
        name = r["name"]
        rel_path = r["relative_path"]
        output_rel = r["output_dir"]
        lines.append(f"- [{name}]({output_rel}/wiki/overview.md) — `{rel_path}`")

    lines.append("")

    overview_path.write_text("\n".join(lines), encoding="utf-8")
    return overview_path


def handle_analyze_workspace(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Scan a workspace directory for git repos and analyze each one.

    For multi-repo workspaces: each sub-repo gets its own full repowiki,
    and a lightweight overview.md is generated at the parent level.
    """
    workspace_path = Path(arguments["workspace_path"]).resolve()
    if not workspace_path.is_dir():
        return json.dumps({"error": f"Workspace path not found: {workspace_path}"})

    # Parse exclude_dirs
    exclude_str = arguments.get("exclude_dirs", "")
    exclude_dirs = set(_DEFAULT_EXCLUDE_DIRS)
    if exclude_str:
        exclude_dirs.update(d.strip() for d in exclude_str.split(",") if d.strip())

    # Output dir for the workspace-level overview
    output_dir_arg = arguments.get("output_dir")
    if output_dir_arg:
        output_dir = Path(output_dir_arg).resolve()
    else:
        output_dir = workspace_path / "workspace-wiki"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Scan for git repos
    repos = _scan_git_repos(workspace_path, exclude_dirs)
    if not repos:
        return json.dumps({
            "error": f"No git repositories found in {workspace_path}",
            "hint": "Make sure each sub-project has its own .git directory.",
        })

    # Analyze each repo
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    repo_results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for repo_path in repos:
        repo_output_dir = repo_path / "repowiki"
        logger.info("Analyzing %s → %s", repo_path.name, repo_output_dir)
        try:
            result_json = handle_analyze_repo(
                {
                    "repo_path": str(repo_path),
                    "output_dir": str(repo_output_dir),
                },
                store,
            )
            result = json.loads(result_json)

            # Read summary.json for richer info
            summary = {}
            summary_path = repo_output_dir / "summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            repo_results.append({
                "name": repo_path.name,
                "relative_path": str(repo_path.relative_to(workspace_path)),
                "path": str(repo_path),
                "output_dir": str(repo_output_dir),
                "session_id": result.get("session_id"),
                "total_components": result.get("total_components", summary.get("total_components", 0)),
                "total_leaf_nodes": result.get("total_leaf_nodes", summary.get("total_leaf_nodes", 0)),
                "languages": summary.get("languages", result.get("languages", {})),
                "has_overview": (repo_output_dir / "overview.md").exists() or (repo_output_dir / "wiki" / "overview.md").exists(),
            })
        except Exception as e:
            logger.error("Failed to analyze %s: %s", repo_path.name, e)
            errors.append({"repo": repo_path.name, "error": str(e)})

    # Generate workspace overview.md
    overview_path = _generate_overview(workspace_path.name, output_dir, repo_results)

    # Create lightweight workspace session for ingest_note / query_wiki
    workspace_session = store.create(
        repo_path=str(workspace_path),
        output_dir=str(output_dir),
        components={},
        leaf_nodes=[],
    )
    ws_workspace = SessionWorkspace(str(workspace_path), workspace_session.session_id)
    workspace_session.workspace = ws_workspace

    return json.dumps({
        "workspace_session_id": workspace_session.session_id,
        "workspace_path": str(workspace_path),
        "overview_path": str(overview_path),
        "repos_analyzed": len(repo_results),
        "repos": repo_results,
        "errors": errors if errors else None,
    }, indent=2, ensure_ascii=False)
