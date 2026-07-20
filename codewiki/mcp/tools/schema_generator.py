"""MCP tool: schema_generator — auto-generate project documentation constitution.

Generates a ``schema.yaml`` in the output directory that captures project-specific
documentation conventions derived from the actual codebase structure.  On subsequent
runs, preserves user customizations while updating auto-inferred fields.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Fields that are always auto-managed (user edits to these may be overwritten)
_AUTO_FIELDS = {"version", "generated_at", "project"}

# Default conventions
_DEFAULT_CONVENTIONS = {
    "module_naming": "snake_case",
    "file_pattern": "*.md",
    "cross_reference_format": "[[{module_name}]]({{module_name}}.md)",
    "mermaid_required": True,
    "min_leaf_doc_lines": 200,
    "max_overview_doc_lines": 300,
    "auto_crosslink": True,
    "okf_frontmatter": True,
    "okf_tags": [],
}

_DEFAULT_REQUIRED_SECTIONS = [
    {"title": "Architecture Overview", "mermaid_diagram": True},
    {"title": "Component Responsibilities"},
    {"title": "Cross-References"},
]

_DEFAULT_DIMENSIONS = [
    "architecture_decisions",
    "api_contracts",
    "data_model_changes",
    "dependency_rationale",
]

_DEFAULT_UPDATE_POLICY = {
    "on_code_change": "update_affected",
    "preserve_decisions": True,
    "cascade_to_overview": True,
}

_DEFAULT_LINT = {
    "high_impact_threshold": 5,
}

# Default page type routing table (LLM Wiki knowledge layer)
_DEFAULT_PAGE_TYPES = {
    "module": {
        "directory": "wiki/modules",
        "description": "代码模块文档，描述一个功能模块的架构、组件和依赖",
        "required_sections": [
            "Architecture Overview",
            "Component Responsibilities",
            "Cross-References",
        ],
    },
    "entity": {
        "directory": "wiki/entities",
        "description": "关键类、接口、数据模型、API 端点的独立文档",
        "required_sections": [
            "职责描述", "公开 API", "使用示例", "依赖关系",
        ],
    },
    "concept": {
        "directory": "wiki/concepts",
        "description": "设计模式、架构理念、领域概念的文档",
        "required_sections": [
            "概念定义", "适用场景", "在本项目中的应用",
        ],
    },
    "source": {
        "directory": "wiki/sources",
        "description": "第三方文档（SDK/API/框架文档）的摘要",
        "required_sections": [
            "文档概述", "关键 API/概念", "与本项目相关的部分",
        ],
    },
    "comparison": {
        "directory": "wiki/comparisons",
        "description": "方案对比、技术选型分析",
        "required_sections": [
            "背景与目标", "候选方案", "对比分析", "结论与决策",
        ],
    },
    "query": {
        "directory": "wiki/queries",
        "description": "方案设计决策记录，包含推理过程和权衡",
        "required_sections": [
            "问题描述", "调研过程", "方案权衡", "决策结论",
        ],
    },
}

# ── config.yaml loading ──────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config.yaml"
_project_config_cache: Optional[dict] = None


def _load_project_config() -> dict:
    """Load config.yaml from CodeWiki-CN installation root.

    Returns cached result on subsequent calls.  Returns empty dict on any
    failure so callers can transparently fall back to hardcoded defaults.
    """
    global _project_config_cache
    if _project_config_cache is not None:
        return _project_config_cache
    try:
        import yaml
        if _CONFIG_PATH.exists():
            data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _project_config_cache = data
                logger.info("Loaded project config from %s", _CONFIG_PATH)
                return _project_config_cache
    except Exception as e:
        logger.warning("Failed to load config.yaml: %s", e)
    _project_config_cache = {}
    return _project_config_cache


def _get_defaults() -> dict:
    """Build merged defaults: hardcoded defaults overridden by config.yaml."""
    cfg = _load_project_config()
    return {
        "conventions": {**_DEFAULT_CONVENTIONS, **cfg.get("conventions", {})},
        "required_sections": cfg.get("required_sections", _DEFAULT_REQUIRED_SECTIONS),
        "documentation_dimensions": cfg.get("documentation_dimensions", _DEFAULT_DIMENSIONS),
        "update_policy": {**_DEFAULT_UPDATE_POLICY, **cfg.get("update_policy", {})},
        "lint": {**_DEFAULT_LINT, **cfg.get("lint", {})},
        "page_types": cfg.get("page_types", _DEFAULT_PAGE_TYPES),
        "extraction_granularity": cfg.get("extraction_granularity", "standard"),
        "wiki_link_syntax": cfg.get("wiki_link_syntax", False),
    }


def _detect_naming_convention(names: List[str]) -> str:
    """Detect the dominant naming convention from a list of names."""
    if not names:
        return "unknown"

    counts: Counter = Counter()
    for name in names:
        if not name:
            continue
        if "-" in name:
            counts["kebab-case"] += 1
        elif "_" in name:
            counts["snake_case"] += 1
        elif name[0].isupper():
            counts["PascalCase"] += 1
        elif any(c.isupper() for c in name[1:]):
            counts["camelCase"] += 1
        else:
            counts["snake_case"] += 1  # default for single lowercase words

    if not counts:
        return "unknown"
    return counts.most_common(1)[0][0]


def generate_schema(
    repo_name: str,
    components: Dict[str, Any],
    languages: List[str],
    output_dir: Path,
    module_names: Optional[List[str]] = None,
) -> dict:
    """Generate or update schema.yaml in *output_dir*.

    If schema.yaml already exists, merges with it — auto-inferred fields
    are updated, but user-customized fields are preserved.

    Returns the final schema dict.
    """
    from codewiki.src.config import SCHEMA_FILENAME

    schema_path = output_dir / SCHEMA_FILENAME

    # Build auto-inferred data
    inferred_project = {
        "name": repo_name,
        "languages": sorted(set(languages)),
        "total_components": len(components),
    }

    # Detect naming convention from module names if available
    naming = _detect_naming_convention(module_names or [])

    defaults = _get_defaults()
    inferred_conventions = dict(defaults["conventions"])
    if naming != "unknown":
        inferred_conventions["module_naming"] = naming

    # Build the full new schema
    new_schema: Dict[str, Any] = {
        "version": 1,
        "generated_at": datetime.now().isoformat(),
        "project": inferred_project,
        "conventions": inferred_conventions,
        "required_sections": list(defaults["required_sections"]),
        "documentation_dimensions": list(defaults["documentation_dimensions"]),
        "update_policy": dict(defaults["update_policy"]),
        "lint": dict(defaults["lint"]),
        "page_types": dict(defaults["page_types"]),
        "extraction_granularity": defaults["extraction_granularity"],
        "wiki_link_syntax": defaults["wiki_link_syntax"],
    }

    # Merge with existing schema if present
    existing = _load_existing_schema(schema_path)
    if existing is not None:
        new_schema = _merge_schemas(existing, new_schema)

    # Write to disk
    _write_yaml(schema_path, new_schema)

    return new_schema


def _load_existing_schema(schema_path: Path) -> Optional[dict]:
    """Load existing schema.yaml, returning None if not found or invalid."""
    if not schema_path.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Failed to load existing schema: %s", e)
    return None


def _merge_schemas(existing: dict, new: dict) -> dict:
    """Merge existing schema with new auto-inferred data.

    Auto-managed fields (version, generated_at, project.name/languages/total_components)
    are always updated.  All other fields from the existing schema are preserved.

    page_types uses shallow merge: user-customized types preserved, new defaults added.
    """
    merged = dict(new)  # start from new schema

    # Preserve user-customized top-level sections
    for key in existing:
        if key in _AUTO_FIELDS:
            continue  # always use new auto values
        if key == "page_types":
            # Shallow merge by page type name:
            # - existing user types are preserved entirely
            # - new default types are added if not present
            merged_pt = dict(new.get("page_types", {}))
            for pt_name, pt_config in existing.get("page_types", {}).items():
                merged_pt[pt_name] = pt_config  # user customisation wins
            merged["page_types"] = merged_pt
        elif key not in merged:
            merged[key] = existing[key]
        elif isinstance(existing[key], dict) and isinstance(merged.get(key), dict):
            # Deep merge dicts: existing user values win for non-auto keys
            merged_dict = dict(merged[key])
            for sub_key, sub_val in existing[key].items():
                if sub_key not in merged_dict:
                    merged_dict[sub_key] = sub_val
                # For conventions, auto-inferred keys are overwritten
                # but user-added keys are preserved
            merged[key] = merged_dict
        elif isinstance(existing[key], list) and isinstance(merged.get(key), list):
            # Lists: keep existing if user modified (different length or content)
            if existing[key] != new.get(key):
                merged[key] = existing[key]

    return merged


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict as YAML, using a clean format with comments."""
    try:
        import yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# CodeWiki LLM Wiki — Project Documentation Constitution\n"
            "# Auto-generated, can be manually edited. "
            "Re-running analyze_repo preserves user customizations.\n"
            "# Fields under 'project' are always auto-updated.\n"
            "---\n"
        )
        yaml_content = yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        path.write_text(header + yaml_content, encoding="utf-8")
        logger.info("Schema written to %s", path)
    except Exception as e:
        logger.warning("Failed to write schema.yaml: %s", e)
