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
    "overview_stale",
    "unsupported_claims",
    "isolated_components",
    "stale_notes",
    # P0 (openwiki 借鉴): content-hashed repo:// code evidence drift detection
    "stale_evidence",
    "note_clusters",
    "okf_conformance",
    # P2 (team-memory fusion): L2 scene block hygiene
    "scenario_capacity",
    "scenario_orphan",
    # P1 B-line: hot-but-never-adopted notes (usage utility dimension)
    "low_adoption",
    # Centralized-layout discipline (ticket 09)
    "layout_violations",
    # Team-layout Phase 1 (D1): rebuildable derived files must not be tracked
    "team_layout_gitignore",
}

# 归档/调试暂存目录不参与 wiki 一致性审计：.trash/（deprecated 笔记归档区，
# 历史快照的相对链接随迁移自然失效，不应误报）与 .hook-debug/（抓包调试输出）。
_SCRATCH_DIR_NAMES = {".trash", ".hook-debug", ".meta"}

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
_OKF_TOP_LEVEL_KEYS = frozenset(
    {
        "type",
        "title",
        "description",
        "aliases",
        "status",
        "verified",
        "stale_after",
        "generated",
        "tags",
        "sources",
        "metadata",
        # Team-layout Phase 3 (D16): author provenance, write-only — the
        # data foundation for multi-user governance (no edit-gating).
        "author",
    }
)
# Legacy top-level extensions that may still appear on older pages.  They are
# producer-private under OKF §4/§5 and should be folded under ``metadata``
# (migrate_okf.py --fold-private does this).  They stay tolerated here — and
# line-based consumers (wiki_index note date, lint note_clusters, cache.py
# boost) keep reading them via the indented ``key: value`` rows — so folding
# remains backwards-compatible.
_OKF_LEGACY_TOP_LEVEL_KEYS = frozenset(
    {
        "severity",
        "origin",
        "root_cause",
        "source_refs",
        "chunk_refs",
        "related_modules",
        "related_components",
        "source_ref",
        "summary",
        "keywords",
        "date",
        "reject_reason",  # knowledge_loop reject() 写入的拒绝原因（migrate_okf --fold-private 会折叠进 metadata）
    }
)

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
    # Drop inline code spans (`...`).  `[^`\n]*` is single-line scoped: a lone
    # unmatched backtick in prose (e.g. a truncated code ref) must never swallow
    # the rest of the file across newlines, which would silently drop real
    # links and produce false orphan/broken-link reports.
    stripped = re.sub(r"`[^`\n]*`", "", stripped)
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
                t = s.split(":", 1)[1].strip().strip("\"'")
                if t:
                    title_to_rel[t.lower()] = rel
                    title_to_rel[t.lower().replace(" ", "-")] = rel
            elif s.startswith("aliases:"):
                raw = s.split(":", 1)[1].strip().strip("[]")
                for a in raw.split(","):
                    a = a.strip().strip("\"'")
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
    # Fallback: derive from repo_path (layout-aware, ticket 09: centralized
    # members lint the workspace knowledge base).
    rp = arguments.get("repo_path")
    if rp:
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        return default_output_dir(Path(rp).expanduser().resolve())
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

    _get_all_module_names(module_tree)
    # Recursively collect all .md files for valid_files set
    {f.name for f in output_dir.rglob("*.md")}

    for md_file in output_dir.rglob("*.md"):
        if _SCRATCH_DIR_NAMES.intersection(md_file.parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # raw/sources/ 是外部同步的源文档层，其内部相对链接指向源仓库
        # 的其他文件（CHANGELOG.md、docs/*.md 等），这些目标文件不会同步进
        # repowiki，检查 stale refs 会把它们全部误报。源文档层的链接语义
        # 不属于 wiki 文档一致性审计范围，整层跳过。
        if "sources" in md_file.parts and "raw" in md_file.parts:
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
                    issues.append(
                        {
                            "check": "stale_refs",
                            "severity": "error",
                            "message": f"Reference to non-existent file '{ref_file}' (module '{ref_name}')",
                            "file": str(md_file.relative_to(output_dir)),
                            "line": line_no,
                            "suggestion": f"Remove or update the reference to '{ref_name}'",
                        }
                    )

            # Check simple [text](file.md) patterns (skip http links)
            for match in _MD_LINK_RE.finditer(line):
                match.group(1)
                ref_file = match.group(2)
                if ref_file.startswith(("http://", "https://")):
                    continue
                # Resolve relative to source file's directory
                resolved = (md_file.parent / ref_file).resolve()
                if not resolved.exists():
                    issues.append(
                        {
                            "check": "stale_refs",
                            "severity": "error",
                            "message": f"Broken link to '{ref_file}'",
                            "file": str(md_file.relative_to(output_dir)),
                            "line": line_no,
                            "suggestion": "Update the link target or remove the reference",
                        }
                    )

    return issues


def _check_broken_links(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Find broken markdown links within the documentation directory."""
    issues: List[Dict[str, Any]] = []

    for md_file in output_dir.rglob("*.md"):
        if _SCRATCH_DIR_NAMES.intersection(md_file.parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # raw/sources/ 是外部同步的源文档层，其内部相对链接指向源仓库的
        # 其他文件（CHANGELOG.md、docs/*.md 等），这些目标文件不会同步进
        # repowiki，检查 broken links 会把它们全部误报。与 _check_stale_refs
        # 保持一致，整层跳过。
        if "sources" in md_file.parts and "raw" in md_file.parts:
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
                    issues.append(
                        {
                            "check": "broken_links",
                            "severity": "error",
                            "message": f"Link target '{ref_file}' does not exist",
                            "file": str(md_file.relative_to(output_dir)),
                            "line": line_no,
                            "suggestion": "Fix the link path or create the target file",
                        }
                    )

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
            issues.append(
                {
                    "check": "undocumented",
                    "severity": "warning",
                    "message": (
                        f"High-impact component '{comp_id}' "
                        f"({count} dependents) has no documentation coverage"
                    ),
                    "component_id": comp_id,
                    "depended_by_count": count,
                    "suggestion": "Add this component to a module or create dedicated documentation",
                }
            )

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
            issues.append(
                {
                    "check": "cycles",
                    "severity": "info",
                    "message": f"Circular dependency detected: {' → '.join(cycle[:5])}{'...' if len(cycle) > 5 else ''}",
                    "components": cycle,
                    "suggestion": "Consider refactoring to break the cycle (e.g. via interface or event pattern)",
                }
            )
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
            fpath = (
                getattr(meta, "relative_path", "") or getattr(meta, "file_path", "") or "unknown"
            )
            name = getattr(meta, "name", comp_id) if meta else comp_id
            by_file[fpath].append(name)

        for fpath, names in sorted(by_file.items()):
            issues.append(
                {
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
                }
            )

        if total > 20:
            issues.append(
                {
                    "check": "isolated_components",
                    "severity": "info",
                    "message": f"... and {total - 20} more isolated components (showing first 20)",
                    "suggestion": "Run with component analysis to see the full list.",
                }
            )

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

    issues.append(
        {
            "check": "coverage",
            "severity": "info",
            "message": f"Documentation coverage: {covered}/{total} components ({pct:.1f}%)",
            "covered": covered,
            "total": total,
            "percentage": round(pct, 1),
            "suggestion": ("Coverage is below 50%" if pct < 50 else "Good coverage"),
        }
    )

    # Per-module coverage
    def _walk(tree: dict):
        for name, info in tree.items():
            mod_comps = set(info.get("components", []))
            if mod_comps:
                mod_covered = len(mod_comps & set(components.keys()))
                mod_total = len(mod_comps)
                mod_pct = (mod_covered / mod_total * 100) if mod_total > 0 else 0
                if mod_pct < 50:
                    issues.append(
                        {
                            "check": "coverage",
                            "severity": "info",
                            "message": f"Module '{name}': {mod_covered}/{mod_total} components ({mod_pct:.0f}%)",
                            "module": name,
                            "covered": mod_covered,
                            "total": mod_total,
                            "percentage": round(mod_pct, 1),
                            "suggestion": "Consider adding more components to this module's documentation",
                        }
                    )
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

    # Collect all .md files and their relative paths.  System files such as
    # index.md act as the entry hub — they ARE a valid source of incoming
    # links, so they must be scanned for links; they are only excluded from
    # the set of pages that need to RECEIVE links.
    link_sources: List[Tuple[str, Path]] = []
    all_pages: Dict[str, Path] = {}
    for md_file in scan_root.rglob("*.md"):
        if not md_file.is_file():
            continue
        rel = str(md_file.relative_to(output_dir))
        link_sources.append((rel, md_file))
        if md_file.name not in WIKI_SYSTEM_FILES:
            all_pages[rel] = md_file

    if not all_pages:
        return issues

    # Build incoming link set — standard links, explicit wikilinks, and bare
    # [[Name]] wikilinks resolved via the anchor map.  Scan ALL files including
    # system files (index.md links count as incoming links).
    linked_targets: Set[str] = set()
    for _rel, md_file in link_sources:
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scan = _strip_code_blocks(content)
        linked_targets |= _collect_linked_targets(scan, md_file, output_dir, anchor_map)

    # Find pages with no incoming links
    for rel_path, md_file in all_pages.items():
        if rel_path not in linked_targets:
            issues.append(
                {
                    "check": "orphan_pages",
                    "severity": "warning",
                    "message": "Page has no incoming links",
                    "file": rel_path,
                    "suggestion": "Add cross-references from related pages",
                }
            )

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
        if _SCRATCH_DIR_NAMES.intersection(md_file.parts):
            continue
        if not md_file.is_file() or md_file.name in WIKI_SYSTEM_FILES:
            continue
        rel_path = str(md_file.relative_to(output_dir))
        # conversations/ 蒸馏归档层、tasks/ 任务记忆层、raw/ 暂存区（待蒸馏对话
        # 与 sources 外部同步文档）是系统生成/同步层：归档与暂存文件无需（也不应）
        # 向 wiki 页面出链，豁免 no_outlinks。
        if any(k in md_file.parts for k in ("conversations", "tasks", "raw")):
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        scan = _strip_code_blocks(content)
        targets = _collect_linked_targets(scan, md_file, output_dir, anchor_map)
        if not targets:
            issues.append(
                {
                    "check": "no_outlinks",
                    "severity": "info",
                    "message": "Page has no outgoing links to other wiki pages",
                    "file": rel_path,
                    "suggestion": "Add cross-references to related pages for better navigation",
                }
            )

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
                has_aliases = any(line.strip().startswith("aliases:") for line in fm.splitlines())
                if not has_aliases:
                    missing.append(rel_path)
            except (ValueError, IndexError):
                pass

    if missing:
        issues.append(
            {
                "check": "missing_aliases",
                "severity": "info",
                "message": (
                    f"{len(missing)} page(s) lack 'aliases' in frontmatter; "
                    "adding alternate names improves search discoverability"
                ),
                "count": len(missing),
                "files": missing,
                "suggestion": "Add 'aliases: [<alt names>]' to frontmatter when generating docs",
            }
        )

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
                name
                for name, info in sources.items()
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
                    issues.append(
                        {
                            "check": "stale_sources",
                            "severity": "warning",
                            "message": f"References retracted source '{src_name}'",
                            "file": rel_path,
                            "suggestion": f"Update or remove the reference to '{src_name}'",
                        }
                    )

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
                        m = re.search(
                            r"^superseded_by:\s*[\"']?(.+?)[\"']?\s*$", fm_text, re.MULTILINE
                        )
                        if m:
                            superseded_by = m.group(1)
                        msg = "Page marked as superseded"
                        if superseded_by:
                            msg += f" (replaced by: {superseded_by})"
                        issues.append(
                            {
                                "check": "superseded_pages",
                                "severity": "info",
                                "message": msg,
                                "file": rel_path,
                                "suggestion": "Consider archiving or removing this page"
                                + (f"; see '{superseded_by}'" if superseded_by else ""),
                            }
                        )

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
        issues.append(
            {
                "check": "overview_stale",
                "severity": "warning",
                "message": "overview.md references modules that have changed and may need updating",
                "file": "overview.md",
                "suggestion": "Review and update overview.md to reflect changes in referenced modules",
            }
        )

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
                issues.append(
                    {
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
                    }
                )

    return issues


def _check_stale_evidence(output_dir: Path) -> List[Dict[str, Any]]:
    """Flag pages whose ``repo://`` code evidence no longer matches source.

    Reads each page's ``sources`` list for entries carrying a ``content_hash``
    (stamped by ``stamp_evidence``), re-reads the referenced region, and reports
    ``stale`` (code drifted) or ``missing`` (file gone) entries.  Evidence
    drives review only — this check never rewrites content.
    """
    from codewiki.src.evidence import verify_entry

    repo_root = output_dir.parent
    issues: List[Dict[str, Any]] = []

    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file():
            continue
        parts = set(md_file.relative_to(output_dir).parts)
        if parts & _SCRATCH_DIR_NAMES or "raw" in parts:
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.startswith("---"):
            continue
        end = content.find("---", 3)
        if end < 0:
            continue
        try:
            import yaml

            data = yaml.safe_load(content[3:end]) or {}
        except Exception:  # noqa: BLE001 - malformed FM is other checks' concern
            continue
        if not isinstance(data, dict):
            continue
        sources = data.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        if not isinstance(sources, list):
            continue

        rel_path = str(md_file.relative_to(output_dir)).replace("\\", "/")
        for entry in sources:
            if not isinstance(entry, dict) or "content_hash" not in entry:
                continue
            status = verify_entry(entry, repo_root)
            if status == "ok":
                continue
            resource = str(entry.get("resource", "<unknown>"))
            if status == "stale":
                message = f"code evidence drifted: {resource}"
                suggestion = (
                    "Source changed since this page was grounded. Re-verify the "
                    "claim, then re-stamp via stamp_evidence or edit_doc_file."
                )
            elif status == "missing":
                message = f"evidence file disappeared: {resource}"
                suggestion = (
                    "Referenced source no longer exists under the repo root. "
                    "Re-check the page and re-stamp or remove the entry."
                )
            else:
                message = f"unresolvable evidence resource: {resource}"
                suggestion = "Malformed repo:// resource; re-stamp with a valid URI."
            issues.append(
                {
                    "check": "stale_evidence",
                    "severity": "warning",
                    "message": message,
                    "file": rel_path,
                    "suggestion": suggestion,
                }
            )

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
            fm[key] = value.strip("\"'")
    return fm


def _check_stale_notes(
    output_dir: Path,
    stale_days: Optional[int] = None,
    retrieval_gap_days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flag stable/confirmed notes whose re-verification deadline has passed.

    新鲜度机制专项 (docs/新鲜度机制设计方案.md).  Judgment basis is the
    frontmatter ``stale_after`` rolling review deadline (renewed by
    confirm_note) — NOT the creation date.  The legacy implementation read
    ``metadata.date`` with a flat age threshold, so confirming a note never
    affected its staleness (stale_after was write-only).

    Judgment cascade per note (v2, via ``evaluate_note_freshness``):
      - due date = ``stale_after``; fallback when absent =
        ``metadata.date`` + the note's type window (legacy behaviour);
      - due date passed → warning「复核期已过」, unless the note was
        retrieved within ``retrieval_defer_days`` → deferred (activity
        exemption preserved);
      - otherwise fresh.

    Config precedence: explicit parameters > schema ``conventions.freshness``
    > hardcoded defaults (90/60) — dispatch passes no parameters, so bundles
    with a freshness block now actually get their configured windows.
    """
    from datetime import datetime

    issues: List[Dict[str, Any]] = []

    from codewiki.src.config import NOTES_DIR

    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return issues

    # Freshness config from schema.yaml (fallback chain handled inside).
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
    except Exception:
        schema = {}
    try:
        from codewiki.mcp.tools.knowledge_loop import (
            evaluate_note_freshness,
            load_freshness_config,
        )
    except Exception:
        return issues
    cfg = load_freshness_config(schema)
    if stale_days is not None:
        cfg = {**cfg, "default_window_days": int(stale_days)}
    if retrieval_gap_days is not None:
        cfg = {**cfg, "retrieval_defer_days": int(retrieval_gap_days)}

    # Telemetry usage aggregate (T2) if available (activity exemption source).
    # U2 复核联动: hit_count is also surfaced in the message and drives the
    # review-priority ordering (most overdue + least recently retrieved first).
    retrieval_map: Dict[str, str] = {}  # file_path -> last_hit date string
    hit_count_map: Dict[str, int] = {}  # file_path -> hit_count (U2)
    try:
        from codewiki.mcp.tools import telemetry

        for fp, entry in telemetry.aggregate_usage(output_dir).items():
            hit_count_map[str(fp)] = int(entry.get("hits", 0) or 0)
            lh = entry.get("last_hit")
            if lh:
                retrieval_map[str(fp)] = str(lh)
    except Exception:
        pass

    today = datetime.now()
    # (overdue_days desc, last_hit asc, issue) — populated in the loop below.
    ranked: List[Tuple[int, str, Dict[str, Any]]] = []

    for note_file in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(note_file)
        if not fm:
            continue

        # Only check confirmed/stable notes (legacy + OKF v0.2 vocabulary)
        status = str(fm.get("status", "")).lower()
        if status not in ("confirmed", "stable"):
            continue

        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        last_hit_str = retrieval_map.get(rel_path) or retrieval_map.get(f"notes/{note_file.name}")

        verdict = evaluate_note_freshness(fm, cfg, today=today, last_hit=last_hit_str)
        if verdict["state"] != "due":
            continue

        due_date = verdict["due_date"] or "?"
        try:
            overdue_days = (today - datetime.strptime(due_date, "%Y-%m-%d")).days
        except (ValueError, TypeError):
            overdue_days = 0
        title = fm.get("title", note_file.stem)
        note_type = fm.get("type", "general")
        hit_count = hit_count_map.get(rel_path, hit_count_map.get(f"notes/{note_file.name}", 0))

        issue = {
            "check": "stale_notes",
            "severity": "warning",
            "message": (
                f"Note '{title}' ({note_type}) passed its review deadline "
                f"({due_date}) {overdue_days} day(s) ago and has not been "
                f"retrieved in {cfg['retrieval_defer_days']}+ days "
                f"(retrieved {hit_count} times total)"
            ),
            "file": rel_path,
            "suggestion": (
                f"超过 {overdue_days} 天未验证。确认仍然准确用 "
                f'confirm_note(note_file="{rel_path}") 续期'
                f"（将按类型窗口刷新 stale_after），已过时用 reject_note 退役。"
            ),
        }
        # U2: never-retrieved notes sort before any retrieved date ("").
        ranked.append((overdue_days, last_hit_str or "", issue))

    # U2 复核联动: review priority — most overdue first, then least recently
    # retrieved ("超期最久且最没人查"的先复核). Judgment above is unchanged.
    ranked.sort(key=lambda x: (-x[0], x[1]))
    issues.extend(issue for _od, _lh, issue in ranked)
    return issues


def _check_low_adoption(
    output_dir: Path,
    min_hits: Optional[int] = None,
    max_adopted: Optional[int] = None,
    recent_days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flag stable notes that are recalled often but never adopted.

    P1 B-line (docs/知识飞轮增强设计方案-P1三项.md §3).  This is the
    *utility* dimension of note quality: ``hit_count`` measures exposure,
    ``adopted_count`` (``adopted`` telemetry events written by
    capture_conversation when the agent declares the docs it actually
    used) measures usefulness.  A note that keeps getting recalled and
    never gets adopted is likely *relevant but not actionable*.

    Trigger (all must hold, per stable/confirmed note):
      - hit_count >= min_hits (default 5, from the telemetry aggregate);
      - adopted_count <= max_adopted (default 0 — never adopted);
      - last_hit within recent_days (default 60) — "was hot, now dead"
        belongs to stale_notes instead.

    Cold-start guard (critical): when the bundle has zero adopted events
    anywhere, the check silently
    returns no issues — right after the A-line ships nobody has declared
    anything yet, and flagging every hot note would be pure noise.

    Config precedence: explicit parameters > schema ``conventions.
    usage_ranking.low_adoption`` > hardcoded defaults (5 / 0 / 60) —
    dispatch passes no parameters, same posture as _check_stale_notes.
    """
    from datetime import datetime, timedelta

    issues: List[Dict[str, Any]] = []

    # Config from schema.yaml (fallback chain handled below).
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
    except Exception:
        schema = {}
    cfg: Dict[str, Any] = {}
    if isinstance(schema, dict):
        usage = schema.get("conventions", {}).get("usage_ranking")
        if isinstance(usage, dict) and isinstance(usage.get("low_adoption"), dict):
            cfg = usage["low_adoption"]

    def _param(name: str, default: int, override: Optional[int]) -> int:
        if override is not None:
            return int(override)
        try:
            return int(cfg.get(name, default))
        except (TypeError, ValueError):
            return default

    min_hits = _param("min_hits", 5, min_hits)
    max_adopted = _param("max_adopted", 0, max_adopted)
    recent_days = _param("recent_days", 60, recent_days)

    # Cold-start guard: no adopted events anywhere in the bundle → the
    # adoption signal is not in use yet, skip.
    from codewiki.mcp.tools.adoption import load_adoption_counts

    adoption_counts = load_adoption_counts(output_dir)
    if not adoption_counts:
        return issues

    from codewiki.src.config import NOTES_DIR

    notes_dir = output_dir / NOTES_DIR
    if not notes_dir.is_dir():
        return issues

    # Usage signals from the telemetry aggregate (T2; same source
    # stale_notes uses — one call carries hit_count / last_hit / adopted).
    try:
        from codewiki.mcp.tools import telemetry

        usage_agg = telemetry.aggregate_usage(output_dir)
    except Exception:
        return issues
    if not usage_agg:
        return issues
    hit_map: Dict[str, Tuple[int, str]] = {}  # file_path -> (hit_count, last_hit)
    for fp, entry in usage_agg.items():
        hit_map[str(fp).replace("\\", "/")] = (
            int(entry.get("hits", 0) or 0),
            str(entry.get("last_hit") or ""),
        )

    cutoff = datetime.now() - timedelta(days=recent_days)

    for note_file in sorted(notes_dir.glob("*.md")):
        fm = _parse_note_frontmatter(note_file)
        if not fm:
            continue

        # Only stable/confirmed notes are judged (legacy + OKF v0.2 vocabulary)
        status = str(fm.get("status", "")).lower()
        if status not in ("stable", "confirmed"):
            continue

        rel_path = str(note_file.relative_to(output_dir)).replace("\\", "/")
        alt_key = f"notes/{note_file.name}"
        entry = hit_map.get(rel_path) or hit_map.get(alt_key)
        if not entry:
            continue
        hit_count, last_hit = entry

        if hit_count < min_hits:
            continue
        # Recency: last_hit must be inside the window, otherwise the note
        # "was hot but is dead now" — that case belongs to stale_notes.
        try:
            last_hit_dt = datetime.fromisoformat(last_hit[:10])
        except ValueError:
            continue  # no / unparseable last_hit → not verifiably recent
        if last_hit_dt < cutoff:
            continue

        adopted = int(adoption_counts.get(rel_path, adoption_counts.get(alt_key, 0)))
        if adopted > max_adopted:
            continue

        title = fm.get("title", note_file.stem)
        issues.append(
            {
                "check": "low_adoption",
                "severity": "warning",
                "message": (
                    f"Note '{title}' was recalled {hit_count} times recently "
                    f"but adopted {adopted} time(s) — content is likely relevant "
                    f"but not actionable enough"
                ),
                "file": rel_path,
                "suggestion": (
                    "高频召回但零采纳：内容相关但可能不够 actionable。建议重写为更"
                    "可执行的形式（补充具体步骤/命令/预期结果），可用 "
                    "distill_conversation 产出草稿后 confirm_note，或用 "
                    f"edit_doc_file 直接更新 {rel_path}。"
                ),
            }
        )

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

        issues.append(
            {
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
            }
        )

    return issues


# ---------------------------------------------------------------------------
#  P2: L2 scene block hygiene (team-memory fusion 设计方案 §4.3.4)
# ---------------------------------------------------------------------------


def _check_scenario_capacity(
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Error/warning when live scene blocks reach or exceed the capacity cap.

    The consolidation protocol (UPDATE > MERGE > CREATE with graded warnings)
    exists precisely to keep the scenario set bounded; lint backstops it in
    case a submit slipped through or files were written outside the tool.
    """
    issues: List[Dict[str, Any]] = []
    try:
        from codewiki.mcp.tools.note_consolidation import _scan_scenarios
        from codewiki.mcp.tools.aggregation_state import read_config

        live = _scan_scenarios(output_dir)
        max_scenes = read_config(output_dir)["max_scenarios"]
    except Exception:
        return issues
    if not live:
        return issues
    if len(live) > max_scenes:
        issues.append(
            {
                "check": "scenario_capacity",
                "severity": "error",
                "message": (
                    f"Scenario blocks exceed the cap: {len(live)}/{max_scenes}. "
                    "MERGE similar scenes (mark losers [DELETED]) before adding more."
                ),
                "file": "wiki/scenarios/",
                "suggestion": (
                    "Run consolidate_notes(mode='prepare') and follow the RED "
                    "capacity protocol: merge first, then re-submit."
                ),
            }
        )
    elif len(live) == max_scenes:
        issues.append(
            {
                "check": "scenario_capacity",
                "severity": "warning",
                "message": (
                    f"Scenario blocks at capacity: {len(live)}/{max_scenes}. "
                    "Only UPDATE is allowed until a merge frees a slot."
                ),
                "file": "wiki/scenarios/",
                "suggestion": "Prefer UPDATE/MERGE on the next consolidate_notes run.",
            }
        )
    return issues


def _check_scenario_orphan(
    output_dir: Path,
    retrieval_gap_days: int = 90,
) -> List[Dict[str, Any]]:
    """Info-level flag for scene blocks with no provenance and no retrieval use.

    A scenario is an orphan when it has no metadata.source_notes (never linked
    to the notes it was consolidated from) AND has not been retrieved for
    retrieval_gap_days (or ever). Such blocks may be redundant or outdated.
    """
    from datetime import datetime, timedelta

    issues: List[Dict[str, Any]] = []
    try:
        from codewiki.mcp.tools.note_consolidation import (
            _scan_scenarios,
            _read_frontmatter,
        )
    except Exception:
        return issues

    scenarios = _scan_scenarios(output_dir)
    if not scenarios:
        return issues

    # Telemetry usage aggregate (T2; same source stale_notes uses)
    retrieval_map: Dict[str, str] = {}
    try:
        from codewiki.mcp.tools import telemetry

        for fp, entry in telemetry.aggregate_usage(output_dir).items():
            lh = entry.get("last_hit")
            if lh:
                retrieval_map[str(fp).replace("\\", "/")] = str(lh)
    except Exception:
        pass

    retrieval_threshold = datetime.now() - timedelta(days=retrieval_gap_days)
    for sc in scenarios:
        path = output_dir / sc["file"]
        fm = _read_frontmatter(path) or {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        if meta.get("source_notes"):
            continue  # provenance present — not an orphan
        last_hit = retrieval_map.get(sc["file"].replace("\\", "/"))
        recently_used = False
        if last_hit:
            try:
                recently_used = datetime.fromisoformat(last_hit) >= retrieval_threshold
            except ValueError:
                recently_used = True  # unparseable timestamp: be conservative
        if recently_used:
            continue
        issues.append(
            {
                "check": "scenario_orphan",
                "severity": "info",
                "message": (
                    f"Scene block '{sc['title']}' has no source_notes provenance and "
                    f"has not been retrieved for {retrieval_gap_days}+ days — "
                    "consider reviewing, merging, or retiring it."
                ),
                "file": sc["file"],
                "suggestion": (
                    "Verify the block is still valid; retire via [DELETED] on the "
                    "next consolidate_notes run if superseded."
                ),
            }
        )
    return issues


# ---------------------------------------------------------------------------
#  OKF v0.2 conformance (§11 / §12)
# ---------------------------------------------------------------------------


def _check_okf_conformance(
    output_dir: Path,
    skip_notes_staleness: bool = False,
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
        CONVERSATIONS_DIR,
        INDEX_FILENAME,
        META_DIR,
        NOTES_DIR,
        RAW_DIR,
        TASKS_DIR,
        WIKI_DIR,
    )

    issues: List[Dict[str, Any]] = []

    # Collect candidate .md files across the bundle.  P3: the original scan
    # only covered wiki/, notes/ and raw/sources/, silently missing root-level
    # runbooks such as team-memory-hook.md.  Scan the whole bundle and skip
    # scratch/staging directories (.meta/, .trash/, .hook-debug/) and the raw/
    # capture staging layer (conv-*.md from capture_conversation).  raw/sources/
    # is exempt: it holds the ingested source documents that still get audited.
    #
    # System-generated layers are exempt from OKF conformance: tasks/ (task.md
    # + memories.md, 由 task_manager 维护，frontmatter 由任务系统自行管理) 和
    # conversations/ (L0 蒸馏归档层，conv-*.md 的 frontmatter 由蒸馏管线写入,
    # 含 captured_at/content_hash 等私有键)。
    _scratch_dirs = {META_DIR, ".trash", ".hook-debug"}
    _system_layers = {TASKS_DIR, CONVERSATIONS_DIR}
    targets: List[Path] = []
    for _md in output_dir.rglob("*.md"):
        parts = _md.parts
        # raw/ 根下是 capture_conversation 采集暂存层（conv-*.md），跳过；
        # raw/sources/ 是真实源文档层，仍参与审计。
        if RAW_DIR in parts and "sources" not in parts:
            continue
        if any(_part in _scratch_dirs for _part in parts):
            continue
        # 系统生成层（任务记忆、蒸馏归档）不要求 OKF 合规
        if any(_part in _system_layers for _part in parts):
            continue
        targets.append(_md)

    today_str = date.today().isoformat()

    for md_file in sorted(targets):
        # §4/§11: index.md, log.md and its monthly shards (log-YYYY-MM.md)
        # are reserved system files
        if md_file.name in ("index.md", "log.md") or (
            md_file.name.startswith("log-") and md_file.name.endswith(".md")
        ):
            continue

        rel_path = md_file.relative_to(output_dir).as_posix()
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not text.startswith("---") or text.find("---", 3) < 0:
            issues.append(
                {
                    "check": "okf_conformance",
                    "severity": "error",
                    "message": "Missing YAML frontmatter (OKF v0.2 §11 requires a 'type' field)",
                    "file": rel_path,
                    "suggestion": (
                        "Run `python scripts/migrate_okf.py <wiki-dir>` to backfill "
                        "OKF frontmatter, or regenerate the page."
                    ),
                }
            )
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
                issues.append(
                    {
                        "check": "okf_conformance",
                        "severity": "error",
                        "message": "Frontmatter is not parseable YAML (OKF v0.2 §11)",
                        "file": rel_path,
                        "suggestion": "Fix the YAML frontmatter block manually or regenerate the page.",
                    }
                )
                continue

        # §4: type is the only required field
        page_type = fm.get("type")
        if not page_type or not str(page_type).strip():
            issues.append(
                {
                    "check": "okf_conformance",
                    "severity": "error",
                    "message": "Missing required 'type' field in frontmatter (OKF v0.2 §4)",
                    "file": rel_path,
                    "suggestion": (
                        "Run `python scripts/migrate_okf.py <wiki-dir>` to backfill "
                        "the type field, or regenerate the page."
                    ),
                }
            )

        # P2: producer-private keys must not leak at the top level.  OKF §4/§5
        # standard fields plus the backward-compat legacy set are allowed; any
        # other key should be folded under `metadata:`.
        _unknown_top = sorted(set(fm) - _OKF_TOP_LEVEL_KEYS - _OKF_LEGACY_TOP_LEVEL_KEYS)
        if _unknown_top:
            issues.append(
                {
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
                }
            )

        # §5 status vocabulary
        status_raw = fm.get("status")
        status = str(status_raw).strip().lower() if status_raw else ""
        if status and status not in _OKF_STATUSES:
            mapped = _LEGACY_STATUS_MAP.get(status)
            if mapped:
                issues.append(
                    {
                        "check": "okf_conformance",
                        "severity": "warning",
                        "message": (f"Legacy status '{status}' — OKF v0.2 uses '{mapped}'"),
                        "file": rel_path,
                        "suggestion": (
                            "Run `python scripts/migrate_okf.py <wiki-dir>` to migrate "
                            "legacy lifecycle statuses to the OKF v0.2 vocabulary."
                        ),
                    }
                )
            else:
                issues.append(
                    {
                        "check": "okf_conformance",
                        "severity": "warning",
                        "message": (
                            f"Unknown status '{status}' — expected one of "
                            f"draft/stable/deprecated (OKF v0.2 §5)"
                        ),
                        "file": rel_path,
                        "suggestion": "Set status to draft, stable, or deprecated.",
                    }
                )

        # §5 verified: mapping or list of mappings ({by, at, note?})
        verified = fm.get("verified")
        if verified is not None:
            valid = isinstance(verified, dict) or (
                isinstance(verified, list) and all(isinstance(v, dict) for v in verified)
            )
            if not valid:
                issues.append(
                    {
                        "check": "okf_conformance",
                        "severity": "warning",
                        "message": "'verified' must be a mapping or a list of {by, at} mappings (OKF v0.2 §5)",
                        "file": rel_path,
                        "suggestion": "Use confirm_note to record verification events correctly.",
                    }
                )

        # §5 stale_after expiry
        stale_after = fm.get("stale_after")
        if stale_after:
            sa = str(stale_after)[:10]
            # Notes are judged by the dedicated type-aware stale_notes check
            # (with retrieval-defer + per-type windows); skip them here to
            # avoid double-reporting when that check also runs.
            is_note = NOTES_DIR in md_file.parts
            if re.match(r"^\d{4}-\d{2}-\d{2}$", sa) and sa < today_str:
                if skip_notes_staleness and is_note:
                    pass  # handled by _check_stale_notes
                else:
                    issues.append(
                        {
                            "check": "okf_conformance",
                            "severity": "warning",
                            "message": f"stale_after ({sa}) has passed — knowledge may be outdated",
                            "file": rel_path,
                            "suggestion": (
                                "Verify the content is still accurate, then regenerate or "
                                "update the page to renew stale_after."
                            ),
                        }
                    )

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
            issues.append(
                {
                    "check": "okf_conformance",
                    "severity": "warning",
                    "message": "wiki/index.md does not declare okf_version (OKF v0.2 §12)",
                    "file": "wiki/index.md",
                    "suggestion": (
                        "Regenerate the index, or run `python scripts/migrate_okf.py "
                        "<wiki-dir>` to add okf_version."
                    ),
                }
            )

    return issues


def _check_layout_violations(output_dir: Path) -> List[Dict[str, Any]]:
    """Centralized-layout discipline (ticket 09).

    Two rules, only meaningful under a centralized workspace (the dispatcher
    gates on ``is_centralized_corpus``):

    * **knowledge leak** — a registered business repo's directory contains a
      ``repowiki/``; centralized keeps business repos pure-code, so knowledge
      has leaked back into the repo. Severity ``warning``.
    * **missing provenance** — a shared-pool page carries no ``repo:``/
      ``repos:`` tag. Untagged means "global," which is legitimate, so this
      is an ``info`` advisory asking the reader to confirm intent; its real
      job is surfacing orphans whose sole source was stripped by a
      ``remove_workspace_repo`` cleanup (ticket 10) for a human decision.

    Module partitions are exempt: their location IS their provenance.
    """
    from codewiki.mcp.tools.workspace_bootstrap import read_registration_table_names
    from codewiki.mcp.tools.workspace_layout import read_provenance

    issues: List[Dict[str, Any]] = []
    workspace_root = output_dir.parent

    # Rule 1: knowledge leaked back into a business repo
    for name in sorted(read_registration_table_names(workspace_root)):
        leaked = workspace_root / name / "repowiki"
        if leaked.exists():
            issues.append(
                {
                    "check": "layout_violations",
                    "severity": "warning",
                    "message": (
                        f"business repo '{name}' contains a repowiki/ directory; "
                        "centralized layout keeps business repos pure-code."
                    ),
                    "file": f"{name}/repowiki",
                    "line": 1,
                    "suggestion": (
                        "Merge the leaked knowledge into the workspace repowiki "
                        "(modules → wiki/modules/<repo>/, the rest → shared pools "
                        "with repo: tags), then remove the in-repo repowiki."
                    ),
                }
            )

    # Rule 2: shared-pool pages without provenance (advisory)
    shared_dirs = [
        output_dir / "wiki" / "entities",
        output_dir / "wiki" / "concepts",
        output_dir / "wiki" / "sources",
        output_dir / "wiki" / "comparisons",
        output_dir / "wiki" / "queries",
        output_dir / "notes",
    ]
    for d in shared_dirs:
        if not d.is_dir():
            continue
        for page in sorted(d.glob("*.md")):
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if read_provenance(text):
                continue
            try:
                rel = page.relative_to(output_dir).as_posix()
            except ValueError:
                rel = page.name
            issues.append(
                {
                    "check": "layout_violations",
                    "severity": "info",
                    "message": (
                        "shared-pool page has no repo:/repos: provenance — "
                        "confirm it is intentionally product-line (global)."
                    ),
                    "file": rel,
                    "line": 1,
                    "suggestion": (
                        "If it belongs to specific repo(s), add a repo:/repos: tag; "
                        "if it is an orphan left by remove_workspace_repo, keep or "
                        "delete it deliberately."
                    ),
                }
            )

    return issues


def _check_team_layout_gitignore(output_dir: Path) -> List[Dict[str, Any]]:
    """Team-layout Phase 1 (D1): rebuildable derived files must not be tracked.

    Every file in ``TEAM_LAYOUT_REBUILDABLE_FILES`` has a local rebuild path
    (directory scan / re-analysis / rebuild_index); committing it only creates
    merge conflicts.  This check reports the ones still tracked by git so a
    team migrating to the layout sees exactly what ``codewiki
    migrate-team-layout`` will fix.  Skipped silently when output_dir is not
    inside a git repository (nothing to untrack).
    """
    from codewiki.mcp.tools.team_layout import find_repo_root, list_tracked_rebuildables

    issues: List[Dict[str, Any]] = []
    repo_root = find_repo_root(output_dir)
    if repo_root is None:
        return issues  # not a git repo — nothing to check
    for rel in list_tracked_rebuildables(repo_root, output_dir):
        issues.append(
            {
                "check": "team_layout_gitignore",
                "severity": "warning",
                "message": (
                    f"'{rel}' is a rebuildable derived file tracked by git — "
                    "in team use it becomes a recurring merge-conflict source."
                ),
                "file": rel,
                "line": 1,
                "suggestion": (
                    "Run `codewiki migrate-team-layout` (untracks via "
                    "git rm --cached, files stay on disk) or add the "
                    "team-layout block to .gitignore manually."
                ),
            }
        )
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

    # ``fix=true`` lets lint self-heal index staleness: when the only
    # stale_refs point at the wiki index (i.e. index.md references files that
    # have been removed), rebuild the index BEFORE the checks run, so no
    # check reports issues the rebuild already resolved. Content files are
    # never modified -- the fix only regenerates the index.
    fix = bool(arguments.get("fix", False))

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

    # Team-layout Phase 1 (D7): wiki/index.md is a rebuildable derived file
    # no longer committed — a fresh clone has no copy.  Materialise it
    # transparently before the checks run (seconds-cheap, byte-stable, no-op
    # when present) so index-referencing checks never report its absence.
    if output_dir:
        try:
            from codewiki.mcp.tools.wiki_index import ensure_index

            ensure_index(output_dir)
        except Exception:  # self-heal must never block lint
            pass

    # Self-heal stale index references when fix=true.  Rebuild the index only
    # when every stale_ref points at wiki/index.md (a stale generated index),
    # leaving content files untouched.  This runs BEFORE the checks so every
    # check that reads wiki files (stale_refs, broken_links, orphan_pages, ...)
    # sees the rebuilt index and does not report issues that the rebuild
    # already resolved.  Non-fatal: failures leave the original issues in
    # place (the checks below simply run against the old state).
    if fix and output_dir and "stale_refs" in checks:
        try:
            pre_stale = _check_stale_refs(output_dir, module_tree)
            if pre_stale and all(
                Path(str(i.get("file", ""))).as_posix().endswith("wiki/index.md") for i in pre_stale
            ):
                from codewiki.mcp.tools.wiki_index import rebuild_index

                rebuild_index(output_dir)
                module_tree = _load_module_tree(output_dir)
        except Exception as exc:  # keep lint non-fatal
            all_issues.append(
                {
                    "check": "stale_refs",
                    "severity": "error",
                    "message": f"fix=true rebuild failed: {exc}",
                    "file": "wiki/index.md",
                    "line": 1,
                    "suggestion": "Run the rebuild manually and re-lint.",
                }
            )

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
                    threshold = schema.get("lint", {}).get("high_impact_threshold", 5)
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

    if "stale_evidence" in checks and output_dir:
        all_issues.extend(_check_stale_evidence(output_dir))

    if "stale_notes" in checks and output_dir:
        # Config (type-aware windows + retrieval-defer) is read from
        # schema.yaml inside the check; dispatch passes no hardcoded values.
        all_issues.extend(_check_stale_notes(output_dir))

    if "note_clusters" in checks and output_dir:
        all_issues.extend(_check_note_clusters(output_dir))

    if "low_adoption" in checks and output_dir:
        # Config (min_hits/max_adopted/recent_days) is read from schema.yaml
        # inside the check; dispatch passes no hardcoded values.
        all_issues.extend(_check_low_adoption(output_dir))

    if "scenario_capacity" in checks and output_dir:
        all_issues.extend(_check_scenario_capacity(output_dir))

    if "scenario_orphan" in checks and output_dir:
        all_issues.extend(_check_scenario_orphan(output_dir))

    if "okf_conformance" in checks and output_dir:
        all_issues.extend(
            _check_okf_conformance(
                output_dir,
                skip_notes_staleness=("stale_notes" in checks),
            )
        )

    # Centralized-layout discipline (ticket 09): gated so non-centralized
    # corpora never see these checks.
    if "layout_violations" in checks and output_dir:
        from codewiki.mcp.tools.workspace_layout import is_centralized_corpus

        if is_centralized_corpus(output_dir):
            all_issues.extend(_check_layout_violations(output_dir))

    # Team-layout Phase 1 (D1): rebuildable derived files must stay untracked.
    if "team_layout_gitignore" in checks and output_dir:
        all_issues.extend(_check_team_layout_gitignore(output_dir))

    # Deduplicate: if a link is already reported as stale_refs, don't also
    # report it as broken_links (same file + line = same underlying problem).
    stale_locations = {
        (issue.get("file"), issue.get("line"))
        for issue in all_issues
        if issue.get("check") == "stale_refs"
    }
    all_issues = [
        issue
        for issue in all_issues
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
        issue for issue in all_issues if _SEVERITY_ORDER.get(issue["severity"], 2) <= min_severity
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

            append_log(str(output_dir), "lint_wiki", f"检查完成: {len(filtered)} 个问题")
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
