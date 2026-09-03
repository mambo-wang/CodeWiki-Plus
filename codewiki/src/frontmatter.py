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
  - §7: ``generated.by`` follows the ``<producer>/<version>`` convention for
        agents and tools (``human:<id>`` for people, ``process:<id>`` for
        pipelines)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# OKF v0.2 standard top-level keys (see okf/SPEC.md §4/§5/§7).
# Anything else written by producers should live under ``metadata``.
_OKF_STANDARD_KEYS = frozenset(
    {
        "type",
        "title",
        "aliases",
        "description",
        "status",
        "verified",
        "stale_after",
        "generated",
        "tags",
        "sources",
    }
)

# Producer-private keys that were historically written at the top level and
# must be folded under ``metadata`` by this helper.  Kept here so lint rules
# and other consumers share one definition of "private".
PRIVATE_FRONTMATTER_KEYS = frozenset(
    {
        "resource",
        "generated_from",
        "category",
        "domain",
        "version",
        "format",
        "decision",
        "decided_at",
        "severity",
        "root_cause",
        "captured_at",
        "content_hash",
        "turn_count",
        "link_to",
        "source_session",
        "keep_raw",
        "task_id",
        # Note-specific fields historically written at the top level (notes/)
        "date",
        "summary",
        "keywords",
        "origin",
        "related_modules",
        "related_components",
        "source_ref",
        "source_refs",
        "chunk_refs",
    }
)


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
    defaults: Dict[str, Any] = {
        "default_stale_days": 90,
        "okf_tags": ["codewiki", "auto-generated"],
    }
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


# ---------------------------------------------------------------------------
# Read side — single parse entry point
# ---------------------------------------------------------------------------
# Before this existed, 13+ hand-rolled parsers (capture/_peek_frontmatter,
# task_manager/_extract_fm, knowledge_loop/_extract_frontmatter, ...) drifted
# on quote handling and metadata depth, producing real bugs (index entries
# with literal quotes slipping past task_id filters). The write side emits
# ``key: <json scalar>`` lines plus a two-space ``metadata:`` block, so a
# line-based parser that json-decodes values round-trips it exactly and stays
# tolerant of hand-edited plain values.

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _decode_scalar(raw: str) -> Any:
    """Decode a frontmatter scalar: JSON forms become typed values, plain
    text stays a string. Surrounding quotes always end up stripped."""
    v = raw.strip()
    if not v:
        return ""
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        pass
    # Quoted scalars that are not valid JSON (YAML single quotes, or
    # hand-written double-quoted text with unescaped content).
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        return inner.replace("''", "'") if v[0] == "'" else inner
    return v


def _block_lines(block: str) -> List[Tuple[int, str]]:
    """(indent, stripped_text) pairs for the significant lines of a block."""
    out: List[Tuple[int, str]] = []
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        out.append((indent, line.strip()))
    return out


def _is_item(s: str) -> bool:
    return s == "-" or s.startswith("- ")


# ``key: value`` inside a "- " item or its continuation lines. The key must
# be a bare identifier (letters/digits/_/-) so quoted strings containing a
# colon (``- "foo: bar"``) never parse as mapping items.
_KEY_VAL_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$")


def _item_text(s: str) -> str:
    return s[2:] if s.startswith("- ") else ""


