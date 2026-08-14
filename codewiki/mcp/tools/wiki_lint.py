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
    "superseded_pages", "overview_stale", "unsupported_claims",
    "isolated_components", "stale_notes", "note_clusters",
    "okf_conformance",
}

# OKF v0.2 lifecycle vocabulary (see okf/SPEC.md §5)
_OKF_STATUSES = {"draft", "stable", "deprecated"}
_LEGACY_STATUS_MAP = {
    "candidate": "draft",
    "confirmed": "stable",
    "rejected": "deprecated",
    "superseded": "deprecated",
}

# OKF v0.2 §4/§5/§7 standard top-level fields (P2).  Producer-private
# extensions must live under ``metadata``; anything else at the top level
# triggers an okf_conformance warning so new docs don't leak private keys.
_OKF_TOP_LEVEL_KEYS = frozenset({
    "type", "title", "description", "aliases",
    "status", "verified", "stale_after", "generated",
    "tags", "sources", "metadata",
})
# Legacy top-level extensions that may still appear on older pages.  They are
# producer-private under OKF §4/§5 and should be folded under ``metadata``
# (migrate_okf.py --fold-private does this).  They stay tolerated here — and
# line-based consumers (wiki_index note date, lint note_clusters, cache.py
# boost) keep reading them via the indented ``key: value`` rows — so folding
# remains backwards-compatible.
_OKF_LEGACY_TOP_LEVEL_KEYS = frozenset({
    "severity", "origin", "root_cause",
    "source_refs", "chunk_refs",
    "related_modules", "related_components", "source_ref",
    "summary", "keywords", "date",
})

