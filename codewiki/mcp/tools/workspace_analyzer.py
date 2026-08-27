"""MCP tool: analyze_workspace — scan a parent directory for git repos,
analyze each independently, and generate a workspace-level overview.md
with cross-service topology.

Design principle: one .git = one repowiki.
- Monorepo (single .git): analyze as one repo via analyze_repo directly.
- Multi-repo (multiple .git): each sub-repo gets its own repowiki,
  parent gets a lightweight overview.md with service descriptions,
  cross-service relationships (auto-detected), and links to sub-repikis.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from codewiki.mcp.session import SessionStore
from codewiki.mcp.workspace import SessionWorkspace

logger = logging.getLogger(__name__)

# Directories to skip during workspace scanning
_DEFAULT_EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".codewiki",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
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


def _run_cross_service_analysis(
    workspace_path: Path,
    output_dir: Path,
    repo_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run cross-service matching across all analyzed repos.

    Returns a dict with topology summary and writes results to .meta/.
    """
    from codewiki.src.be.dependency_analyzer.analysis.cross_service_matcher import (
        CrossServiceMatcher,
    )
    from codewiki.src.be.dependency_analyzer.analysis.topology_visualizer import (
        TopologyVisualizer,
    )
    from codewiki.src.be.dependency_analyzer.models.cross_service import (
        RouteNode,
        RouteProtocol,
        RouteRole,
    )

    matcher = CrossServiceMatcher()
    all_routes_raw: List[Dict] = []
    total_routes = 0

    # Load routes from each repo's SQLite cache
    for r in repo_results:
        repo_path = r.get("path", "")
        if not repo_path:
            continue
        try:
            from codewiki.mcp.cache import AnalysisCache

            cache = AnalysisCache(Path(repo_path))
            routes_raw = cache.get_all_routes()
            cache.close()

            # Convert raw dicts to RouteNode objects for the matcher
            route_nodes: List[RouteNode] = []
            for rd in routes_raw:
                try:
                    route_nodes.append(
                        RouteNode(
                            route_key=rd["route_key"],
                            protocol=RouteProtocol(rd.get("protocol", "http")),
                            method=rd.get("method"),
                            path=rd.get("path", ""),
                            role=RouteRole(rd.get("role", "server")),
                            component_id=rd.get("component_id", ""),
                            repo_name=rd.get("repo_name", r["name"]),
                            file_path=rd.get("file_path", ""),
                            line_number=rd.get("line_number", 0),
                            framework=rd.get("framework"),
                            extra=rd.get("extra", {}),
                        )
                    )
                except Exception:
                    continue

            matcher.add_repo_routes(r["name"], route_nodes)
            all_routes_raw.extend(routes_raw)
            total_routes += len(route_nodes)
        except Exception as e:
            logger.warning("Failed to load routes for %s: %s", r["name"], e)

    if total_routes == 0:
        logger.info("No routes found across workspace repos")
        # Write empty indicator so query_cross_service knows analysis ran
        meta_dir = output_dir / ".meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "cross_service_links.json").write_text("[]", encoding="utf-8")
        (meta_dir / "workspace_routes.json").write_text("[]", encoding="utf-8")
        return {"total_routes": 0, "total_links": 0}

    # Run matching
    topology = matcher.match()
    logger.info(
        "Cross-service matching: %d routes → %d links, %d unmatched",
        len(topology.routes),
        len(topology.links),
        len(topology.unmatched_routes),
    )

    # Generate visualizer output — concise for overview
    viz = TopologyVisualizer()
    cross_service_md = viz.render_overview_section(topology)

    # Persist results
    meta_dir = output_dir / ".meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Save links as JSON
    links_data = [link.model_dump() for link in topology.links]
    (meta_dir / "cross_service_links.json").write_text(
        json.dumps(links_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Save all routes as JSON
    routes_data = [route.model_dump() for route in topology.routes]
    (meta_dir / "workspace_routes.json").write_text(
        json.dumps(routes_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Run infra scanner for supplementary service discovery
    try:
        from codewiki.src.be.dependency_analyzer.analysis.infra_scanner import InfraScanner

        scanner = InfraScanner(str(workspace_path))
        infra_services = scanner.scan()
        if infra_services:
            infra_data = {name: svc.to_dict() for name, svc in infra_services.items()}
            (meta_dir / "infra_services.json").write_text(
                json.dumps(infra_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("Infra scanner found %d services", len(infra_services))
    except Exception as e:
        logger.debug("Infra scanner skipped: %s", e)

    return {
        "total_routes": len(topology.routes),
        "total_links": len(topology.links),
        "total_unmatched": len(topology.unmatched_routes),
        "cross_service_md": cross_service_md,
    }


def _load_infra_services(output_dir: Path) -> Dict[str, Any]:
    """Load infra_services.json from .meta/ if available."""
    infra_path = output_dir / ".meta" / "infra_services.json"
    if not infra_path.exists():
        return {}
    try:
        return json.loads(infra_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _generate_overview(
    workspace_name: str,
    output_dir: Path,
    repo_results: List[Dict[str, Any]],
    cross_service_info: Dict[str, Any] = None,
) -> Path:
    """Generate workspace overview.md — concise architectural scaffold.

    The output is designed to be enriched by the calling LLM agent via
    ``get_prompt(prompt_type="overview_workspace")``.  It provides:
    - Compact service inventory
    - Mermaid topology + aggregated cross-service summary
    - Links to per-repo wikis and the full API reference
    """
    overview_path = output_dir / "overview.md"

    lines = [
        f"# {workspace_name} — Workspace Overview",
        "",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]

    # --- Architectural narrative placeholder (for LLM enrichment) ---
    lines.extend(
        [
            "<!-- AGENT_ENRICH: Replace this section with a 2-3 paragraph architectural",
            "     narrative describing the system's purpose, high-level data flow,",
            '     and key design decisions. Use get_prompt(prompt_type="overview_workspace")',
            "     for guidance. -->",
            "",
        ]
    )

    # --- Services (compact) ---
    lines.extend(
        [
            "## Services",
            "",
            "| Service | Path | Languages | Components | Wiki |",
            "|---------|------|-----------|------------|------|",
        ]
    )

    for r in repo_results:
        name = r["name"]
        rel_path = r["relative_path"]
        languages = ", ".join(r.get("languages", {}).keys()) or "—"
        components = r.get("total_components", 0)
        # BUG-20: use relative paths instead of absolute
        try:
            wiki_rel = os.path.relpath(r["output_dir"], str(output_dir)).replace("\\", "/")
        except ValueError:
            wiki_rel = r["relative_path"] + "/repowiki"
        wiki_link = f"[wiki]({wiki_rel}/wiki/)" if r.get("has_overview") else f"[wiki]({wiki_rel}/)"
        lines.append(f"| {name} | `{rel_path}` | {languages} | {components} | {wiki_link} |")

    lines.append("")

    # --- Infra services (ports) ---
    infra_services = _load_infra_services(output_dir)
    if infra_services:
        lines.extend(
            [
                "## Infrastructure Services",
                "",
                "| Service | Type | Port(s) |",
                "|---------|------|---------|",
            ]
        )
        for svc_name, svc_info in infra_services.items():
            svc_type = svc_info.get("type", "unknown")
            ports = svc_info.get("ports", [])
            ports_str = ", ".join(str(p) for p in ports) if ports else "—"
            lines.append(f"| {svc_name} | {svc_type} | {ports_str} |")
        lines.append("")

    # --- Cross-service section (concise: Mermaid + aggregated summary) ---
    if cross_service_info and cross_service_info.get("cross_service_md"):
        lines.append(cross_service_info["cross_service_md"])
    else:
        lines.extend(
            [
                "## Cross-Service Relationships",
                "",
                "_No cross-service API calls detected automatically._",
                "",
            ]
        )

    # --- Per-repo overview links ---
    lines.extend(
        [
            "## Service Overviews",
            "",
        ]
    )

    for r in repo_results:
        name = r["name"]
        rel_path = r["relative_path"]
        # BUG-20: use relative path and only link wiki/overview.md if it exists
        try:
            output_rel = os.path.relpath(r["output_dir"], str(output_dir)).replace("\\", "/")
        except ValueError:
            output_rel = r["relative_path"] + "/repowiki"
        overview_file = Path(r["output_dir"]) / "wiki" / "overview.md"
        if overview_file.exists():
            lines.append(f"- [{name}]({output_rel}/wiki/overview.md) — `{rel_path}`")
        else:
            lines.append(f"- {name} — `{rel_path}`")

    lines.append("")

    overview_path.write_text("\n".join(lines), encoding="utf-8")
    return overview_path


def _handle_monorepo_fallback(
    workspace_path: Path,
    output_dir: Path,
    store: SessionStore,
) -> str:
    """Handle the case where workspace_path is itself a git repo (monorepo).

    Instead of failing with "No git repositories found", delegate to
    analyze_repo which already detects sub-services within a single repo
    (via docker-compose, Dockerfiles, build manifests, convention dirs)
    and runs intra-repo cross-service matching.
    """
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    repo_output_dir = output_dir
    logger.info("Monorepo fallback: analyzing %s as single repo", workspace_path.name)

    try:
        result_json = handle_analyze_repo(
            {
                "repo_path": str(workspace_path),
                "output_dir": str(repo_output_dir),
            },
            store,
        )
        result = json.loads(result_json)
    except Exception as e:
        logger.error("Monorepo analyze_repo failed: %s", e)
        return json.dumps({"error": f"Monorepo analysis failed: {e}"})

    # Extract cross-service info from analyze_repo's sub-service detection
    cross_service = result.get("cross_service", {})

    # Create a lightweight workspace session for ingest_note / query_wiki
    workspace_session = store.create(
        repo_path=str(workspace_path),
        output_dir=str(repo_output_dir),
        components={},
        leaf_nodes=[],
    )
    ws_workspace = SessionWorkspace(str(workspace_path), workspace_session.session_id)
    workspace_session.workspace = ws_workspace

    return json.dumps(
        {
            "mode": "monorepo",
            "workspace_session_id": workspace_session.session_id,
            "workspace_path": str(workspace_path),
            "output_dir": str(repo_output_dir),
            "explanation": (
                "No sub-repos with individual .git directories were found. "
                "The workspace root is itself a git repository (monorepo). "
                "Cross-service analysis used analyze_repo's single-repo route "
                "detection (sub-service discovery via docker-compose, Dockerfiles, "
                "build manifests, convention directories) instead of multi-repo matching."
            ),
            "analyze_repo_result": result,
            "cross_service": {
                "total_routes": cross_service.get("total_routes", 0),
                "total_links": cross_service.get("total_links", 0),
                "total_unmatched": cross_service.get("total_unmatched", 0),
                "sub_services": cross_service.get("sub_services", []),
            },
        },
        indent=2,
        ensure_ascii=False,
    )


def handle_analyze_workspace(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Scan a workspace directory for git repos and analyze each one.

    For multi-repo workspaces: each sub-repo gets its own full repowiki,
    and a lightweight overview.md is generated at the parent level with
    auto-detected cross-service relationships.
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
        # Monorepo fallback: if the workspace itself is a git repo, delegate
        # to analyze_repo which already handles sub-service detection.
        if (workspace_path / ".git").exists():
            return _handle_monorepo_fallback(workspace_path, output_dir, store)
        return json.dumps(
            {
                "error": f"No git repositories found in {workspace_path}",
                "hint": "Make sure each sub-project has its own .git directory, "
                "or that the workspace root is itself a git repository (monorepo).",
            }
        )

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

            # Read summary.json for richer info (path comes from analyze_repo result)
            summary = {}
            summary_path = Path(
                result.get("files", {}).get("summary") or (repo_output_dir / "summary.json")
            )
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            stats = result.get("stats") or {}

            repo_results.append(
                {
                    "name": repo_path.name,
                    "relative_path": str(repo_path.relative_to(workspace_path)),
                    "path": str(repo_path),
                    "output_dir": str(repo_output_dir),
                    "session_id": result.get("session_id"),
                    "total_components": stats.get(
                        "total_components", summary.get("total_components", 0)
                    ),
                    "total_leaf_nodes": stats.get(
                        "total_leaf_nodes", summary.get("total_leaf_nodes", 0)
                    ),
                    "languages": stats.get("languages", summary.get("languages", {})),
                    "has_overview": (repo_output_dir / "overview.md").exists()
                    or (repo_output_dir / "wiki" / "overview.md").exists(),
                }
            )
        except Exception as e:
            logger.error("Failed to analyze %s: %s", repo_path.name, e)
            errors.append({"repo": repo_path.name, "error": str(e)})

    # Cross-service analysis
    cross_service_info = {}
    try:
        cross_service_info = _run_cross_service_analysis(
            workspace_path,
            output_dir,
            repo_results,
        )
    except Exception as e:
        logger.warning("Cross-service analysis failed: %s", e)

    # Generate workspace overview.md (with cross-service topology)
    overview_path = _generate_overview(
        workspace_path.name,
        output_dir,
        repo_results,
        cross_service_info,
    )

    # Create lightweight workspace session for ingest_note / query_wiki
    workspace_session = store.create(
        repo_path=str(workspace_path),
        output_dir=str(output_dir),
        components={},
        leaf_nodes=[],
    )
    ws_workspace = SessionWorkspace(str(workspace_path), workspace_session.session_id)
    workspace_session.workspace = ws_workspace

    return json.dumps(
        {
            "workspace_session_id": workspace_session.session_id,
            "workspace_path": str(workspace_path),
            "overview_path": str(overview_path),
            "repos_analyzed": len(repo_results),
            "repos": repo_results,
            "cross_service": {
                "total_routes": cross_service_info.get("total_routes", 0),
                "total_links": cross_service_info.get("total_links", 0),
                "total_unmatched": cross_service_info.get("total_unmatched", 0),
            },
            "errors": errors if errors else None,
        },
        indent=2,
        ensure_ascii=False,
    )
