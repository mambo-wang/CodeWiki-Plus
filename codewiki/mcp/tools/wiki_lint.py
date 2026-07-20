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
_ALL_CHECKS = {
    "stale_refs", "undocumented", "broken_links", "cycles", "coverage",
    "orphan_pages", "no_outlinks", "missing_aliases", "stale_sources",
    "superseded_pages",
}

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
        p.mkdir(parents=True, exist_ok=True)
        return p
    return None


def _load_module_tree(output_dir: Path) -> Optional[dict]:
    """Load module_tree.json from output directory."""
    from codewiki.src.config import meta_resolve
    mt_path = Path(meta_resolve(output_dir, "module_tree.json"))
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
    # Recursively collect all .md files for valid_files set
    valid_files = {f.name for f in output_dir.rglob("*.md")}

    for md_file in output_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for line_no, line in enumerate(content.splitlines(), 1):
            # Check [[Name]](file.md) patterns
            for match in _WIKILINK_RE.finditer(line):
                ref_name = match.group(1)
                ref_file = match.group(2)
                # Resolve relative to source file's directory
                resolved = (md_file.parent / ref_file).resolve()
                if not resolved.exists():
                    issues.append({
                        "check": "stale_refs",
                        "severity": "error",
                        "message": f"Reference to non-existent file '{ref_file}' (module '{ref_name}')",
                        "file": str(md_file.relative_to(output_dir)),
                        "line": line_no,
                        "suggestion": f"Remove or update the reference to '{ref_name}'",
                    })

            # Check simple [text](file.md) patterns (skip http links)
            for match in _MD_LINK_RE.finditer(line):
                ref_text = match.group(1)
                ref_file = match.group(2)
                if ref_file.startswith(("http://", "https://")):
                    continue
                # Resolve relative to source file's directory
                resolved = (md_file.parent / ref_file).resolve()
                if not resolved.exists():
                    issues.append({
                        "check": "stale_refs",
                        "severity": "error",
                        "message": f"Broken link to '{ref_file}'",
                        "file": str(md_file.relative_to(output_dir)),
                        "line": line_no,
                        "suggestion": f"Update the link target or remove the reference",
                    })

    return issues


