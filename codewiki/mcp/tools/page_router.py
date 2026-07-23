"""Centralised wiki path routing.

All wiki file paths are resolved through this module so that the structured
directory layout (``wiki/modules/``, ``wiki/entities/``, etc.) is the single
source of truth.

Typical usage::

    from codewiki.mcp.tools.page_router import (
        resolve_wiki_paths,
        resolve_doc_path,
        compute_link_path,
        load_schema,
        get_page_type_dir,
    )
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from codewiki.src.config import (
    WIKI_DIR,
    RAW_SOURCES_DIR,
    NOTES_DIR,
    INDEX_FILENAME,
    LOG_FILENAME,
    OVERVIEW_FILENAME,
    SCHEMA_FILENAME,
    PURPOSE_FILENAME,
    PAGE_TYPE_DIRS,
    WIKI_SYSTEM_FILES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema cache (avoids repeated YAML parsing within a session)
# ---------------------------------------------------------------------------

_schema_cache: Dict[str, dict] = {}


def load_schema(output_dir: str | Path) -> dict:
    """Read and cache *schema.yaml* from *output_dir*.

    Returns ``{}`` if the file does not exist or cannot be parsed.
    """
    od = Path(output_dir)
    key = str(od.resolve())
    if key in _schema_cache:
        return _schema_cache[key]

    schema_path = od / SCHEMA_FILENAME
    if not schema_path.is_file():
        _schema_cache[key] = {}
        return {}

    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        logger.warning("Failed to parse %s", schema_path, exc_info=True)
        data = {}

    _schema_cache[key] = data
    return data


def invalidate_schema_cache(output_dir: str | Path | None = None) -> None:
    """Clear the schema cache.  Pass *output_dir* to clear a single entry."""
    if output_dir is None:
        _schema_cache.clear()
    else:
        _schema_cache.pop(str(Path(output_dir).resolve()), None)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_wiki_paths(output_dir: str | Path, schema: dict | None = None) -> dict:
    """Return a complete mapping of logical names to filesystem paths.

    The returned dict always contains these keys::

        modules, entities, concepts, sources, comparisons, queries,
        notes, raw_sources,
        index, log, overview, schema, purpose

    Directory values are absolute ``Path`` objects.
    """
    od = Path(output_dir).resolve()
    if schema is None:
        schema = load_schema(od)

    wiki = od / WIKI_DIR

    paths: Dict[str, Path] = {
        "modules":      wiki / PAGE_TYPE_DIRS["module"],
        "entities":     wiki / PAGE_TYPE_DIRS["entity"],
        "concepts":     wiki / PAGE_TYPE_DIRS["concept"],
        "sources":      wiki / PAGE_TYPE_DIRS["source"],
        "comparisons":  wiki / PAGE_TYPE_DIRS["comparison"],
        "queries":      wiki / PAGE_TYPE_DIRS["query"],
        "notes":        od / NOTES_DIR,
        "raw_sources":  od / RAW_SOURCES_DIR,
        "index":        wiki / INDEX_FILENAME,
        "log":          wiki / LOG_FILENAME,
        "overview":     wiki / OVERVIEW_FILENAME,
        "schema":       od / SCHEMA_FILENAME,
        "purpose":      od / PURPOSE_FILENAME,
    }

    # Allow schema.page_types to override directory names
    for ptype, config in schema.get("page_types", {}).items():
        if ptype in paths:
            custom_dir = config.get("directory", "")
            if custom_dir:
                paths[ptype] = od / custom_dir

    return paths


def get_page_type_dir(page_type: str, output_dir: str | Path, schema: dict | None = None) -> Path:
    """Return the target directory for *page_type*.

    Resolution order:
    1. ``schema.page_types[<page_type>].directory`` override, if present.
    2. Built-in :data:`PAGE_TYPE_DIRS` mapping (singular page_type ->
       plural subdirectory name under ``wiki/``).
    3. Fall back to ``wiki/modules/`` for unknown types.

    Note: *page_type* is the singular form (``module``, ``entity``,
    ``concept``, ``source``, ``comparison``, ``query``), matching the keys
    of :data:`PAGE_TYPE_DIRS`.
    """
    od = Path(output_dir).resolve()
    if schema is None:
        schema = load_schema(od)

    # 1. schema override (directory relative to output_dir)
    pt_config = schema.get("page_types", {}).get(page_type, {})
    custom_dir = pt_config.get("directory", "") if isinstance(pt_config, dict) else ""
    if custom_dir:
        return od / custom_dir

    # 2. built-in mapping (keyed by singular page_type)
    subdir = PAGE_TYPE_DIRS.get(page_type)
    if subdir:
        return od / WIKI_DIR / subdir

    # 3. fallback
    return od / WIKI_DIR / PAGE_TYPE_DIRS["module"]


def resolve_doc_path(
    filename: str,
    page_type: str,
    output_dir: str | Path,
    schema: dict | None = None,
) -> Path:
    """Resolve the absolute path for a wiki document.

    Routing logic:

    1. If *filename* already contains a directory component (e.g.
       ``wiki/entities/UserService.md``), resolve relative to *output_dir*.
    2. Otherwise look up the target directory from the page type routing
       table and join with *filename*.
    3. Always append ``.md`` if missing.

    Raises ``ValueError`` on directory-traversal attempts.
    """
    od = Path(output_dir).resolve()
    if schema is None:
        schema = load_schema(od)

    # Normalise extension
    if not filename.endswith(".md"):
        filename += ".md"

    # Already has a directory prefix?
    if "/" in filename or "\\" in filename:
        # Normalize separators for prefix checks
        normalized = filename.replace("\\", "/")
        wiki_prefix = WIKI_DIR.rstrip("/") + "/"

        if normalized.startswith(wiki_prefix):
            # Already under wiki/ — use as-is
            candidate = (od / filename).resolve()
        else:
            # Agent passed a bare relative path like "entities/Foo.md"
            # or "modules/auth.md" — force it under wiki/
            candidate = (od / WIKI_DIR / normalized).resolve()
    elif filename == OVERVIEW_FILENAME:
        # Overview always lives at wiki/overview.md (not in a page_type subdir)
        wiki_dir = od / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)
        candidate = (wiki_dir / filename).resolve()
    else:
        target_dir = get_page_type_dir(page_type, od, schema)
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = (target_dir / filename).resolve()

    # Guard against traversal
    if not str(candidate).startswith(str(od)):
        raise ValueError(f"directory traversal detected: {filename}")

    return candidate


def compute_link_path(from_file: Path, to_module: str, output_dir: str | Path) -> str:
    """Compute a relative link from *from_file* to a module doc.

    *to_module* is a module name (e.g. ``"auth_module"``).  The function
    computes the relative path from *from_file*'s parent directory to
    ``wiki/modules/<to_module>.md``.

    Returns a POSIX-style string suitable for markdown links.
    """
    od = Path(output_dir).resolve()
    target = od / WIKI_DIR / PAGE_TYPE_DIRS["module"] / f"{to_module.lower().replace(' ', '_')}.md"

    from_dir = from_file.parent if from_file.is_file() else from_file
    try:
        rel = os.path.relpath(target, from_dir)
    except ValueError:
        # Cross-drive on Windows — fall back to absolute
        rel = str(target)

    return rel.replace("\\", "/")


def compute_depth(file_path: Path, output_dir: str | Path) -> int:
    """Return the directory depth of *file_path* relative to *output_dir*.

    Used by ``_inject_symbol_links`` to compute ``../`` prefixes.

    Examples (with output_dir = ``/repo/repowiki``)::

        wiki/modules/auth.md  → 2
        notes/2026-07-19.md   → 1
        wiki/overview.md      → 1
    """
    od = Path(output_dir).resolve()
    fp = file_path.resolve()
    try:
        rel = fp.relative_to(od)
    except ValueError:
        return 1
    # Depth = number of parent directories (exclude the filename itself)
    return max(len(rel.parts) - 1, 1)


def is_wiki_system_file(path: Path, output_dir: str | Path) -> bool:
    """Return *True* if *path* is a wiki system file that should be excluded
    from indexes and searches.
    """
    return path.name in WIKI_SYSTEM_FILES


def ensure_wiki_dirs(output_dir: str | Path, schema: dict | None = None) -> None:
    """Create all wiki subdirectories if they don't exist yet."""
    paths = resolve_wiki_paths(output_dir, schema)
    for key in ("modules", "entities", "concepts", "sources",
                "comparisons", "queries", "notes", "raw_sources"):
        paths[key].mkdir(parents=True, exist_ok=True)
