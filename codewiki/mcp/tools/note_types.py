"""note_types — note type declarations, single source of truth (V4).

OpenViking 借鉴 P3-V4（docs/OpenViking借鉴详细设计方案-P3四项.md §1）：
note_type 的合法枚举、复核窗口、晋升路由、合并字段策略此前散在
schema_generator 硬编码、distill ``_VALID_NOTE_TYPES``、registry
inputSchema 枚举、knowledge_loop ``_PROMOTION_PAGE_TYPES`` 四处——
query_wiki type_filter 漏 "scenario" 的 live bug 即多处不同步所致。

本模块是唯一权威表：所有消费方 import 本表，schema.yaml 的
``conventions.note_types`` 段按 key 覆盖默认值（新类型/调窗只改一处）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 字段合并策略（V3 note_merge 消费；OpenViking merge_op 借鉴）：
#   body: append            正文按来源时间升序拼接，段间带来源标记
#   related_modules/title: replace  取最新一条
#   tags: union             并集（缺省，无需声明也生效）
_DEFAULT_MERGE_FIELDS: Dict[str, str] = {
    "body": "append",
    "related_modules": "replace",
    "title": "replace",
    "tags": "union",
}

# 权威声明表。每类笔记：
#   freshness_days — stale_after 复核窗口（天），派生 freshness.by_type
#   promote_to     — promote 晋升的默认目标 page_type（"" = 留给 agent）
#   merge_fields   — 多条同主题 draft 预合并时的字段策略
DEFAULT_NOTE_TYPES: Dict[str, Dict[str, Any]] = {
    "workaround": {
        "freshness_days": 45,
        "promote_to": "query",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "known_issue": {
        "freshness_days": 60,
        "promote_to": "query",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "general": {
        "freshness_days": 120,
        "promote_to": "",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "pitfall": {
        "freshness_days": 180,
        "promote_to": "query",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "lesson": {
        "freshness_days": 180,
        "promote_to": "concept",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "bug_fix": {
        "freshness_days": 180,
        "promote_to": "query",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "decision": {
        "freshness_days": 365,
        "promote_to": "concept",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
    "architecture": {
        "freshness_days": 365,
        "promote_to": "concept",
        "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
    },
}


def _load_schema(output_dir: Optional[Path]) -> Optional[dict]:
    """Best-effort schema load (page_router.load_schema), never raises."""
    if output_dir is None:
        return None
    try:
        from codewiki.mcp.tools.page_router import load_schema
        return load_schema(str(output_dir))
    except Exception as e:  # missing schema / parser absent — fall back to defaults
        logger.debug("note_types: schema load skipped (%s)", e)
        return None


def load_note_types(
    schema: Optional[dict] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return the effective note-type table: defaults + schema overrides.

    ``schema`` wins when given; otherwise lazily loaded from *output_dir*.
    Custom entries in ``conventions.note_types`` override defaults per key
    (shallow: unspecified sub-keys inherit the default for that type, or the
    shared defaults for brand-new types).
    """
    if schema is None:
        schema = _load_schema(output_dir)
    table: Dict[str, Dict[str, Any]] = {
        t: dict(spec) for t, spec in DEFAULT_NOTE_TYPES.items()
    }
    conv = (schema or {}).get("conventions") or {}
    custom = conv.get("note_types")
    if isinstance(custom, dict):
        for raw_key, spec in custom.items():
            t = str(raw_key).strip().lower()
            if not t:
                continue
            base = dict(table.get(t, {
                "freshness_days": 180, "promote_to": "",
                "merge_fields": dict(_DEFAULT_MERGE_FIELDS),
            }))
            if isinstance(spec, dict):
                for k, v in spec.items():
                    base[k] = v
            table[t] = base
    return table


def valid_note_types(
    schema: Optional[dict] = None, output_dir: Optional[Path] = None
) -> Set[str]:
    """Legal note_type values (MCP inputSchema enum source)."""
    return set(load_note_types(schema, output_dir))


def freshness_windows(
    schema: Optional[dict] = None, output_dir: Optional[Path] = None
) -> Dict[str, int]:
    """Per-type stale_after windows derived from the table."""
    out: Dict[str, int] = {}
    for t, spec in load_note_types(schema, output_dir).items():
        try:
            out[t] = int(spec.get("freshness_days", 180))
        except (TypeError, ValueError):
            continue
    return out


def promotion_targets(
    schema: Optional[dict] = None, output_dir: Optional[Path] = None
) -> Dict[str, str]:
    """Per-type promote target page_type ("" = agent's choice)."""
    return {
        t: str(spec.get("promote_to") or "")
        for t, spec in load_note_types(schema, output_dir).items()
    }


def merge_fields_for(
    note_type: str,
    schema: Optional[dict] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Field-merge strategy map for *note_type* (V3 note_merge input)."""
    table = load_note_types(schema, output_dir)
    spec = table.get(str(note_type or "").strip().lower())
    if spec and isinstance(spec.get("merge_fields"), dict):
        merged = dict(_DEFAULT_MERGE_FIELDS)
        merged.update({k: str(v) for k, v in spec["merge_fields"].items()})
        return merged
    return dict(_DEFAULT_MERGE_FIELDS)


def validate_note_types(
    schema: Optional[dict] = None,
    output_dir: Optional[Path] = None,
    accepted: Optional[Set[str]] = None,
) -> List[str]:
    """Sanity check: every note_type accepted by code must be declared.

    With all consumers importing this table the check is structural, but it
    still catches hand-written schema tables that shadow a type with a
    misspelled key (the declared key lands in the enum while handlers route
    to the default). Returns human-readable error strings (empty = OK).
    """
    if accepted is None:
        from codewiki.mcp.tools.distill_conversation import _VALID_NOTE_TYPES
        accepted = set(_VALID_NOTE_TYPES)
    declared = set(load_note_types(schema, output_dir))
    errors: List[str] = []
    missing = accepted - declared
    if missing:
        errors.append(
            "note_types: handler accepts %s but the table does not declare them"
            % sorted(missing)
        )
    return errors
