"""MCP tool: lint_wiki — documentation-code consistency checker.

Performs health checks on generated documentation, detecting stale references,
undocumented components, broken links, circular dependencies, and coverage gaps.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.workspace_result import write_result

logger = logging.getLogger(__name__)

# Severity levels in priority order
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# All available check names
_ALL_CHECKS = {"stale_refs", "undocumented", "broken_links", "cycles", "coverage"}

# Regex patterns for markdown links
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]\(([^\)]+\.md)\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")
_SIMPLE_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _get_output_dir(session: Optional[SessionState], arguments: Dict) -> Optional[Path]:
    """Resolve the output directory from session or arguments."""
    if session:
        return Path(session.output_dir)
    output_dir = arguments.get("output_dir")
    if output_dir:
        p = Path(output_dir).expanduser().resolve()
        if p.is_dir():
            return p
    return None


def _load_module_tree(output_dir: Path) -> Optional[dict]:
    """Load module_tree.json from output directory."""
    mt_path = output_dir / "module_tree.json"
    if not mt_path.exists():
        return None
    try:
        return json.loads(mt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _get_all_module_names(module_tree: dict) -> Set[str]:
    """Collect all module names from the tree (including nested)."""
    names: Set[str] = set()

    def _walk(tree: dict):
        for name, info in tree.items():
            names.add(name)
            children = info.get("children", {})
            if isinstance(children, dict):
                _walk(children)

    _walk(module_tree)
    return names


def _get_documented_components(module_tree: dict) -> Set[str]:
    """Collect all component IDs that appear in the module tree."""
    comps: Set[str] = set()

    def _walk(tree: dict):
        for name, info in tree.items():
            comps.update(info.get("components", []))
            children = info.get("children", {})
            if isinstance(children, dict):
                _walk(children)

    _walk(module_tree)
    return comps


# ---------------------------------------------------------------------------
#  Individual checks
# ---------------------------------------------------------------------------

def _check_stale_refs(
    output_dir: Path,
    module_tree: Optional[dict],
) -> List[Dict[str, Any]]:
    """Find doc references to modules that no longer exist."""
    issues: List[Dict[str, Any]] = []
    if not module_tree:
        return issues

    valid_modules = _get_all_module_names(module_tree)
    # Also allow overview.md and notes/
    valid_files = {f.name for f in output_dir.glob("*.md")}

    for md_file in output_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for line_no, line in enumerate(content.splitlines(), 1):
            # Check [[Name]](file.md) patterns
            for match in _WIKILINK_RE.finditer(line):
                ref_name = match.group(1)
                ref_file = match.group(2)
                if not (output_dir / ref_file).exists():
                    issues.append({
                        "check": "stale_refs",
                        "severity": "error",
                        "message": f"Reference to non-existent file '{ref_file}' (module '{ref_name}')",
                        "file": md_file.name,
                        "line": line_no,
                        "suggestion": f"Remove or update the reference to '{ref_name}'",
                    })

            # Check simple [text](file.md) patterns (skip http links)
            for match in _MD_LINK_RE.finditer(line):
                ref_text = match.group(1)
                ref_file = match.group(2)
                if ref_file.startswith(("http://", "https://")):
                    continue
                if not (output_dir / ref_file).exists():
                    issues.append({
                        "check": "stale_refs",
                        "severity": "error",
                        "message": f"Broken link to '{ref_file}'",
                        "file": md_file.name,
                        "line": line_no,
                        "suggestion": f"Update the link target or remove the reference",
                    })

    return issues


def _check_broken_links(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find broken markdown links within the documentation directory."""
    issues: List[Dict[str, Any]] = []

    for md_file in output_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for line_no, line in enumerate(content.splitlines(), 1):
            for match in _MD_LINK_RE.finditer(line):
                ref_file = match.group(2)
                if ref_file.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                # Strip anchor (#section) from path
                file_part = ref_file.split("#")[0]
                if not file_part:
                    continue
                target = (output_dir / file_part).resolve()
                if not target.exists():
                    issues.append({
                        "check": "broken_links",
                        "severity": "error",
                        "message": f"Link target '{ref_file}' does not exist",
                        "file": md_file.name,
                        "line": line_no,
                        "suggestion": "Fix the link path or create the target file",
                    })

    return issues


def _check_undocumented(
    components: Optional[Dict[str, Any]],
    module_tree: Optional[dict],
    threshold: int = 5,
) -> List[Dict[str, Any]]:
    """Find high-impact components that are not covered by any module."""
    issues: List[Dict[str, Any]] = []
    if not components or not module_tree:
        return issues

    documented = _get_documented_components(module_tree)

    # Build reverse dependency count
    reverse_count: Dict[str, int] = defaultdict(int)
    for comp_id, node in components.items():
        deps = getattr(node, "depends_on", None) or set()
        for dep in deps:
            reverse_count[dep] += 1

    for comp_id, count in sorted(reverse_count.items(), key=lambda x: -x[1]):
        if count < threshold:
            break
        if comp_id not in documented:
            issues.append({
                "check": "undocumented",
                "severity": "warning",
                "message": (
                    f"High-impact component '{comp_id}' "
                    f"({count} dependents) has no documentation coverage"
                ),
                "component_id": comp_id,
                "depended_by_count": count,
                "suggestion": "Add this component to a module or create dedicated documentation",
            })

    return issues


