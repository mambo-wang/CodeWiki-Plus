"""MCP tool: schema_generator — auto-generate project documentation constitution.

Generates a ``schema.yaml`` in the output directory that captures project-specific
documentation conventions derived from the actual codebase structure.  On subsequent
runs, preserves user customizations while updating auto-inferred fields.
"""

from __future__ import annotations

import logging
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
    "okf_version": "0.2",
    "default_stale_days": 90,
    # 类型感知新鲜度窗口（新鲜度机制专项）：笔记 stale_after 按 note_type 查表，
    # 回退链 by_type[type] → default_window_days → default_stale_days → 90。
    # V4（OpenViking 借鉴 P3）：note_types 为类型权威声明表（枚举/复核窗口/
    # 晋升路由/合并字段策略），freshness.by_type 保留作向后兼容回退——
    # 消费方（load_freshness_config 等）优先读 note_types 派生值。
    "freshness": {
        "default_window_days": 180,
        "retrieval_defer_days": 60,
        "by_type": {
            "workaround": 45,
            "known_issue": 60,
            "general": 120,
            "pitfall": 180,
            "lesson": 180,
            "bug_fix": 180,
            "decision": 365,
            "architecture": 365,
        },
    },
    # V4 权威类型表：单一事实源，schema.yaml 覆盖式自定义（见 note_types.py）。
    "note_types": {},  # filled below from note_types.DEFAULT_NOTE_TYPES
    # 默认 tags 不再为空：schema.yaml 里 okf_tags 为 [] 时，
    # frontmatter 注入 helper 会回落到此默认值。
    "okf_tags": ["codewiki", "auto-generated"],
}

# V4: fill the note_types placeholder from the authoritative table (import kept
# below _DEFAULT_CONVENTIONS to keep the dict literal readable).
from codewiki.mcp.tools.note_types import DEFAULT_NOTE_TYPES  # noqa: E402

_DEFAULT_CONVENTIONS["note_types"] = {t: dict(spec) for t, spec in DEFAULT_NOTE_TYPES.items()}

