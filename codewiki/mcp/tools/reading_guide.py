"""Internal utility: generate reading-guide.md via PageRank.

Called automatically by close_session — not exposed as an MCP tool.
Produces a markdown reading guide in the wiki output directory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.src.be.dependency_analyzer.topo_sort import (
    build_graph_from_components,
    build_reverse_graph,
    compute_pagerank,
)

logger = logging.getLogger(__name__)


def _build_comp_module_index(module_tree: Dict[str, Any]) -> Dict[str, str]:
    """Build a component-id → module-name inverted index."""
    index: Dict[str, str] = {}

    def _walk(tree: Dict) -> None:
        for mod_name, mod_info in tree.items():
            for cid in mod_info.get("components", []):
                index.setdefault(cid, mod_name)
            children = mod_info.get("children", {})
            if isinstance(children, dict) and children:
                _walk(children)

    _walk(module_tree)
    return index


def generate_reading_guide(
    components: Dict[str, Any],
    module_tree: Optional[Dict[str, Any]],
    output_dir: str,
    *,
    top_n: int = 20,
) -> Optional[str]:
    """Generate wiki/reading-guide.md from PageRank analysis.

    Args:
        components: Component dict from session (comp_id → Node).
        module_tree: Module clustering tree (may be None).
        output_dir: Wiki output directory path.
        top_n: Number of top components to include.

    Returns:
        Path to the generated file, or None if generation failed.
    """
    if not components:
        return None

    try:
        graph = build_graph_from_components(components)
        scores = compute_pagerank(graph)
        if not scores:
            return None

        reverse = build_reverse_graph(graph)
        comp_module_idx = _build_comp_module_index(module_tree) if module_tree else {}

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_n]

        # Build markdown. 带 OKF 兼容 frontmatter：本文件由 close_session 自动重建，
        # 若无 type 字段会被 lint 的 okf_conformance 检查标记为缺失 frontmatter。
        from codewiki.mcp import i18n as _i18n

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines: List[str] = [
            "---",
            "type: Concept",
            'title: "' + _i18n.t("artifacts.reading_guide.title") + '"',
            f"generated: {{ by: codewiki/reading_guide.py, at: {generated_at} }}",
            "stale_after: 2099-12-31",
            'description: "' + _i18n.t("artifacts.reading_guide.description") + '"',
            "---",
            _i18n.t("artifacts.reading_guide.heading"),
            "",
            _i18n.t("artifacts.reading_guide.description"),
            _i18n.t("artifacts.reading_guide.intro_line2"),
            _i18n.t("artifacts.reading_guide.intro_line3"),
            "",
            _i18n.t("artifacts.reading_guide.recommended_order"),
            "",
            _i18n.t("artifacts.reading_guide.table_header"),
            "|---|------|------|----------|--------------|----------|------|",
        ]

        for i, (comp_id, score) in enumerate(ranked, 1):
            meta = components.get(comp_id)
            name = getattr(meta, "name", comp_id) if meta else comp_id
            ctype = getattr(meta, "component_type", "?") if meta else "?"
            fpath = (
                (getattr(meta, "relative_path", "") or getattr(meta, "file_path", ""))
                if meta
                else ""
            )
            mod = comp_module_idx.get(comp_id, "-")
            dep_count = len(reverse.get(comp_id, set()))
            # Truncate long paths for table readability
            short_path = fpath if len(fpath) <= 50 else "..." + fpath[-47:]
            lines.append(
                f"| {i} | `{name}` | {ctype} | {mod} | {dep_count} | {score:.4f} | {short_path} |"
            )

        # Module-level summary
        if comp_module_idx:
            mod_scores: Dict[str, float] = {}
            for comp_id, score in scores.items():
                mod = comp_module_idx.get(comp_id)
                if mod:
                    mod_scores[mod] = mod_scores.get(mod, 0.0) + score

            top_mods = sorted(mod_scores.items(), key=lambda x: -x[1])[:10]
            if top_mods:
                lines.extend(
                    [
                        "",
                        _i18n.t("artifacts.reading_guide.module_ranking"),
                        "",
                        _i18n.t("artifacts.reading_guide.module_table_header"),
                        "|---|------|---------------|",
                    ]
                )
                for i, (mod, sc) in enumerate(top_mods, 1):
                    lines.append(f"| {i} | {mod} | {sc:.4f} |")

        lines.extend(
            [
                "",
                "---",
                _i18n.t(
                    "artifacts.reading_guide.footer",
                    components=len(components),
                    edges=sum(len(d) for d in graph.values()),
                ),
            ]
        )

        # Write file
        wiki_dir = Path(output_dir) / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        out_path = wiki_dir / "reading-guide.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Generated reading guide: %s (%d components ranked)", out_path, len(ranked))
        return str(out_path)

    except Exception as e:
        logger.warning("Failed to generate reading guide: %s", e)
        return None