def _parse_block(lines: List[Tuple[int, str]]) -> Any:
    """Parse the indented block following an empty-value key.

    Returns a list when the block opens with ``- item`` entries, a dict when
    it opens with ``key: value`` lines (nested ``- item`` lists one more
    level deep are folded into their key), or "" for an empty block. This
    covers every shape the write side emits plus the hand-edited YAML block
    forms found in real notes (``tags:`` block lists, ``metadata:`` nested
    dicts, ``verified:`` mapping lists). Unrecognized continuation lines are
    folded into the current item/key as text rather than lost or promoted to
    bogus keys.
    """
    if not lines:
        return ""

    if _is_item(lines[0][1]):
        items: List[Any] = []
        item_indent = lines[0][0]
        cur: Optional[Dict[str, Any]] = None  # mapping item under construction

        def _flush() -> None:
            nonlocal cur
            if cur is not None:
                items.append(cur)
                cur = None

        for indent, s in lines:
            if _is_item(s) and indent == item_indent:
                _flush()
                text = _item_text(s)
                m = _KEY_VAL_RE.match(text)
                if m:
                    # ``- key: value`` opens a mapping item; deeper-indented
                    # ``key: value`` continuation lines extend it (the OKF §5
                    # ``verified:`` list of {by, at} is the canonical shape).
                    val = m.group(2).strip()
                    cur = {m.group(1): _decode_scalar(val)} if val else {}
                else:
                    items.append(_decode_scalar(text))
            elif cur is not None and indent > item_indent:
                m = _KEY_VAL_RE.match(s)
                if m:
                    val = m.group(2).strip()
                    cur[m.group(1)] = _decode_scalar(val) if val else ""
                else:
                    # Non key: value continuation — degrade the mapping to
                    # text folding (same behaviour as plain string items).
                    _flush()
                    items[-1] = f"{items[-1]} {s}" if items else s
            elif cur is not None:
                _flush()
            elif items and not _is_item(s):
                prev = items[-1]
                items[-1] = f"{prev} {s}" if str(prev) else s
        _flush()
        return items

    result: Dict[str, Any] = {}
    pending: Optional[str] = None  # key whose block has not materialized yet
    list_key: Optional[str] = None  # key currently collecting "- " items
    for _, s in lines:
        if _is_item(s):
            item = _decode_scalar(_item_text(s))
            if list_key is not None:
                result[list_key].append(item)
            elif pending is not None:
                result[pending] = [item]
                list_key, pending = pending, None
            continue
        if pending is not None:
            result[pending] = ""  # no items came for the empty-value key
            pending = None
        list_key = None
        key, sep, val = s.partition(":")
        if not sep or not key.strip():
            continue
        key = key.strip()
        val = val.strip()
        if val:
            result[key] = _decode_scalar(val)
        else:
            pending = key
    if pending is not None:
        result[pending] = ""
    return result


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split a document into ``(frontmatter_dict, body)``.

    The single read-side counterpart of :func:`inject_okf_frontmatter`.
    Handles the OKF shapes written across the codebase: top-level
    ``key: value`` scalars (json-encoded or plain), empty-value keys followed
    by ``- item`` block lists (including YAML's same-indent item form) or a
    nested block such as ``metadata:``. Documents without a leading fence
    return ``({}, text)``; unreadable values are skipped, never raised.
    """
    if not text:
        return {}, ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    block, body = m.group(1), text[m.end() :]

    lines = _block_lines(block)
    data: Dict[str, Any] = {}
    i, n = 0, len(lines)
    while i < n:
        indent, s = lines[i]
        if indent > 0 or _is_item(s):
            i += 1  # stray: indented or item line with no owning key
            continue
        key, sep, val = s.partition(":")
        if not sep or not key.strip():
            i += 1
            continue
        key = key.strip()
        val = val.strip()
        if val:
            data[key] = _decode_scalar(val)
            i += 1
            continue
        # Empty value: gather its block — indented lines, plus same-indent
        # "- " items (YAML allows list items at their key's indent).
        j = i + 1
        sub: List[Tuple[int, str]] = []
        while j < n:
            ind2, s2 = lines[j]
            if ind2 > 0 or _is_item(s2):
                sub.append((ind2, s2))
                j += 1
            else:
                break
        data[key] = _parse_block(sub)
        i = j
    return data, body


_PLAIN_UNSAFE_FIRST = set("-[{>\"'|&*!?")
# YAML 1.1 reserved literals: PyYAML (yaml.safe_load) still reads frontmatter
# in knowledge_loop / note_consolidation / doctrine, and it parses a bare
# "on" / "Yes" / "no" as a boolean. Keep such strings quoted.
_YAML_RESERVED = {"y", "n", "yes", "no", "on", "off", "true", "false", "null", "~"}


def format_frontmatter_value(value: Any) -> str:
    """Render *value* as a frontmatter scalar.

    Unambiguous strings are emitted plain (``status: confirmed`` — the
    corpus-wide convention, matching how :func:`inject_okf_frontmatter`
    writes status/type). JSON encoding is reserved for strings that carry
    special characters and for non-string values. A string that would parse
    back as a JSON literal (``true``, ``42``, ``null``...) — or that PyYAML
    would read as a YAML 1.1 boolean/null — stays quoted so every read side
    returns the original string.
    """
    if isinstance(value, str):
        v = value
        plain_ok = (
            bool(v)
            and v == v.strip()
            and v.lower() not in _YAML_RESERVED
            and v[0] not in _PLAIN_UNSAFE_FIRST
            and not any(c in v for c in ":#\n\r\t\"'\\")
        )
        if plain_ok:
            try:
                json.loads(v)
            except (ValueError, TypeError):
                return v
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)
