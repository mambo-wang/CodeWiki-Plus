"""MCP tools: ingest_source + retract_source — third-party document management.

ingest_source: Import third-party documents (PDF, MD, DOCX, HTML) into the
raw/sources/ directory and register them in source_registry.json.

retract_source: Remove a previously imported source document and clean up
references (flag_stale or remove_refs mode).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


def _load_registry(output_dir: Path) -> Dict[str, Any]:
    """Load source_registry.json from output_dir/.meta/. Falls back to root for compat."""
    from codewiki.src.config import SOURCE_REGISTRY_FILENAME, META_DIR
    # Prefer .meta/ location, fallback to root (backward compat)
    meta_path = output_dir / META_DIR / SOURCE_REGISTRY_FILENAME
    root_path = output_dir / SOURCE_REGISTRY_FILENAME
    reg_path = meta_path if meta_path.exists() else root_path
    if not reg_path.exists():
        return {"sources": {}, "version": 1}
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "sources" in data else {"sources": {}, "version": 1}
    except (json.JSONDecodeError, OSError):
        return {"sources": {}, "version": 1}


def _save_registry(output_dir: Path, registry: Dict[str, Any]) -> None:
    """Persist source_registry.json to output_dir/.meta/."""
    from codewiki.src.config import SOURCE_REGISTRY_FILENAME, META_DIR
    meta_dir = output_dir / META_DIR
    meta_dir.mkdir(parents=True, exist_ok=True)
    reg_path = meta_dir / SOURCE_REGISTRY_FILENAME
    reg_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_output_dir(session: Optional[SessionState], arguments: Dict) -> Path:
    """Resolve the output directory from session or arguments."""
    if session:
        return Path(session.output_dir)
    od = arguments.get("output_dir")
    if not od:
        raise ValueError("session_id or output_dir is required.")
    return Path(od).expanduser().resolve()


def handle_ingest_source(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Import a third-party document into the knowledge base.

    The source file is copied to raw/sources/<name> and registered in
    source_registry.json so query_wiki and lint_wiki can track it.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Validate inputs
    source_path = arguments.get("source_path")
    if not source_path:
        return json.dumps({"error": "source_path is required."})

    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        return json.dumps({"error": f"Source file not found: {source_path}"})

    name = arguments.get("name", src.stem)
    source_type = arguments.get("source_type", src.suffix.lstrip(".").lower())
    description = arguments.get("description", "")
    version = arguments.get("version", "")
    related_pages = arguments.get("related_pages", [])

    # SHA-256 content fingerprint for deduplication
    try:
        content_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    except OSError:
        content_hash = ""

    if content_hash:
        registry = _load_registry(output_dir)
        hash_key = f"sha256:{content_hash}"
        for existing_name, info in registry.get("sources", {}).items():
            if isinstance(info, dict) and info.get("content_hash") == hash_key:
                if info.get("status") != "retracted":
                    return json.dumps({
                        "status": "duplicate",
                        "name": name,
                        "existing_name": existing_name,
                        "content_hash": f"sha256:{content_hash[:16]}...",
                        "message": f"Content identical to existing source '{existing_name}'. "
                                   f"Use a different file or retract the existing source first.",
                    }, indent=2, ensure_ascii=False)

    # Ensure raw/sources/ directory exists
    from codewiki.src.config import RAW_SOURCES_DIR
    raw_sources = output_dir / RAW_SOURCES_DIR
    raw_sources.mkdir(parents=True, exist_ok=True)

    # Copy the source file
    dest_name = f"{name}{src.suffix}" if src.suffix else name
    dest_path = raw_sources / dest_name

    # Handle name collision
    if dest_path.exists():
        hash_suffix = src.stat().st_mtime_ns % 0xFFFFFF
        dest_name = f"{name}_{hash_suffix:06x}{src.suffix}"
        dest_path = raw_sources / dest_name

    try:
        shutil.copy2(str(src), str(dest_path))
    except OSError as e:
        return json.dumps({"error": f"Failed to copy source file: {e}"})

    # Register in source_registry.json
    registry = _load_registry(output_dir)
    now = datetime.now().isoformat()
    registry["sources"][name] = {
        "path": str(dest_path.relative_to(output_dir)),
        "original_path": str(src),
        "source_type": source_type,
        "description": description,
        "version": version,
        "imported_at": now,
        "related_pages": related_pages,
        "status": "active",
        "content_hash": f"sha256:{content_hash}" if content_hash else "",
    }
    _save_registry(output_dir, registry)

    # LLM Wiki: update log
    try:
        from codewiki.mcp.tools.wiki_index import append_log
        append_log(str(output_dir), "ingest_source",
                   f"导入外部文档: {name} ({source_type})")
    except Exception:
        pass

    # Update search index for the new source
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index
        build_full_index(output_dir, session=session)
    except Exception as e:
        logger.warning("Search index rebuild failed (non-fatal): %s", e)

    return json.dumps({
        "status": "ingested",
        "name": name,
        "source_type": source_type,
        "stored_at": str(dest_path.relative_to(output_dir)),
        "description": description,
        "version": version,
    }, indent=2, ensure_ascii=False)


def handle_retract_source(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Remove a previously imported source document.

    Two modes:
      - flag_stale: Mark the source as retracted but keep the file (default).
        Pages referencing it will show stale_sources lint warnings.
      - remove_refs: Delete the file and attempt to clean source_refs from
        pages that reference this source.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    name = arguments.get("name")
    if not name:
        return json.dumps({"error": "name is required (the source identifier)."})

    mode = arguments.get("mode", "flag_stale")
    if mode not in ("flag_stale", "remove_refs"):
        return json.dumps({"error": f"Invalid mode '{mode}'. Use 'flag_stale' or 'remove_refs'."})

    dry_run = bool(arguments.get("dry_run", False))

    registry = _load_registry(output_dir)
    if name not in registry["sources"]:
        return json.dumps({"error": f"Source '{name}' not found in registry."})

    source_info = registry["sources"][name]
    source_rel_path = source_info.get("path", "")
    cleaned_refs = 0

    # dry_run: report what would happen without mutating anything
    if dry_run:
        would_clean = _count_source_refs(output_dir, name) if mode == "remove_refs" else 0
        return json.dumps({
            "status": "dry_run",
            "name": name,
            "mode": mode,
            "would_move_to_trash": (mode == "remove_refs" and bool(source_rel_path)),
            "source_file": source_rel_path,
            "would_clean_refs": would_clean,
        }, indent=2, ensure_ascii=False)

    if mode == "remove_refs":
        # Move the source file to .trash/ instead of permanent deletion
        source_abs = output_dir / source_rel_path
        if source_abs.exists():
            try:
                trash_dir = output_dir / ".trash"
                trash_dir.mkdir(parents=True, exist_ok=True)
                dest = trash_dir / source_abs.name
                if dest.exists():
                    dest = trash_dir / f"{source_abs.stem}_{int(datetime.now().timestamp())}{source_abs.suffix}"
                shutil.move(str(source_abs), str(dest))
            except OSError as e:
                logger.warning("Failed to move source file to trash: %s", e)

        # Clean source_refs from wiki pages
        cleaned_refs = _clean_source_refs(output_dir, name)
    else:
        # flag_stale: just mark as retracted, keep the file
        pass

    # Update registry
    source_info["status"] = "retracted"
    source_info["retracted_at"] = datetime.now().isoformat()
    source_info["retract_mode"] = mode
    _save_registry(output_dir, registry)

    # LLM Wiki: update log
    try:
        from codewiki.mcp.tools.wiki_index import append_log
        append_log(str(output_dir), "retract_source",
                   f"撤回外部文档: {name} (mode={mode})")
    except Exception:
        pass

    # Rebuild search index
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index
        build_full_index(output_dir, session=session)
    except Exception:
        pass

    return json.dumps({
        "status": "retracted",
        "name": name,
        "mode": mode,
        "cleaned_refs": cleaned_refs,
    }, indent=2, ensure_ascii=False)


def _count_source_refs(output_dir: Path, source_name: str) -> int:
    """Count how many wiki/notes files reference *source_name* (no mutation)."""
    import re

    pattern = re.compile(
        rf"\[\^src:{re.escape(source_name)}(?::[^\]]*)?\]"
    )
    count = 0
    for search_dir_name in ("wiki", "notes"):
        search_dir = output_dir / search_dir_name
        if not search_dir.is_dir():
            continue
        for md_file in search_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if pattern.search(content) or f'source_ref: "{source_name}"' in content:
                count += 1
    return count


def _clean_source_refs(output_dir: Path, source_name: str) -> int:
    """Remove source_ref annotations referencing *source_name* from all wiki pages.

    Returns the number of files modified.
    """
    import re

    pattern = re.compile(
        rf"\[\^src:{re.escape(source_name)}(?::[^\]]*)?\]"
    )
    cleaned = 0

    # Scan wiki/ subdirectories and notes/
    for search_dir_name in ("wiki", "notes"):
        search_dir = output_dir / search_dir_name
        if not search_dir.is_dir():
            continue
        for md_file in search_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            new_content = pattern.sub("", content)
            if new_content != content:
                md_file.write_text(new_content, encoding="utf-8")
                cleaned += 1

    # Also clean frontmatter source_ref fields
    for search_dir_name in ("wiki", "notes"):
        search_dir = output_dir / search_dir_name
        if not search_dir.is_dir():
            continue
        for md_file in search_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if f'source_ref: "{source_name}"' in content:
                new_content = content.replace(
                    f'source_ref: "{source_name}"', ""
                )
                md_file.write_text(new_content, encoding="utf-8")
                cleaned += 1

    return cleaned