_DEFAULT_REQUIRED_SECTIONS = [
    {"title": "Architecture Overview", "mermaid_diagram": True},
    {"title": "Component Constraint Index"},
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

_DEFAULT_EXPORT = {
    "html": False,  # opt-in: set to true to generate wiki-export.html on close_session
}

# Default doc_type definitions (prompt hints per documentation style)
_DEFAULT_DOC_TYPES = {
    "default": "design",
    "types": {
        "api": {
            "module": "Focus on API documentation: endpoints, parameters, return types, and usage examples."
        },
        "architecture": {
            "module": "Focus on architecture documentation: system design, component relationships, and data flow.",
            "overview": "Focus on system-level architecture: show how modules relate, data flows between components, and the overall layered design. Include a high-level Mermaid architecture diagram.",
        },
        "user-guide": {
            "module": "Focus on user guide documentation: how to use features, step-by-step tutorials."
        },
        "developer": {
            "module": "Focus on developer documentation: code structure, contribution guidelines, and implementation details."
        },
        "business": {
            "module": "Focus on business logic documentation: describe business workflows, processing pipelines, state transitions, and domain rules. Emphasize WHAT the system does for users and WHY, trace end-to-end business scenarios through the code, and document domain-specific terminology. De-emphasize infrastructure and deployment details."
        },
        "design": {
            "module": "Generate technical design documentation optimized for AI comprehension. For each module, describe in depth: (1) module responsibilities and boundaries, (2) detailed implementation logic and business rules, (3) data flow within and through the module, (4) interface contracts — inputs, outputs, and side effects, (5) internal layered design and component collaboration patterns, (6) relationships and dependencies with other modules, (7) constraints, assumptions, and edge cases. Use precise technical language. Include Mermaid diagrams for complex flows and interactions. Do not limit documentation length — let the content depth match the module's complexity.",
            "overview": "Focus on system-level architecture: show how modules relate to each other, data flows between components, overall layered design, and key architectural decisions. Provide a high-level view that helps readers understand the system's structural blueprint. Include Mermaid diagrams for the architecture overview.",
        },
    },
}

# Default code routing rules (Roadmap 2.1)
_DEFAULT_CODE_ROUTING = {
    "boilerplate_patterns": {
        "suffix": [
            "DTO",
            "VO",
            "Request",
            "Response",
            "Entity",
            "PO",
            "Model",
            "Mapper",
            "Repository",
            "Dao",
        ],
        "annotation": ["@Data", "@Getter", "@Entity", "@Table", "@Document"],
    },
    "business_patterns": {
        "suffix": ["Service", "Controller", "Job", "Consumer", "Handler", "Manager", "Processor"],
        "annotation": ["@Service", "@RestController", "@Controller", "@Component"],
    },
}

# Default page type routing table (LLM Wiki knowledge layer)
_DEFAULT_PAGE_TYPES = {
    "module": {
        "directory": "wiki/modules",
        "description": "代码模块文档，描述一个功能模块的架构、组件和依赖",
        "required_sections": [
            "Architecture Overview",
            "Component Constraint Index",
            "Component Responsibilities",
            "Cross-References",
        ],
    },
    "entity": {
        "directory": "wiki/entities",
        "description": "关键类、接口、数据模型、API 端点的独立文档",
        "required_sections": [
            "职责描述",
            "公开 API",
            "使用示例",
            "依赖关系",
        ],
    },
    "concept": {
        "directory": "wiki/concepts",
        "description": "设计模式、架构理念、领域概念的文档",
        "required_sections": [
            "概念定义",
            "适用场景",
            "在本项目中的应用",
        ],
    },
    "source": {
        "directory": "wiki/sources",
        "description": "第三方文档（SDK/API/框架文档）的摘要",
        "required_sections": [
            "文档概述",
            "关键 API/概念",
            "与本项目相关的部分",
        ],
    },
    "comparison": {
        "directory": "wiki/comparisons",
        "description": "方案对比、技术选型分析",
        "required_sections": [
            "背景与目标",
            "候选方案",
            "对比分析",
            "结论与决策",
        ],
    },
    "query": {
        "directory": "wiki/queries",
        "description": "方案设计决策记录，包含推理过程和权衡",
        "required_sections": [
            "问题描述",
            "调研过程",
            "方案权衡",
            "决策结论",
        ],
    },
}

# ── installation schema.yaml loading ─────────────────────────────────────

_CONFIG_PATH_PKG = Path(__file__).resolve().parents[2] / "templates" / "schema.yaml"
_CONFIG_PATH_ROOT = Path(__file__).resolve().parents[3] / "schema.yaml"
_CONFIG_PATH = _CONFIG_PATH_PKG if _CONFIG_PATH_PKG.exists() else _CONFIG_PATH_ROOT
_project_config_cache: Optional[dict] = None


def _load_project_config() -> dict:
    """Load schema.yaml from CodeWiki-CN installation root as default template.

    Returns cached result on subsequent calls.  Returns empty dict on any
    failure so callers can transparently fall back to hardcoded defaults.
    """
    global _project_config_cache
    if _project_config_cache is not None:
        return _project_config_cache
    try:
        from ruamel.yaml import YAML

        if _CONFIG_PATH.exists():
            yaml = YAML()
            yaml.preserve_quotes = True
            data = yaml.load(_CONFIG_PATH)
            if isinstance(data, dict):
                _project_config_cache = data
                logger.info("Loaded project config from %s", _CONFIG_PATH)
                return _project_config_cache
    except Exception as e:
        logger.warning("Failed to load installation schema.yaml: %s", e)
    _project_config_cache = {}
    return _project_config_cache


def _get_defaults() -> dict:
    """Build merged defaults: hardcoded defaults overridden by installation schema.yaml."""
    cfg = _load_project_config()
    return {
        "purpose": cfg.get("purpose", ""),
        "doc_types": cfg.get("doc_types", _DEFAULT_DOC_TYPES),
        "conventions": {**_DEFAULT_CONVENTIONS, **cfg.get("conventions", {})},
        "required_sections": cfg.get("required_sections", _DEFAULT_REQUIRED_SECTIONS),
        "documentation_dimensions": cfg.get("documentation_dimensions", _DEFAULT_DIMENSIONS),
        "update_policy": {**_DEFAULT_UPDATE_POLICY, **cfg.get("update_policy", {})},
        "lint": {**_DEFAULT_LINT, **cfg.get("lint", {})},
        "code_routing": {**_DEFAULT_CODE_ROUTING, **cfg.get("code_routing", {})},
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
        "purpose": defaults["purpose"],
        "doc_types": defaults["doc_types"],
        "conventions": inferred_conventions,
        "required_sections": list(defaults["required_sections"]),
        "documentation_dimensions": list(defaults["documentation_dimensions"]),
        "update_policy": dict(defaults["update_policy"]),
        "lint": dict(defaults["lint"]),
        "export": dict(_DEFAULT_EXPORT),
        "page_types": dict(defaults["page_types"]),
        "extraction_granularity": defaults["extraction_granularity"],
        "wiki_link_syntax": defaults["wiki_link_syntax"],
    }

    # Merge with existing schema if present
    existing = _load_existing_schema(schema_path)
    if existing is not None:
        # Team-layout Phase 1 (churn suppression): schema.yaml is the team's
        # highest-frequency meaningless-conflict source — every analyze_repo
        # run used to rewrite generated_at (and occasionally project.*),
        # producing a diff for every developer even when nothing substantive
        # changed.  Snapshot the on-disk content with generated_at stripped;
        # if the merge result is byte-identical apart from the timestamp,
        # skip the write-back entirely.  generated_at thus becomes "last
        # substantive change of auto-managed content", matching the
        # team-layout design doc §5.2.
        before_text = _normalized_yaml_text(existing)
        old_generated_at = existing.get("generated_at")
        new_schema = _merge_schemas(existing, new_schema)
        if _normalized_yaml_text(new_schema) == before_text:
            new_schema["generated_at"] = old_generated_at
            logger.debug("Schema unchanged (timestamp-only drift); write skipped")
            return new_schema

    # Write to disk
    _write_yaml(schema_path, new_schema)

    return new_schema


def _normalized_yaml_text(data) -> str:
    """Serialize *data* to YAML text with ``generated_at`` stripped.

    The churn-free signature used to decide whether a merge changed anything
    substantive.  Works on both plain dicts and ruamel CommentedMaps
    (deep-copied first so the caller's object is never mutated).
    """
    import copy
    from io import StringIO

    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    snapshot = copy.deepcopy(data)
    if isinstance(snapshot, dict):
        snapshot.pop("generated_at", None)
    buf = StringIO()
    yaml.dump(snapshot, buf)
    return buf.getvalue()


def _load_existing_schema(schema_path: Path):
    """Load existing schema.yaml using ruamel.yaml round-trip mode.

    Returns a CommentedMap (dict-like) that preserves comments, or None if
    the file is not found or invalid.
    """
    if not schema_path.exists():
        return None
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        data = yaml.load(schema_path)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Failed to load existing schema: %s", e)
    return None


def _merge_schemas(existing, new: dict):
    """Merge new auto-inferred data into existing schema (mutates in place).

    Mutating the existing CommentedMap preserves YAML comments attached to
    user-customized keys.

    Auto-managed fields (version, generated_at, project.name/languages/total_components)
    are always updated.  All other fields from the existing schema are preserved.

    page_types uses shallow merge: user-customized types preserved, new defaults added.
    """
    # Always refresh auto-managed fields from new
    for key in _AUTO_FIELDS:
        if key in new:
            existing[key] = new[key]

    # Add top-level keys that exist in new but not in existing
    for key in new:
        if key not in existing:
            existing[key] = new[key]

    # Handle page_types shallow merge: add new default types not present in existing
    if "page_types" in new and "page_types" in existing:
        if isinstance(existing["page_types"], dict):
            for pt_name, pt_config in new["page_types"].items():
                if pt_name not in existing["page_types"]:
                    existing["page_types"][pt_name] = pt_config

    # Handle dict fields: add new sub-keys that don't exist in existing
    for key in new:
        if key in _AUTO_FIELDS or key == "page_types":
            continue
        if isinstance(new[key], dict) and isinstance(existing.get(key), dict):
            for sub_key, sub_val in new[key].items():
                if sub_key not in existing[key]:
                    existing[key][sub_key] = sub_val
            # conventions.module_naming is auto-inferred — always refresh
            if key == "conventions" and "module_naming" in new.get(key, {}):
                existing[key]["module_naming"] = new[key]["module_naming"]

    return existing


def _write_yaml(path: Path, data) -> None:
    """Write schema data as YAML using ruamel.yaml round-trip mode.

    If *data* is a CommentedMap (loaded from an existing file), all comments
    are preserved automatically.  For brand-new schemas (plain dict), a header
    comment block is attached before writing.
    """
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.explicit_start = True  # emit '---' document start marker

        # For new schemas, wrap in CommentedMap and attach header comment
        if not isinstance(data, CommentedMap):
            cm = CommentedMap(data)
            cm.yaml_set_start_comment(
                "CodeWiki LLM Wiki — Project Documentation Constitution\n"
                "Auto-generated, can be manually edited. "
                "Re-running analyze_repo preserves user customizations.\n"
                "Fields under 'project' are always auto-updated."
            )
            data = cm

        # Team-layout Phase 2: dump to string then atomic-write (temp +
        # replace) — a crash mid-dump used to leave a truncated schema.yaml.
        from io import StringIO

        buf = StringIO()
        yaml.dump(data, buf)
        from codewiki.src.store import atomic_write

        atomic_write(path, buf.getvalue())
        logger.info("Schema written to %s", path)
    except Exception as e:
        logger.warning("Failed to write schema.yaml: %s", e)
