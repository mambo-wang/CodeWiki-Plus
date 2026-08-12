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
from datetime import datetime, timezone
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
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    if od:
        return Path(od).expanduser().resolve()
    # Fallback: derive from repo_path
    rp = arguments.get("repo_path")
    if rp:
        return Path(rp).expanduser().resolve() / "repowiki"
    raise ValueError("output_dir or repo_path is required (or pass an active session).")


def _okf_source_entry(output_dir: Path, name: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """Map a source_registry.json entry to an OKF v0.2 ``sources`` item (§5.1)."""
    entry: Dict[str, Any] = {"id": name}
    rel_path = info.get("path", "")
    if rel_path:
        entry["resource"] = rel_path.replace("\\", "/")
    elif info.get("original_path"):
        entry["resource"] = info["original_path"]
    if info.get("description"):
        entry["title"] = info["description"]
    imported_at = info.get("imported_at", "")
    if imported_at:
        entry["last_modified"] = imported_at[:10]  # YYYY-MM-DD
    return entry


def _merge_okf_sources_entry(page_path: Path, entry: Dict[str, Any]) -> None:
    """Merge one OKF ``sources`` entry into a page's frontmatter (idempotent).

    Uses a YAML round-trip so list-of-mapping values stay well-formed.
    Existing entries with the same ``id`` are left untouched.
    """
    try:
        content = page_path.read_text(encoding="utf-8")
    except OSError:
        return
    if not content.startswith("---"):
        return  # pages without frontmatter are handled elsewhere
    end = content.find("---", 3)
    if end < 0:
        return
    try:
        import yaml
        data = yaml.safe_load(content[3:end])
        if not isinstance(data, dict):
            return
        sources = data.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        if not isinstance(sources, list):
            sources = []
        if any(isinstance(s, dict) and s.get("id") == entry.get("id") for s in sources):
            return  # already present
        sources.append(entry)
        data["sources"] = sources
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        page_path.write_text(f"---\n{new_fm}---{content[end + 3:]}", encoding="utf-8")
    except Exception as e:
        logger.debug("OKF sources merge skipped for %s: %s", page_path, e)


def _ensure_source_frontmatter(dest_path: Path, name: str, description: str, output_dir: Optional[Path] = None) -> None:
    """Ensure an ingested raw/sources markdown file carries OKF frontmatter.

    OKF v0.2 §11 conformance applies to every non-reserved .md in the
    bundle, including raw/sources/.  Only .md files are affected; binary
    formats are outside the spec's scope.

    ``stale_after`` / ``tags`` fall back to the bundle's schema.yaml
    conventions when *output_dir* is provided.
    """
    if dest_path.suffix.lower() != ".md":
        return
    try:
        content = dest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if content.startswith("---"):
        return  # keep whatever the source document already declares
    from codewiki.src.frontmatter import inject_okf_frontmatter
    fm = inject_okf_frontmatter(
        content,
        type_="Source",
        title=name,
        output_dir=output_dir,
        description=description or name,
        status="stable",
    )
    try:
        dest_path.write_text(fm, encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to add OKF frontmatter to %s: %s", dest_path, e)


def _inject_source_refs(output_dir: Path, related_pages: List[str], source_name: str) -> None:
    """Inject source_ref into the YAML frontmatter of related wiki pages.

    For each page in *related_pages*, resolves the file path relative to
    *output_dir* and adds ``source_ref: "<source_name>"`` to its frontmatter.
    If the page already has a ``source_refs`` list, appends to it instead.
    Pages that cannot be found or read are silently skipped.

    OKF v0.2: additionally merges a ``sources`` entry (§5.1) into the page
    frontmatter so provenance is readable by any OKF consumer.
    """
    registry = _load_registry(output_dir)
    info = registry.get("sources", {}).get(source_name, {})
    okf_entry = _okf_source_entry(output_dir, source_name, info) if info else {"id": source_name}

    for page_ref in related_pages:
        # Resolve page path: try as-is relative to output_dir, then in wiki/
        page_path = output_dir / page_ref
        if not page_path.exists():
            page_path = output_dir / "wiki" / page_ref
        if not page_path.exists():
            logger.debug("Related page not found, skipping source_ref injection: %s", page_ref)
            continue

        try:
            content = page_path.read_text(encoding="utf-8")
        except OSError:
            continue

        source_ref_line = f'source_ref: "{source_name}"'

        if content.startswith("---"):
            # Has existing frontmatter — find the closing delimiter
            end_idx = content.find("---", 3)
            if end_idx < 0:
                continue
            frontmatter = content[3:end_idx]
            rest = content[end_idx:]  # includes closing "---" and body

            # Check if source_refs list already exists
            if "source_refs:" in frontmatter:
                # Append to existing source_refs list (YAML list item)
                # Find the source_refs line and insert after its block
                lines = frontmatter.split("\n")
                insert_idx = None
                for i, line in enumerate(lines):
                    if line.strip().startswith("source_refs:"):
                        # Find end of the list (next non-indented, non-list line)
                        insert_idx = i + 1
                        while insert_idx < len(lines) and (
                            lines[insert_idx].startswith("  ") or lines[insert_idx].strip().startswith("- ")
                        ):
                            insert_idx += 1
                        break
                if insert_idx is not None:
                    # Avoid duplicate
                    if f'- "{source_name}"' not in frontmatter and f"- {source_name}" not in frontmatter:
                        lines.insert(insert_idx, f'  - "{source_name}"')
                        frontmatter = "\n".join(lines)
            else:
                # Add source_ref field to frontmatter
                frontmatter = frontmatter.rstrip("\n") + f"\n{source_ref_line}\n"

            new_content = "---" + frontmatter + rest
        else:
            # No frontmatter — create one
            new_content = f"---\n{source_ref_line}\n---\n\n" + content

        if new_content != content:
            try:
                page_path.write_text(new_content, encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to inject source_ref into %s: %s", page_path, e)

        # OKF v0.2 §5.1: dual-write the `sources` frontmatter entry
        _merge_okf_sources_entry(page_path, okf_entry)


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
    source_path = arguments.get("source_ref")
    if not source_path:
        return json.dumps({"error": "source_ref is required."})

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
    # Ensure .meta/ exists for registry and search index
    (output_dir / ".meta").mkdir(parents=True, exist_ok=True)

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

    # OKF v0.2 §11: raw/sources/*.md are part of the bundle — ensure frontmatter
    _ensure_source_frontmatter(dest_path, name, description, output_dir)

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

    # Write source_ref back to related pages' frontmatter so that
    # retract_source(mode=remove_refs) can find and clean them later.
    if related_pages:
        _inject_source_refs(output_dir, related_pages, name)

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


def _body_ref_patterns(source_name: str):
    """Regexes for in-body references that retract must clean."""
    import re
    return (
        # Legacy annotation: [^src:name] / [^src:name:range]
        re.compile(rf"\[\^src:{re.escape(source_name)}(?::[^\]]*)?\]"),
        # OKF v0.2 per-claim attribution marker: [^name]
        re.compile(rf"\[\^{re.escape(source_name)}\]"),
    )


def _frontmatter_mentions(content: str, source_name: str) -> bool:
    """Whether the frontmatter references *source_name* in any OKF/legacy form.

    Checks ``source_ref`` (flat field), ``source_refs`` (list) and the OKF
    v0.2 ``sources`` entries (id match).  Parsing goes through YAML so any
    quoting style produced by frontmatter re-dumps is handled uniformly.
    """
    if not content.startswith("---"):
        return False
    end = content.find("---", 3)
    if end < 0:
        return False
    fm = content[3:end]
    try:
        import yaml
        data = yaml.safe_load(fm)
    except Exception:
        data = None
    if isinstance(data, dict):
        if str(data.get("source_ref", "")) == source_name:
            return True
        refs = data.get("source_refs")
        if isinstance(refs, list) and any(str(x) == source_name for x in refs):
            return True
        sources = data.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        if isinstance(sources, list) and any(
                isinstance(s, dict) and s.get("id") == source_name for s in sources):
            return True
        return False
    # YAML parse failed → permissive textual fallback
    import re
    return bool(re.search(
        rf"^source_ref:\s*[\"']?{re.escape(source_name)}[\"']?\s*$",
        fm, re.MULTILINE))


def _count_source_refs(output_dir: Path, source_name: str) -> int:
    """Count how many wiki/notes files reference *source_name* (no mutation).

    Shares its detection semantics with :func:`_clean_source_refs` so the
    ``dry_run`` preview always matches what the real run cleans.
    """
    patterns = _body_ref_patterns(source_name)
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
            if (any(p.search(content) for p in patterns)
                    or _frontmatter_mentions(content, source_name)):
                count += 1
    return count


def _strip_okf_sources_entry(md_file: Path, source_name: str) -> bool:
    """Remove the ``sources`` entry with id == source_name from frontmatter.

    Returns True when the file was modified.
    """
    try:
        content = md_file.read_text(encoding="utf-8")
    except OSError:
        return False
    if not content.startswith("---") or "\nsources:" not in content[:2000]:
        return False
    end = content.find("---", 3)
    if end < 0:
        return False
    try:
        import yaml
        data = yaml.safe_load(content[3:end])
        if not isinstance(data, dict):
            return False
        sources = data.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        if not isinstance(sources, list):
            return False
        kept = [s for s in sources
                if not (isinstance(s, dict) and s.get("id") == source_name)]
        if len(kept) == len(sources):
            return False
        if kept:
            data["sources"] = kept
        else:
            data.pop("sources", None)
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        md_file.write_text(f"---\n{new_fm}---{content[end + 3:]}", encoding="utf-8")
        return True
    except Exception:
        return False


def _strip_source_ref_fields(md_file: Path, source_name: str) -> bool:
    """Remove ``source_ref`` / ``source_refs`` entries naming *source_name*.

    Goes through a YAML round-trip so quoting differences introduced by
    frontmatter re-dumps (``source_ref: name`` vs ``source_ref: "name"``)
    are all handled uniformly.  Returns True when the file was modified.
    """
    try:
        content = md_file.read_text(encoding="utf-8")
    except OSError:
        return False
    if not content.startswith("---"):
        return False
    end = content.find("---", 3)
    if end < 0:
        return False
    try:
        import yaml
        data = yaml.safe_load(content[3:end])
        if not isinstance(data, dict):
            return False
        changed = False
        if str(data.get("source_ref", "")) == source_name:
            data.pop("source_ref", None)
            changed = True
        refs = data.get("source_refs")
        if isinstance(refs, list):
            kept = [x for x in refs if str(x) != source_name]
            if len(kept) != len(refs):
                changed = True
                if kept:
                    data["source_refs"] = kept
                else:
                    data.pop("source_refs", None)
        if not changed:
            return False
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        md_file.write_text(f"---\n{new_fm}---{content[end + 3:]}", encoding="utf-8")
        return True
    except Exception:
        return False


def _clean_source_refs(output_dir: Path, source_name: str) -> int:
    """Remove all references to *source_name* from wiki pages and notes.

    Cleans the legacy ``[^src:name:range]`` annotations, the OKF v0.2
    attribution forms (``[^name]`` footnote markers/definitions and
    ``sources`` frontmatter entries keyed by id) and the flat
    ``source_ref`` / ``source_refs`` frontmatter fields.

    Returns the number of files modified.
    """
    import re

    legacy_pat, okf_marker = _body_ref_patterns(source_name)
    okf_def = re.compile(rf"^\[\^{re.escape(source_name)}\]:.*$\n?", re.MULTILINE)
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
            new_content = okf_def.sub("", okf_marker.sub("", legacy_pat.sub("", content)))
            body_changed = new_content != content
            if body_changed:
                md_file.write_text(new_content, encoding="utf-8")
            stripped_fields = _strip_source_ref_fields(md_file, source_name)
            stripped_sources = _strip_okf_sources_entry(md_file, source_name)
            if body_changed or stripped_fields or stripped_sources:
                cleaned += 1

    return cleaned