# Regex patterns for markdown links
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]\(([^\)]+\.md)\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")
_SIMPLE_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _strip_code_blocks(content: str) -> str:
    """Return *content* with fenced and inline code spans removed.

    Markdown link patterns that appear *inside* code (e.g. a usage example
    `` `[text](x.md)` ``) must not be treated as real references by the
    linter, otherwise they produce false-positive broken-link errors.
    """
    # Replace fenced blocks with equivalent blank lines to preserve line numbering
    def _blank_fenced(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")
    stripped = re.sub(r"(?ms)^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)", _blank_fenced, content)
    # Drop inline code spans (`...`)
    stripped = re.sub(r"`[^`]*`", "", stripped)
    return stripped


def _build_anchor_map(output_dir: Path) -> Dict[str, str]:
    """Map lower-cased title / slug / aliases -> relative posix path.

    Used to resolve bare ``[[Name]]`` wikilinks to the file they point at,
    since the convention in this repo stores cross-references as
    ``[[Module Name]]`` rather than as explicit ``[[Name]](file.md)`` links.
    """
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    title_to_rel: Dict[str, str] = {}
    wiki_dir = output_dir / WIKI_DIR
    if not wiki_dir.is_dir():
        return title_to_rel
    for md_file in wiki_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel = md_file.relative_to(output_dir).as_posix()
        title_to_rel[md_file.stem.lower()] = rel
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        try:
            end = text.index("---", 3)
        except ValueError:
            continue
        for line in text[3:end].splitlines():
            s = line.strip()
            if s.startswith("title:"):
                t = s.split(":", 1)[1].strip().strip('"\'')
                if t:
                    title_to_rel[t.lower()] = rel
                    title_to_rel[t.lower().replace(" ", "-")] = rel
            elif s.startswith("aliases:"):
                raw = s.split(":", 1)[1].strip().strip("[]")
                for a in raw.split(","):
                    a = a.strip().strip('"\'')
                    if a:
                        title_to_rel[a.lower()] = rel
    return title_to_rel


def _collect_linked_targets(
    content: str,
    md_file: Path,
    output_dir: Path,
    anchor_map: Dict[str, str],
) -> Set[str]:
    """Return the set of relative paths that *content* links to.

    Recognises standard markdown links ``[text](file.md)``, wikilinks with an
    explicit target ``[[Name]](file.md)``, and bare wikilinks ``[[Name]]``
    (resolved via *anchor_map*).  The caller should pass already code-stripped
    *content* so links inside code spans are ignored.
    """
    targets: Set[str] = set()
    out_root = output_dir.resolve()
    md_root = md_file.parent

    for match in _MD_LINK_RE.finditer(content):
        ref = match.group(2).split("#")[0]
        if ref.startswith(("http://", "https://", "mailto:")) or not ref:
            continue
        try:
            resolved = (md_root / ref).resolve()
            targets.add(str(resolved.relative_to(out_root)))
        except ValueError:
            pass

    for match in _WIKILINK_RE.finditer(content):
        ref = match.group(2).split("#")[0]
        try:
            resolved = (md_root / ref).resolve()
            targets.add(str(resolved.relative_to(out_root)))
        except ValueError:
            pass

    for match in _SIMPLE_WIKILINK_RE.finditer(content):
        name = match.group(1).strip().lower().replace(".md", "")
        rel = anchor_map.get(name)
        if rel:
            targets.add(rel)

    return targets


def _get_output_dir(session: Optional[SessionState], arguments: Dict) -> Optional[Path]:
    """Resolve the output directory from session or arguments."""
    if session:
        return Path(session.output_dir).expanduser().resolve()
    output_dir = arguments.get("output_dir")
    if output_dir:
        p = Path(output_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    # Fallback: derive from repo_path
    rp = arguments.get("repo_path")
    if rp:
        p = Path(rp).expanduser().resolve()
        return p / "repowiki"
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

        # Ignore markdown links / wikilinks that appear inside code spans
        scan = _strip_code_blocks(content)
        for line_no, line in enumerate(scan.splitlines(), 1):
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

        scan = _strip_code_blocks(content)
        for line_no, line in enumerate(scan.splitlines(), 1):
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


def _check_isolated_components(
    components: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect completely isolated components (potential dead code).

    A component is isolated when it has zero dependencies AND nothing
    depends on it — it's disconnected from the rest of the codebase.
    """
    issues: List[Dict[str, Any]] = []
    if not components:
        return issues

    try:
        from codewiki.src.be.dependency_analyzer.topo_sort import (
            build_graph_from_components,
            find_isolated_nodes,
        )
        graph = build_graph_from_components(components)
        isolated = find_isolated_nodes(graph)

        if not isolated:
            return issues

        # Cap reporting at 20 components
        reported = isolated[:20]
        total = len(isolated)

        # Group by file for readability
        by_file: Dict[str, List[str]] = defaultdict(list)
        for comp_id in reported:
            meta = components.get(comp_id)
            fpath = getattr(meta, "relative_path", "") or getattr(meta, "file_path", "") or "unknown"
            name = getattr(meta, "name", comp_id) if meta else comp_id
            by_file[fpath].append(name)

        for fpath, names in sorted(by_file.items()):
            issues.append({
                "check": "isolated_components",
                "severity": "info",
                "message": (
                    f"{len(names)} isolated component(s) in {fpath}: "
                    f"{', '.join(names[:5])}{'...' if len(names) > 5 else ''}"
                ),
                "file": fpath,
                "components": [f"{fpath}::{n}" for n in names],
                "suggestion": (
                    "These components have no dependency relationships. "
                    "Verify they are not dead code, or document why they exist "
                    "(e.g. plugin entry points, scripts, deprecated code)."
                ),
            })

        if total > 20:
            issues.append({
                "check": "isolated_components",
                "severity": "info",
                "message": f"... and {total - 20} more isolated components (showing first 20)",
                "suggestion": "Run with component analysis to see the full list.",
            })

    except Exception as e:
        logger.warning("Isolated component detection skipped: %s", e)

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
    anchor_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Find wiki pages with no incoming links from other pages.

    Only scans files under wiki/ subdirectories. Directories like notes/,
    raw/, and .meta/ are raw material layers that by design don't need
    inbound wiki links, so they are excluded from the orphan check.
    """
    issues: List[Dict[str, Any]] = []
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    if anchor_map is None:
        anchor_map = _build_anchor_map(output_dir)

    # Only scan wiki/ subdirectories — notes/, raw/, .meta/ etc. are
    # raw material layers that don't require inbound wiki links.
    wiki_dir = output_dir / WIKI_DIR
    scan_root = wiki_dir if wiki_dir.is_dir() else output_dir

    # Collect all .md files and their relative paths
    all_pages: Dict[str, Path] = {}
    for md_file in scan_root.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel = str(md_file.relative_to(output_dir))
        all_pages[rel] = md_file

    if not all_pages:
        return issues

    # Build incoming link set — standard links, explicit wikilinks, and bare
    # [[Name]] wikilinks resolved via the anchor map.
    linked_targets: Set[str] = set()
    for md_file in all_pages.values():
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scan = _strip_code_blocks(content)
        linked_targets |= _collect_linked_targets(scan, md_file, output_dir, anchor_map)

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
    anchor_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Find wiki pages with no outgoing links to other wiki pages."""
    issues: List[Dict[str, Any]] = []
    from codewiki.src.config import WIKI_SYSTEM_FILES

    if anchor_map is None:
        anchor_map = _build_anchor_map(output_dir)

    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel_path = str(md_file.relative_to(output_dir))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        scan = _strip_code_blocks(content)
        targets = _collect_linked_targets(scan, md_file, output_dir, anchor_map)
        if not targets:
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

    missing: List[str] = []
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
                    missing.append(rel_path)
            except (ValueError, IndexError):
                pass

    if missing:
        issues.append({
            "check": "missing_aliases",
            "severity": "info",
            "message": (
                f"{len(missing)} page(s) lack 'aliases' in frontmatter; "
                "adding alternate names improves search discoverability"
            ),
            "count": len(missing),
            "files": missing,
            "suggestion": "Add 'aliases: [<alt names>]' to frontmatter when generating docs",
        })

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
            # Quick check: only parse frontmatter if relevant status appears
            if "superseded" not in content and "deprecated" not in content:
                continue
            # Check frontmatter for status: superseded (legacy) or deprecated (OKF v0.2)
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    fm_text = content[3:end]
                    status_m = re.search(
                        r"^status:\s*(superseded|deprecated)", fm_text, re.MULTILINE
                    )
                    if status_m:
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


def _check_overview_stale_lint(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Check if overview.md is stale (references modules that have changed).

    Reads the overview_stale flag from metadata.json and/or checks
    .meta/overview_refs.json against current module state.
    """
    issues: List[Dict[str, Any]] = []
    import json as _json
    from codewiki.src.config import meta_resolve

    # Check metadata.json for overview_stale flag
    meta_path = Path(meta_resolve(output_dir, "metadata.json"))
    overview_stale = False
    if meta_path.exists():
        try:
            metadata = _json.loads(meta_path.read_text(encoding="utf-8"))
            overview_stale = metadata.get("overview_stale", False)
        except (json.JSONDecodeError, OSError):
            pass

    if overview_stale:
        issues.append({
            "check": "overview_stale",
            "severity": "warning",
            "message": "overview.md references modules that have changed and may need updating",
            "file": "overview.md",
            "suggestion": "Review and update overview.md to reflect changes in referenced modules",
        })

    return issues


# Regex for business constraint assertions: lines containing (confidence: 0.XX)
_CONFIDENCE_RE = re.compile(r"\(confidence:\s*([\d.]+)\)")
_EVIDENCE_RE = re.compile(r">\s*Evidence:", re.IGNORECASE)
_CANDIDATE_RE = re.compile(r"\[candidate\]", re.IGNORECASE)


def _check_unsupported_claims(
    output_dir: Path,
    threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """Flag wiki pages where business assertions lack code evidence.

    Scans for lines with '(confidence: X.XX)' markers.  An assertion is
    considered 'supported' if it is followed (within 2 lines) by a
    '> Evidence:' line.  Assertions marked [candidate] are always
    unsupported.  If the unsupported ratio exceeds *threshold*, a warning
    is emitted for that file.
    """
    issues: List[Dict[str, Any]] = []
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    wiki_dir = output_dir / WIKI_DIR
    scan_dirs = [wiki_dir] if wiki_dir.is_dir() else [output_dir]

    for scan_dir in scan_dirs:
        for md_file in scan_dir.rglob("*.md"):
            if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
                continue
            try:
                lines = md_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            total_claims = 0
            unsupported = 0

            for i, line in enumerate(lines):
                if not _CONFIDENCE_RE.search(line):
                    continue
                total_claims += 1

                # [candidate] marks are always unsupported
                if _CANDIDATE_RE.search(line):
                    unsupported += 1
                    continue

                # Check next 2 lines for evidence
                has_evidence = False
                for j in range(i + 1, min(i + 3, len(lines))):
                    if _EVIDENCE_RE.search(lines[j]):
                        has_evidence = True
                        break
                if not has_evidence:
                    unsupported += 1

            if total_claims == 0:
                continue

            ratio = unsupported / total_claims
            if ratio > threshold:
                rel_path = str(md_file.relative_to(output_dir))
                issues.append({
                    "check": "unsupported_claims",
                    "severity": "warning",
                    "message": (
                        f"{unsupported}/{total_claims} business assertions lack code evidence "
                        f"({ratio:.0%} > {threshold:.0%} threshold)"
                    ),
                    "file": rel_path,
                    "suggestion": (
                        "Add '> Evidence: `<code quote>` — <reason>' lines after each assertion, "
                        "or mark unsupported assertions as [candidate]"
                    ),
                })

    return issues


# ---------------------------------------------------------------------------
#  Note lifecycle checks (staleness + clustering)
# ---------------------------------------------------------------------------

def _parse_note_frontmatter(note_path: Path) -> Optional[Dict[str, Any]]:
    """Parse a note's YAML frontmatter into a dict. Returns None on failure."""
    try:
        text = note_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end < 0:
        return None
    fm: Dict[str, Any] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        # Parse JSON arrays
        if value.startswith("["):
            try:
                fm[key] = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                fm[key] = value
        else:
            fm[key] = value.strip('"\'')
    return fm


def _check_stale_notes(
    output_dir: Path,
    stale_days: int = 90,
    retrieval_gap_days: int = 60,
) -> List[Dict[str, Any]]:
    """Flag confirmed notes that are old and haven't been retrieved recently.

    A note is considered stale when ALL of:
      - status == "confirmed"
      - note age > stale_days (default 90)
      - last retrieval hit > retrieval_gap_days ago (or never hit)

    This helps prevent knowledge rot: confirmed notes that nobody queries
    may be outdated or superseded by newer understanding.
    """
    import sqlite3
    from datetime import datetime, timedelta

    issues: List[Dict[str, Any]] = []

    from codewiki.src.config import NOTES_DIR
    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return issues

    # Load retrieval stats if available
    stats_db = output_dir / ".meta" / "retrieval_stats.db"
    retrieval_map: Dict[str, str] = {}  # file_path -> last_hit date string
    if stats_db.exists():
        try:
            conn = sqlite3.connect(str(stats_db))
            try:
                rows = conn.execute(
                    "SELECT file_path, last_hit FROM retrieval_stats"
                ).fetchall()
                for fp, lh in rows:
                    if lh:
                        retrieval_map[fp] = lh
            finally:
                conn.close()
        except Exception:
            pass

    today = datetime.now()
    stale_threshold = today - timedelta(days=stale_days)
    retrieval_threshold = today - timedelta(days=retrieval_gap_days)

    for note_file in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(note_file)
        if not fm:
            continue

        # Only check confirmed/stable notes (legacy + OKF v0.2 vocabulary)
        status = str(fm.get("status", "")).lower()
        if status not in ("confirmed", "stable"):
            continue

        # Parse note date
        date_str = fm.get("date", "")
        try:
            note_date = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        # Check age
        if note_date > stale_threshold:
            continue  # not old enough

        # Check retrieval recency
        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        # Also try with notes/ prefix variations
        last_hit_str = retrieval_map.get(rel_path) or retrieval_map.get(f"notes/{note_file.name}")
        recently_hit = False
        if last_hit_str:
            try:
                last_hit = datetime.strptime(last_hit_str, "%Y-%m-%d")
                if last_hit > retrieval_threshold:
                    recently_hit = True
            except (ValueError, TypeError):
                pass

        if recently_hit:
            continue  # still being actively retrieved

        age_days = (today - note_date).days
        title = fm.get("title", note_file.stem)
        note_type = fm.get("type", "general")

        issues.append({
            "check": "stale_notes",
            "severity": "warning",
            "message": (
                f"Confirmed note '{title}' ({note_type}) is {age_days} days old "
                f"and has not been retrieved in {retrieval_gap_days}+ days"
            ),
            "file": rel_path,
            "suggestion": (
                f"Review whether this {note_type} note is still accurate. "
                f"Use confirm_note to re-validate, reject_note to retire, "
                f"or update the content if the knowledge has evolved."
            ),
        })

    return issues


def _check_note_clusters(
    output_dir: Path,
    cluster_threshold: int = 3,
) -> List[Dict[str, Any]]:
    """Flag modules that have 3+ notes of the same type (consolidation candidates).

    When multiple notes of the same type accumulate under one module, they
    often contain overlapping or contradictory information that should be
    merged into a single authoritative note.
    """
    issues: List[Dict[str, Any]] = []

    from codewiki.src.config import NOTES_DIR
    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return issues

    # Group notes by (module, type)
    clusters: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)

    for note_file in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(note_file)
        if not fm:
            continue

        # Skip rejected/deprecated notes (legacy + OKF v0.2 vocabulary)
        if str(fm.get("status", "")).lower() in ("rejected", "deprecated"):
            continue

        note_type = fm.get("type", "general")
        modules = fm.get("related_modules", [])
        if isinstance(modules, str):
            modules = [modules] if modules else []
        if not modules:
            continue

        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        entry = {
            "file": rel_path,
            "title": fm.get("title", note_file.stem),
            "date": fm.get("date", ""),
            "status": fm.get("status", "candidate"),
        }

        for mod in modules:
            if isinstance(mod, str) and mod.strip():
                clusters[(mod.strip(), note_type)].append(entry)

    # Report clusters that exceed the threshold
    for (module, note_type), notes in sorted(clusters.items()):
        if len(notes) < cluster_threshold:
            continue

        titles = ", ".join(f"'{n['title']}'" for n in notes[:5])
        if len(notes) > 5:
            titles += f" (+{len(notes) - 5} more)"

        issues.append({
            "check": "note_clusters",
            "severity": "info",
            "message": (
                f"Module '{module}' has {len(notes)} {note_type} notes "
                f"that may benefit from consolidation: {titles}"
            ),
            "file": notes[0]["file"],
            "suggestion": (
                f"Use get_prompt('consolidate') for guidance on merging "
                f"these {len(notes)} {note_type} notes into a single "
                f"authoritative note for module '{module}'."
            ),
        })

    return issues


# ---------------------------------------------------------------------------
#  OKF v0.2 conformance (§11 / §12)
# ---------------------------------------------------------------------------

def _check_okf_conformance(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Audit the bundle against the OKF v0.2 specification.

    Checks (see okf/SPEC.md):
      - §11: every non-reserved .md file must have parseable frontmatter
        carrying a non-empty ``type`` field (error).
      - §5: ``status`` must use the draft/stable/deprecated vocabulary;
        legacy candidate/confirmed/rejected/superseded values get a
        warning suggesting ``scripts/migrate_okf.py``.
      - §5: ``verified`` must be a mapping or a list of mappings.
      - §5: ``stale_after`` dates in the past mark potentially rotten
        knowledge (warning).
      - §12: wiki/index.md should declare ``okf_version`` (warning).

    Reserved files (index.md, log.md) are exempt from the type rule.
    """
    from datetime import date

    from codewiki.src.config import (
        INDEX_FILENAME,
        META_DIR,
        WIKI_DIR,
    )

    issues: List[Dict[str, Any]] = []

    # Collect candidate .md files across the bundle.  P3: the original scan
    # only covered wiki/, notes/ and raw/sources/, silently missing root-level
    # runbooks such as team-memory-hook.md.  Scan the whole bundle and skip
    # scratch/staging directories (.meta/, .trash/, .hook-debug/) instead.
    _scratch_dirs = {META_DIR, ".trash", ".hook-debug"}
    targets: List[Path] = []
    for _md in output_dir.rglob("*.md"):
        if any(_part in _scratch_dirs for _part in _md.parts):
            continue
        targets.append(_md)

    today_str = date.today().isoformat()

    for md_file in sorted(targets):
        # §4/§11: index.md and log.md are reserved system files
        if md_file.name in ("index.md", "log.md"):
            continue

        rel_path = md_file.relative_to(output_dir).as_posix()
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not text.startswith("---") or text.find("---", 3) < 0:
            issues.append({
                "check": "okf_conformance",
                "severity": "error",
                "message": "Missing YAML frontmatter (OKF v0.2 §11 requires a 'type' field)",
                "file": rel_path,
                "suggestion": (
                    "Run `python scripts/migrate_okf.py <wiki-dir>` to backfill "
                    "OKF frontmatter, or regenerate the page."
                ),
            })
            continue

        # Prefer real YAML parsing (needed for nested generated/verified/sources),
        # but fall back to the permissive line parser (§11: consumers must be
        # permissive) before declaring the file non-conformant.
        fm: Optional[Dict[str, Any]] = None
        try:
            import yaml
            end = text.find("---", 3)
            data = yaml.safe_load(text[3:end])
            if isinstance(data, dict):
                fm = data
        except Exception:
            fm = None
        if fm is None:
            fm = _parse_note_frontmatter(md_file)
            if not fm:
                issues.append({
                    "check": "okf_conformance",
                    "severity": "error",
                    "message": "Frontmatter is not parseable YAML (OKF v0.2 §11)",
                    "file": rel_path,
                    "suggestion": "Fix the YAML frontmatter block manually or regenerate the page.",
                })
                continue

        # §4: type is the only required field
        page_type = fm.get("type")
        if not page_type or not str(page_type).strip():
            issues.append({
                "check": "okf_conformance",
                "severity": "error",
                "message": "Missing required 'type' field in frontmatter (OKF v0.2 §4)",
                "file": rel_path,
                "suggestion": (
                    "Run `python scripts/migrate_okf.py <wiki-dir>` to backfill "
                    "the type field, or regenerate the page."
                ),
            })

        # P2: producer-private keys must not leak at the top level.  OKF §4/§5
        # standard fields plus the backward-compat legacy set are allowed; any
        # other key should be folded under `metadata:`.
        _unknown_top = sorted(
            set(fm) - _OKF_TOP_LEVEL_KEYS - _OKF_LEGACY_TOP_LEVEL_KEYS
        )
        if _unknown_top:
            issues.append({
                "check": "okf_conformance",
                "severity": "warning",
                "message": (
                    "Non-OKF top-level frontmatter key(s): "
                    + ", ".join(_unknown_top)
                    + " (OKF v0.2 §4/§5 — producer-private fields belong under `metadata:`)"
                ),
                "file": rel_path,
                "suggestion": (
                    "Fold these keys under a `metadata:` node, or regenerate "
                    "the page with the OKF frontmatter helper."
                ),
            })

        # §5 status vocabulary
        status_raw = fm.get("status")
        status = str(status_raw).strip().lower() if status_raw else ""
        if status and status not in _OKF_STATUSES:
            mapped = _LEGACY_STATUS_MAP.get(status)
            if mapped:
                issues.append({
                    "check": "okf_conformance",
                    "severity": "warning",
                    "message": (
                        f"Legacy status '{status}' — OKF v0.2 uses '{mapped}'"
                    ),
                    "file": rel_path,
                    "suggestion": (
                        "Run `python scripts/migrate_okf.py <wiki-dir>` to migrate "
                        "legacy lifecycle statuses to the OKF v0.2 vocabulary."
                    ),
                })
            else:
                issues.append({
                    "check": "okf_conformance",
                    "severity": "warning",
                    "message": (
                        f"Unknown status '{status}' — expected one of "
                        f"draft/stable/deprecated (OKF v0.2 §5)"
                    ),
                    "file": rel_path,
                    "suggestion": "Set status to draft, stable, or deprecated.",
                })

        # §5 verified: mapping or list of mappings ({by, at, note?})
        verified = fm.get("verified")
        if verified is not None:
            valid = isinstance(verified, dict) or (
                isinstance(verified, list)
                and all(isinstance(v, dict) for v in verified)
            )
            if not valid:
                issues.append({
                    "check": "okf_conformance",
                    "severity": "warning",
                    "message": "'verified' must be a mapping or a list of {by, at} mappings (OKF v0.2 §5)",
                    "file": rel_path,
                    "suggestion": "Use confirm_note to record verification events correctly.",
                })

        # §5 stale_after expiry
        stale_after = fm.get("stale_after")
        if stale_after:
            sa = str(stale_after)[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", sa) and sa < today_str:
                issues.append({
                    "check": "okf_conformance",
                    "severity": "warning",
                    "message": f"stale_after ({sa}) has passed — knowledge may be outdated",
                    "file": rel_path,
                    "suggestion": (
                        "Verify the content is still accurate, then regenerate or "
                        "update the page to renew stale_after."
                    ),
                })

    # §12: wiki/index.md should declare okf_version
    index_path = output_dir / WIKI_DIR / INDEX_FILENAME
    if index_path.exists():
        try:
            idx_text = index_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            idx_text = ""
        has_version = False
        if idx_text.startswith("---"):
            end = idx_text.find("---", 3)
            if end > 0 and re.search(r"^okf_version:", idx_text[3:end], re.MULTILINE):
                has_version = True
        if not has_version:
            issues.append({
                "check": "okf_conformance",
                "severity": "warning",
                "message": "wiki/index.md does not declare okf_version (OKF v0.2 §12)",
                "file": "wiki/index.md",
                "suggestion": (
                    "Regenerate the index, or run `python scripts/migrate_okf.py "
                    "<wiki-dir>` to add okf_version."
                ),
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
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)

    checks = arguments.get("checks", ["all"])
    if isinstance(checks, str):
        checks = [checks]
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

    if "isolated_components" in checks:
        all_issues.extend(_check_isolated_components(components))

    if "coverage" in checks:
        all_issues.extend(_check_coverage(components, module_tree, output_dir))

    # LLM Wiki checks (build the anchor map once and reuse it)
    _anchor_map = None
    if "orphan_pages" in checks and output_dir:
        _anchor_map = _build_anchor_map(output_dir)
        all_issues.extend(_check_orphan_pages(output_dir, _anchor_map))

    if "no_outlinks" in checks and output_dir:
        if _anchor_map is None:
            _anchor_map = _build_anchor_map(output_dir)
        all_issues.extend(_check_no_outlinks(output_dir, _anchor_map))

    if "missing_aliases" in checks and output_dir:
        all_issues.extend(_check_missing_aliases(output_dir))

    if "stale_sources" in checks and output_dir:
        all_issues.extend(_check_stale_sources(output_dir))

    if "superseded_pages" in checks and output_dir:
        all_issues.extend(_check_superseded_pages(output_dir))

    if "overview_stale" in checks and output_dir:
        all_issues.extend(_check_overview_stale_lint(output_dir))

    if "unsupported_claims" in checks and output_dir:
        all_issues.extend(_check_unsupported_claims(output_dir))

    if "stale_notes" in checks and output_dir:
        all_issues.extend(_check_stale_notes(output_dir))

    if "note_clusters" in checks and output_dir:
        all_issues.extend(_check_note_clusters(output_dir))

    if "okf_conformance" in checks and output_dir:
        all_issues.extend(_check_okf_conformance(output_dir))

    # Deduplicate: if a link is already reported as stale_refs, don't also
    # report it as broken_links (same file + line = same underlying problem).
    stale_locations = {
        (issue.get("file"), issue.get("line"))
        for issue in all_issues
        if issue.get("check") == "stale_refs"
    }
    all_issues = [
        issue for issue in all_issues
        if not (
            issue.get("check") == "broken_links"
            and (issue.get("file"), issue.get("line")) in stale_locations
        )
    ]

    # Ensure every issue has a "page" field populated from "file"
    for issue in all_issues:
        if "page" not in issue or issue["page"] is None:
            issue["page"] = issue.get("file", "")

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