def _check_cycles(
    components: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect circular dependencies at the component level."""
    issues: List[Dict[str, Any]] = []
    if not components:
        return issues

    try:
        from codewiki.src.be.dependency_analyzer.topo_sort import (
            build_graph_from_components,
            detect_cycles,
        )
        graph = build_graph_from_components(components)
        cycles = detect_cycles(graph)
        for cycle in cycles[:10]:  # cap at 10 cycles
            issues.append({
                "check": "cycles",
                "severity": "info",
                "message": f"Circular dependency detected: {' → '.join(cycle[:5])}{'...' if len(cycle) > 5 else ''}",
                "components": cycle,
                "suggestion": "Consider refactoring to break the cycle (e.g. via interface or event pattern)",
            })
    except Exception as e:
        logger.warning("Cycle detection skipped: %s", e)

    return issues


def _check_coverage(
    components: Optional[Dict[str, Any]],
    module_tree: Optional[dict],
    output_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Report documentation coverage statistics."""
    issues: List[Dict[str, Any]] = []
    if not components or not module_tree:
        return issues

    documented = _get_documented_components(module_tree)
    total = len(components)
    covered = len(documented & set(components.keys()))
    pct = (covered / total * 100) if total > 0 else 0

    issues.append({
        "check": "coverage",
        "severity": "info",
        "message": f"Documentation coverage: {covered}/{total} components ({pct:.1f}%)",
        "covered": covered,
        "total": total,
        "percentage": round(pct, 1),
        "suggestion": (
            "Coverage is below 50%" if pct < 50
            else "Good coverage"
        ),
    })

    # Per-module coverage
    def _walk(tree: dict):
        for name, info in tree.items():
            mod_comps = set(info.get("components", []))
            if mod_comps:
                mod_covered = len(mod_comps & set(components.keys()))
                mod_total = len(mod_comps)
                mod_pct = (mod_covered / mod_total * 100) if mod_total > 0 else 0
                if mod_pct < 50:
                    issues.append({
                        "check": "coverage",
                        "severity": "info",
                        "message": f"Module '{name}': {mod_covered}/{mod_total} components ({mod_pct:.0f}%)",
                        "module": name,
                        "covered": mod_covered,
                        "total": mod_total,
                        "percentage": round(mod_pct, 1),
                        "suggestion": "Consider adding more components to this module's documentation",
                    })
            children = info.get("children", {})
            if isinstance(children, dict):
                _walk(children)

    _walk(module_tree)

    return issues


# ---------------------------------------------------------------------------
#  Main handler
# ---------------------------------------------------------------------------

def handle_lint_wiki(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Run documentation health checks and return structured results."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None

    checks = arguments.get("checks", ["all"])
    if "all" in checks:
        checks = list(_ALL_CHECKS)
    else:
        checks = [c for c in checks if c in _ALL_CHECKS]

    severity_filter = arguments.get("severity_filter", "info")
    min_severity = _SEVERITY_ORDER.get(severity_filter, 2)

    output_dir = _get_output_dir(session, arguments)
    module_tree = None
    components = None

    if session:
        components = session.components
        module_tree = session.module_tree or None

    if output_dir and module_tree is None:
        module_tree = _load_module_tree(output_dir)

    all_issues: List[Dict[str, Any]] = []

    # Run selected checks
    if "stale_refs" in checks and output_dir:
        all_issues.extend(_check_stale_refs(output_dir, module_tree))

    if "broken_links" in checks and output_dir:
        all_issues.extend(_check_broken_links(output_dir))

    if "undocumented" in checks:
        threshold = 5
        # Read threshold from schema if available
        if output_dir:
            try:
                import yaml
                from codewiki.src.config import SCHEMA_FILENAME
                schema_path = output_dir / SCHEMA_FILENAME
                if schema_path.exists():
                    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
                    threshold = (
                        schema.get("lint", {}).get("high_impact_threshold", 5)
                    )
            except Exception:
                pass
        all_issues.extend(_check_undocumented(components, module_tree, threshold))

    if "cycles" in checks:
        all_issues.extend(_check_cycles(components))

    if "coverage" in checks:
        all_issues.extend(_check_coverage(components, module_tree, output_dir))

    # Filter by severity
    filtered = [
        issue for issue in all_issues
        if _SEVERITY_ORDER.get(issue["severity"], 2) <= min_severity
    ]

    # Sort: errors first, then warnings, then info
    filtered.sort(key=lambda x: _SEVERITY_ORDER.get(x["severity"], 2))

    # Summary stats
    by_severity = {"error": 0, "warning": 0, "info": 0}
    for issue in filtered:
        by_severity[issue["severity"]] = by_severity.get(issue["severity"], 0) + 1

    summary_parts = []
    if by_severity["error"]:
        summary_parts.append(f"{by_severity['error']} error(s)")
    if by_severity["warning"]:
        summary_parts.append(f"{by_severity['warning']} warning(s)")
    if by_severity["info"]:
        summary_parts.append(f"{by_severity['info']} info")
    summary = (
        f"Found {', '.join(summary_parts)}. "
        + ("Priority: fix errors first." if by_severity["error"] else "No critical issues.")
        if filtered
        else "All checks passed. Documentation is healthy."
    )

    # LLM Wiki: log lint operation (no index rebuild needed)
    if output_dir:
        try:
            from codewiki.mcp.tools.wiki_index import append_log
            append_log(str(output_dir), "lint_wiki",
                       f"检查完成: {len(filtered)} 个问题")
        except Exception:
            pass

    result = {
        "total_issues": len(filtered),
        "by_severity": by_severity,
        "checks_run": checks,
        "issues": filtered,
        "summary": summary,
    }

    # Write to workspace file when session is available
    if session and getattr(session, "workspace", None):
        response = write_result(
            session,
            "lint_report.json",
            result,
            summary={
                "total_issues": len(filtered),
                "by_severity": by_severity,
                "summary": summary,
            },
        )
        return json.dumps(response, indent=2, ensure_ascii=False)

    # Fallback: return inline (no session / standalone mode)
    return json.dumps(result, indent=2, ensure_ascii=False)