def _check_broken_links(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find broken markdown links within the documentation directory."""
    issues: List[Dict[str, Any]] = []

    for md_file in output_dir.rglob("*.md"):
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
                # Resolve relative to source file's directory
                target = (md_file.parent / file_part).resolve()
                if not target.exists():
                    issues.append({
                        "check": "broken_links",
                        "severity": "error",
                        "message": f"Link target '{ref_file}' does not exist",
                        "file": str(md_file.relative_to(output_dir)),
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
#  LLM Wiki checks
# ---------------------------------------------------------------------------

def _check_orphan_pages(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find wiki pages with no incoming links from other pages."""
    issues: List[Dict[str, Any]] = []
    from codewiki.src.config import WIKI_SYSTEM_FILES

    # Collect all .md files and their relative paths
    all_pages: Dict[str, Path] = {}
    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel = str(md_file.relative_to(output_dir))
        all_pages[rel] = md_file

    if not all_pages:
        return issues

    # Build incoming link set
    linked_targets: Set[str] = set()
    for md_file in all_pages.values():
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _MD_LINK_RE.finditer(content):
            ref_file = match.group(2).split("#")[0]
            if ref_file.startswith(("http://", "https://", "mailto:")):
                continue
            # Resolve relative to the source file
            resolved = (md_file.parent / ref_file).resolve()
            try:
                resolved_rel = str(resolved.relative_to(output_dir.resolve()))
                linked_targets.add(resolved_rel)
            except ValueError:
                pass

    # Find pages with no incoming links
    for rel_path, md_file in all_pages.items():
        if rel_path not in linked_targets:
            issues.append({
                "check": "orphan_pages",
                "severity": "warning",
                "message": f"Page has no incoming links",
                "file": rel_path,
                "suggestion": "Add cross-references from related pages",
            })

    return issues


def _check_no_outlinks(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find wiki pages with no outgoing links to other wiki pages."""
    issues: List[Dict[str, Any]] = []
    from codewiki.src.config import WIKI_SYSTEM_FILES

    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel_path = str(md_file.relative_to(output_dir))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        has_outlink = False
        for match in _MD_LINK_RE.finditer(content):
            ref_file = match.group(2).split("#")[0]
            if ref_file.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md_file.parent / ref_file).resolve()
            if resolved.exists():
                has_outlink = True
                break

        if not has_outlink:
            issues.append({
                "check": "no_outlinks",
                "severity": "info",
                "message": "Page has no outgoing links to other wiki pages",
                "file": rel_path,
                "suggestion": "Add cross-references to related pages for better navigation",
            })

    return issues


def _check_missing_aliases(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find wiki pages in structured directories that lack aliases in frontmatter."""
    issues: List[Dict[str, Any]] = []

    wiki_dir = output_dir / "wiki"
    if not wiki_dir.is_dir():
        return issues

    for md_file in wiki_dir.rglob("*.md"):
        if not md_file.is_file():
            continue
        rel_path = str(md_file.relative_to(output_dir))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Check frontmatter for aliases
        if content.startswith("---"):
            try:
                end = content.index("---", 3)
                fm = content[3:end]
                has_aliases = any(
                    line.strip().startswith("aliases:")
                    for line in fm.splitlines()
                )
                if not has_aliases:
                    issues.append({
                        "check": "missing_aliases",
                        "severity": "info",
                        "message": "Page lacks 'aliases' in frontmatter",
                        "file": rel_path,
                        "suggestion": "Add alternate names to improve search discoverability",
                    })
            except (ValueError, IndexError):
                pass

    return issues


def _check_stale_sources(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find pages referencing retracted source documents."""
    issues: List[Dict[str, Any]] = []
    import json as _json

    from codewiki.src.config import SOURCE_REGISTRY_FILENAME, META_DIR

    # Load source registry (prefer .meta/, fallback to root for compat)
    meta_path = output_dir / META_DIR / SOURCE_REGISTRY_FILENAME
    root_path = output_dir / SOURCE_REGISTRY_FILENAME
    reg_path = meta_path if meta_path.exists() else root_path
    retracted_sources: Set[str] = set()
    if reg_path.exists():
        try:
            registry = _json.loads(reg_path.read_text(encoding="utf-8"))
            sources = registry.get("sources", {})
            retracted_sources = {
                name for name, info in sources.items()
                if isinstance(info, dict) and info.get("status") == "retracted"
            }
        except (json.JSONDecodeError, OSError):
            pass

    if not retracted_sources:
        return issues

    # Scan all wiki and notes pages for source_ref annotations
    _SRC_REF_RE = re.compile(r"\[\^src:(\w+)(?::[^\]]*)?\]")
    for search_dir in ("wiki", "notes"):
        d = output_dir / search_dir
        if not d.is_dir():
            continue
        for md_file in d.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel_path = str(md_file.relative_to(output_dir))
            for match in _SRC_REF_RE.finditer(content):
                src_name = match.group(1)
                if src_name in retracted_sources:
                    issues.append({
                        "check": "stale_sources",
                        "severity": "warning",
                        "message": f"References retracted source '{src_name}'",
                        "file": rel_path,
                        "suggestion": f"Update or remove the reference to '{src_name}'",
                    })

    return issues


def _check_superseded_pages(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find pages marked as superseded (status: superseded in frontmatter)."""
    issues: List[Dict[str, Any]] = []

    for search_dir_name in ("wiki", "notes"):
        d = output_dir / search_dir_name
        if not d.is_dir():
            continue
        for md_file in d.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Quick check: only parse frontmatter if 'superseded' appears
            if "superseded" not in content:
                continue
            # Check frontmatter for status: superseded
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    fm_text = content[3:end]
                    if re.search(r"^status:\s*superseded", fm_text, re.MULTILINE):
                        rel_path = str(md_file.relative_to(output_dir))
                        # Try to extract superseded_by
                        superseded_by = ""
                        m = re.search(r"^superseded_by:\s*[\"']?(.+?)[\"']?\s*$",
                                      fm_text, re.MULTILINE)
                        if m:
                            superseded_by = m.group(1)
                        msg = "Page marked as superseded"
                        if superseded_by:
                            msg += f" (replaced by: {superseded_by})"
                        issues.append({
                            "check": "superseded_pages",
                            "severity": "info",
                            "message": msg,
                            "file": rel_path,
                            "suggestion": "Consider archiving or removing this page"
                                          + (f"; see '{superseded_by}'" if superseded_by else ""),
                        })

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

    # LLM Wiki checks
    if "orphan_pages" in checks and output_dir:
        all_issues.extend(_check_orphan_pages(output_dir))

    if "no_outlinks" in checks and output_dir:
        all_issues.extend(_check_no_outlinks(output_dir))

    if "missing_aliases" in checks and output_dir:
        all_issues.extend(_check_missing_aliases(output_dir))

    if "stale_sources" in checks and output_dir:
        all_issues.extend(_check_stale_sources(output_dir))

    if "superseded_pages" in checks and output_dir:
        all_issues.extend(_check_superseded_pages(output_dir))

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

    # Compute health score (0-100): start at 100, deduct per issue type
    health_score = 100
    for issue in filtered:
        if issue["severity"] == "error":
            health_score -= 10
        elif issue["severity"] == "warning":
            health_score -= 3
        else:
            health_score -= 1
    health_score = max(0, health_score)

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
        "health_score": health_score,
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
