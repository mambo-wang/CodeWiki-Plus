"""OKF v0.2 frontmatter injection helpers.

Single source of truth for generating OKF-conformant YAML frontmatter
across all wiki write paths (doc_writer, knowledge_loop, capture_conversation,
source_ingest).  Keeps the standard §4/§5 fields at the top level and folds
producer-private fields into a ``metadata`` node so the top level only carries
OKF-standard keys.

OKF v0.2 reference:
  - §4: ``type`` (required), ``title``, ``aliases``
  - §5: lifecycle ``status`` / ``verified`` / ``stale_after``,
        provenance ``generated``
  - §7: ``generated.by`` follows the ``<producer>/<version>`` convention
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# OKF v0.2 standard top-level keys (see okf/SPEC.md §4/§5/§7).
# Anything else written by producers should live under ``metadata``.
_OKF_STANDARD_KEYS = frozenset({
    "type", "title", "aliases", "description",
    "status", "verified", "stale_after", "generated",
})

# Producer-private keys that were historically written at the top level and
# must be folded under ``metadata`` by this helper.  Kept here so lint rules
# and other consumers share one definition of "private".
PRIVATE_FRONTMATTER_KEYS = frozenset({
    "resource", "generated_from", "category", "domain", "version",
    "format", "decision", "decided_at", "severity", "root_cause",
    "captured_at", "content_hash", "turn_count", "link_to",
    "source_session", "keep_raw",
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stale_after_iso(stale_days: Optional[int]) -> Optional[str]:
    """Return ``YYYY-MM-DD`` = today + stale_days, or None when unset."""
    if not stale_days:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=stale_days)).strftime("%Y-%m-%d")


def _default_actor() -> str:
    try:
        from codewiki.src.config import actor_id
        return actor_id()
    except Exception:
        return "codewiki"


def _schema_defaults(output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read ``default_stale_days`` / ``okf_tags`` from the bundle schema.yaml.

    Falls back to the generator's built-in defaults when the schema file is
    missing or unparseable.
    """
    defaults: Dict[str, Any] = {"default_stale_days": 90, "okf_tags": ["codewiki", "auto-generated"]}
    if output_dir is None:
        return defaults
    try:
        from codewiki.src.config import SCHEMA_FILENAME
        import yaml
        schema_path = output_dir / SCHEMA_FILENAME
        if not schema_path.is_file():
            return defaults
        data = yaml.safe_load(schema_path.read_text(encoding="utf-8", errors="replace")) or {}
        conventions = data.get("conventions", {}) or {}
        if conventions.get("default_stale_days") is not None:
            defaults["default_stale_days"] = int(conventions["default_stale_days"])
        if conventions.get("okf_tags") is not None:
            defaults["okf_tags"] = list(conventions["okf_tags"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("schema defaults unavailable: %s", exc)
    return defaults


def inject_okf_frontmatter(
    body: str,
    *,
    type_: str,
    title: str,
    output_dir: Optional[Path] = None,
    description: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    status: str = "draft",
    stale_days: Optional[int] = None,
    okf_tags: Optional[List[str]] = None,
    top_level_extra: Optional[Dict[str, Any]] = None,
    metadata_extra: Optional[Dict[str, Any]] = None,
    actor: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> str:
    """Build an OKF v0.2 YAML frontmatter block and prepend it to *body*.

    Standard fields (type/title/description/aliases/status/stale_after/
    generated) are emitted at the top level.  ``top_level_extra`` keeps
    producer fields at the top level too (for consumers that do simple
    line-based parsing, e.g. distill_conversation reads ``link_to`` /
    ``keep_raw`` / ``content_hash`` with ``key: value`` splitting).
    ``metadata_extra`` is folded under a nested ``metadata`` node so the
    OKF standard top level stays clean.  Missing ``stale_days`` /
    ``okf_tags`` fall back to the bundle's schema.yaml conventions
    (default 90 days, tags ``["codewiki", "auto-generated"]``).
    """
    defaults = _schema_defaults(output_dir)
    if stale_days is None:
        stale_days = defaults["default_stale_days"]
    if okf_tags is None:
        okf_tags = list(defaults["okf_tags"])

    actor = actor or _default_actor()
    now_iso = now_iso or _utc_now_iso()

    lines: List[str] = []
    lines.append(f"type: {type_}")
    lines.append(f"title: {json.dumps(title, ensure_ascii=False)}")
    if description is not None:
        lines.append(f"description: {json.dumps(description, ensure_ascii=False)}")
    if aliases:
        lines.append(f"aliases: {json.dumps(aliases, ensure_ascii=False)}")
    if status:
        lines.append(f"status: {status}")
    stale = _stale_after_iso(stale_days)
    if stale:
        lines.append(f"stale_after: {stale}")
    lines.append(f"generated: {{ by: {actor}, at: {now_iso} }}")
    if okf_tags:
        lines.append(f"tags: {json.dumps(okf_tags, ensure_ascii=False)}")
    if top_level_extra:
        # Producer fields that downstream line-parsers depend on stay flat.
        for key in sorted(top_level_extra):
            lines.append(f"{key}: {json.dumps(top_level_extra[key], ensure_ascii=False)}")
    if metadata_extra:
        # Fold producer-private fields under a nested metadata node.
        lines.append("metadata:")
        for key in sorted(metadata_extra):
            lines.append(f"  {key}: {json.dumps(metadata_extra[key], ensure_ascii=False)}")

    fm = "---\n" + "\n".join(lines) + "\n---\n\n"
    return fm + body


def is_okf_standard_key(key: str) -> bool:
    """True when *key* is an OKF v0.2 standard top-level field."""
    return key in _OKF_STANDARD_KEYS


def fold_private_metadata(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    """Move producer-private keys from the top level into ``metadata``.

    Used by lint / migration tooling to normalise legacy documents without
    dropping their data.  ``aliases`` is part of OKF §4 so it always stays
    at the top level.
    """
    normalized = dict(frontmatter)
    extra = dict(normalized.pop("metadata", None) or {})
    for key in list(normalized):
        if key not in _OKF_STANDARD_KEYS:
            extra[key] = normalized.pop(key)
    if extra:
        normalized["metadata"] = extra
    return normalized
