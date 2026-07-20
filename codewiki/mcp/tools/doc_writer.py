"""MCP tools: write_doc_file + edit_doc_file.

These tools create and edit markdown documentation files in the output
directory, with automatic Mermaid diagram validation after every write.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.file_param import read_param
from codewiki.mcp.tools.page_router import (
    resolve_doc_path,
    compute_link_path,
    compute_depth,
    load_schema,
)

logger = logging.getLogger(__name__)

# Max edit history entries per file (prevent unbounded memory growth)
_MAX_HISTORY_PER_FILE = 20

# Pattern for inline source-reference annotations: [^src:<name>:<start>-<end>]
_SOURCE_REF_PATTERN = re.compile(r"\[\^src:([^:\]]+):(\d+-\d+)\]")


def _extract_source_refs(content: str) -> tuple[list[str], list[str]]:
    """Extract source-file references from document body.

    Scans for ``[^src:<name>:<start>-<end>]`` annotations and returns a
    ``(source_refs, chunk_refs)`` tuple where *source_refs* is the sorted
    unique set of source names and *chunk_refs* is the list of
    ``<name>:<range>`` strings (in order of appearance).
    """
    source_refs: set[str] = set()
    chunk_refs: list[str] = []
    for match in _SOURCE_REF_PATTERN.finditer(content):
        source_name, line_range = match.groups()
        source_refs.add(source_name)
        chunk_refs.append(f"{source_name}:{line_range}")
    return sorted(source_refs), chunk_refs


def _resync_source_refs(content: str) -> str:
    """Re-parse ``[^src:...]`` refs from body and sync frontmatter fields.

    Rewrites (or inserts) the ``source_refs`` and ``chunk_refs`` lines inside
    an existing YAML frontmatter block so they always reflect the current
    body.  Returns *content* unchanged when there is no frontmatter block.
    """
    if not content.startswith("---"):
        return content
    # Locate the closing delimiter of the frontmatter block
    lines = content.split("\n")
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return content

    body = "\n".join(lines[close_idx + 1:])
    source_refs, chunk_refs = _extract_source_refs(body)

    # Drop any existing source_refs/chunk_refs lines within the frontmatter
    fm_lines = [
        ln for ln in lines[1:close_idx]
        if not ln.startswith("source_refs:") and not ln.startswith("chunk_refs:")
    ]
    if source_refs:
        refs_str = ", ".join(f'"{r}"' for r in source_refs)
        fm_lines.append(f"source_refs: [{refs_str}]")
    if chunk_refs:
        chunks_str = ", ".join(f'"{c}"' for c in chunk_refs)
        fm_lines.append(f"chunk_refs: [{chunks_str}]")

    rebuilt = ["---"] + fm_lines + ["---"] + lines[close_idx + 1:]
    return "\n".join(rebuilt)


def _is_within(path: Path, base: Path) -> bool:
    """Return True if *path* resolves to somewhere inside *base*."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_doc_path(
    session: SessionState,
    filename: str,
    page_type: str = "module",
) -> Path | None:
    """Resolve *filename* within session.output_dir using the page type routing table.

    Routes the file to the correct wiki subdirectory based on *page_type*
    (e.g. ``wiki/entities/`` for ``page_type="entity"``).  Guards against
    directory traversal.  Returns ``None`` if the path escapes output_dir.
    """
    schema = load_schema(session.output_dir)
    try:
        return resolve_doc_path(filename, page_type, session.output_dir, schema)
    except ValueError:
        return None


def _build_okf_frontmatter(
    session: SessionState,
    filename: str,
    content: str,
    page_type: str = "module",
    frontmatter_extra: dict | None = None,
) -> str | None:
    """Build OKF-compliant YAML frontmatter from session metadata.

    Returns the frontmatter string (including --- delimiters) or None if
    the content already has frontmatter.

    *page_type* controls the ``type`` field:
      module → Module, entity → Entity, concept → Concept,
      source → Source, comparison → Comparison, query → Query.

    *frontmatter_extra* keys (aliases, category, origin, severity, etc.)
    are merged into the frontmatter.
    """
    # Skip if content already has frontmatter
    if content.startswith("---"):
        return None

    mod_name = filename.replace(".md", "").replace("_", " ").title()
    repo_name = Path(session.repo_path).name if session.repo_path else "unknown"

    # Determine type from page_type (capitalised)
    _TYPE_MAP = {
        "module": "Module",
        "entity": "Entity",
        "concept": "Concept",
        "source": "Source",
        "comparison": "Comparison",
        "query": "Query",
    }
    doc_type = _TYPE_MAP.get(page_type, page_type.capitalize())

    # Extract description from first paragraph of content
    description = ""
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("```"):
            continue
        if line.startswith("---"):
            continue
        description = line[:200]
        break

    # Get source files from module tree (only for module type)
    source_files: list[str] = []
    if page_type == "module":
        module_tree = session.module_tree or {}
        target_mod = filename.replace(".md", "").lower().replace(" ", "_")

        def _find_sources(tree: dict, target: str) -> list[str]:
            for name, info in tree.items():
                if name.lower().replace(" ", "_") == target:
                    components = info.get("components", [])
                    files = set()
                    for comp_id in components:
                        if "::" in comp_id:
                            files.add(comp_id.split("::")[0])
                    return sorted(files)[:5]
                children = info.get("children", {})
                if isinstance(children, dict):
                    found = _find_sources(children, target)
                    if found:
                        return found
            return []

        source_files = _find_sources(module_tree, target_mod)

    # Build resource URI
    if source_files:
        resource = f"file://{source_files[0]}"
        if len(source_files) > 1:
            resource += f" (+{len(source_files) - 1} more)"
    else:
        resource = f"repo://{repo_name}"

    # Build tags from module name and schema
    tags = [repo_name]
    if doc_type == "Module":
        tags.append(filename.replace(".md", "").lower().replace(" ", "_"))

    # Try to read additional tags from schema.yaml
    schema = load_schema(session.output_dir)
    if schema.get("conventions", {}).get("okf_tags"):
        tags.extend(schema["conventions"]["okf_tags"])

    # Build frontmatter lines
    fm_parts = [
        "---",
        f"type: {doc_type}",
        f"title: {mod_name}",
        f'description: "{description}"' if description else f"description: {mod_name}",
        f"resource: {resource}",
        f"tags: [{', '.join(tags)}]",
    ]

    # Merge frontmatter_extra
    extra = frontmatter_extra or {}
    if extra.get("aliases"):
        aliases_str = ", ".join(f'"{a}"' for a in extra["aliases"])
        fm_parts.append(f"aliases: [{aliases_str}]")
    # Type-specific fields from extra
    for key in ("category", "domain", "origin", "version", "format",
                "decision", "status", "decided_at", "severity", "root_cause"):
        if key in extra and extra[key]:
            val = extra[key]
            fm_parts.append(f'{key}: "{val}"' if isinstance(val, str) else f"{key}: {val}")

    # Auto-extract source references from body ([^src:name:start-end])
    source_refs, chunk_refs = _extract_source_refs(content)
    if source_refs:
        refs_str = ", ".join(f'"{r}"' for r in source_refs)
        fm_parts.append(f"source_refs: [{refs_str}]")
    if chunk_refs:
        chunks_str = ", ".join(f'"{c}"' for c in chunk_refs)
        fm_parts.append(f"chunk_refs: [{chunks_str}]")

    fm_parts.append("---")
    fm_parts.append("")
    return "\n".join(fm_parts)


def _inject_frontmatter(
    session: SessionState,
    filename: str,
    content: str,
    page_type: str = "module",
    frontmatter_extra: dict | None = None,
) -> str:
    """Prepend OKF frontmatter to content if not already present and enabled in schema."""
    schema = load_schema(session.output_dir)
    if not schema.get("conventions", {}).get("okf_frontmatter", True):
        return content

    frontmatter = _build_okf_frontmatter(
        session, filename, content,
        page_type=page_type,
        frontmatter_extra=frontmatter_extra,
    )
    if frontmatter:
        return frontmatter + content
    return content


def _ensure_parent_dirs(path: Path) -> None:
    """Create parent directories if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


async def _validate_mermaid(file_path: str, relative_path: str) -> str:
    """Run Mermaid validation and return the result string."""
    try:
        from codewiki.src.be.utils import validate_mermaid_diagrams
        return await validate_mermaid_diagrams(file_path, relative_path)
    except Exception as e:
        return f"Mermaid validation skipped: {e}"


def _save_history(session: SessionState, doc_path: Path, content: str) -> None:
    """Append *content* to edit history for *doc_path*, capped at _MAX_HISTORY_PER_FILE."""
    history = session.registry.get("file_history")
    if history is None:
        history = {}
    elif isinstance(history, str):
        history = json.loads(history)
    key = str(doc_path)
    entry = history.setdefault(key, [])
    entry.append(content)
    # Trim to last N entries
    if len(entry) > _MAX_HISTORY_PER_FILE:
        del entry[: len(entry) - _MAX_HISTORY_PER_FILE]
    session.registry["file_history"] = history  # keep as native dict


def _inject_crosslinks(
    session: SessionState,
    filename: str,
    doc_path: Path,
) -> dict | None:
    """Append a crosslinks section to *doc_path* if auto_crosslink is enabled.

    Returns a summary dict if crosslinks were injected, None otherwise.
    """
    schema = load_schema(session.output_dir)
    if not schema.get("conventions", {}).get("auto_crosslink", False):
        return None

    module_tree = session.module_tree
    if not module_tree:
        return None

    # Derive module name from filename (e.g. "auth_module.md" -> "auth_module")
    mod_name = filename.replace(".md", "")

    # Find this module in module_tree and get its components
    module_components: list[str] = []

    def _find_components(tree: dict, target: str) -> list[str]:
        for name, info in tree.items():
            if name.lower().replace(" ", "_") == target.lower().replace(" ", "_"):
                return info.get("components", [])
            children = info.get("children", {})
            if isinstance(children, dict):
                found = _find_components(children, target)
                if found:
                    return found
        return []

    module_components = _find_components(module_tree, mod_name)
    if not module_components:
        return None

    # Compute module-level dependencies
    depends_on_modules: set[str] = set()
    depended_by_modules: set[str] = set()

    def _comp_to_module(comp_id: str) -> str | None:
        for name, info in module_tree.items():
            if comp_id in info.get("components", []):
                return name
            children = info.get("children", {})
            if isinstance(children, dict):
                for cname, cinfo in children.items():
                    if comp_id in cinfo.get("components", []):
                        return cname
        return None

    for comp_id in module_components:
        node = session.components.get(comp_id)
        if node is None:
            continue
        deps = getattr(node, "depends_on", None) or set()
        for dep_id in deps:
            dep_mod = _comp_to_module(dep_id)
            if dep_mod and dep_mod != mod_name:
                depends_on_modules.add(dep_mod)

    # Reverse: who depends on our components
    for comp_id, node in session.components.items():
        if comp_id in module_components:
            continue
        deps = getattr(node, "depends_on", None) or set()
        if deps & set(module_components):
            src_mod = _comp_to_module(comp_id)
            if src_mod and src_mod != mod_name:
                depended_by_modules.add(src_mod)

    if not depends_on_modules and not depended_by_modules:
        return None

    # Build crosslinks section
    lines = ["\n<!-- crosslinks (auto-generated) -->", "## Related Modules"]
    if depends_on_modules:
        links = ", ".join(
            f"[{m}]({compute_link_path(doc_path, m, session.output_dir)})"
            for m in sorted(depends_on_modules)
        )
        lines.append(f"- Depends on: {links}")
    if depended_by_modules:
        links = ", ".join(
            f"[{m}]({compute_link_path(doc_path, m, session.output_dir)})"
            for m in sorted(depended_by_modules)
        )
        lines.append(f"- Used by: {links}")

    crosslink_text = "\n".join(lines) + "\n"

    # Replace existing crosslinks block or append
    content = doc_path.read_text(encoding="utf-8")
    marker = "<!-- crosslinks (auto-generated) -->"
    if marker in content:
        # Replace from marker to end of file
        idx = content.index(marker)
        content = content[:idx] + crosslink_text
    else:
        content = content.rstrip() + "\n\n" + crosslink_text

    doc_path.write_text(content, encoding="utf-8")

    return {
        "depends_on": sorted(depends_on_modules),
        "depended_by": sorted(depended_by_modules),
        "injected": True,
    }


def _collect_wiki_terms(output_dir: Path, exclude: Path | None = None) -> dict[str, str]:
    """Build a {term_lower: slug} map from existing wiki pages.

    Scans ``wiki/**/*.md`` frontmatter for ``slug``/``title``/``aliases`` so
    plain-text mentions can be turned into ``[[slug|display]]`` wiki-links.
    """
    terms: dict[str, str] = {}
    wiki_dir = output_dir / "wiki"
    if not wiki_dir.is_dir():
        return terms
    for md_file in wiki_dir.rglob("*.md"):
        if exclude is not None and md_file == exclude:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        lines = text.split("\n")
        slug = md_file.stem
        title = None
        aliases: list[str] = []
        for ln in lines[1:]:
            if ln.strip() == "---":
                break
            if ln.startswith("slug:"):
                slug = ln.split(":", 1)[1].strip().strip('"')
            elif ln.startswith("title:"):
                title = ln.split(":", 1)[1].strip().strip('"')
            elif ln.startswith("aliases:"):
                raw = ln.split(":", 1)[1].strip().strip("[]")
                aliases = [a.strip().strip('"') for a in raw.split(",") if a.strip()]
        for term in filter(None, [title, *aliases]):
            if len(term) >= 3:  # avoid noisy tiny terms
                terms[term.lower()] = slug
    return terms


def _inject_wiki_links(content: str, terms: dict[str, str]) -> str:
    """Convert first plain-text mention of each known term into ``[[slug|term]]``.

    Skips fenced code blocks, existing links, and the frontmatter block.
    """
    if not terms:
        return content

    # Separate frontmatter so we never rewrite it
    prefix = ""
    body = content
    if content.startswith("---"):
        parts = content.split("\n")
        for i in range(1, len(parts)):
            if parts[i].strip() == "---":
                prefix = "\n".join(parts[: i + 1]) + "\n"
                body = "\n".join(parts[i + 1:])
                break

    # Sort longer terms first to prefer specific matches
    sorted_terms = sorted(terms.items(), key=lambda kv: len(kv[0]), reverse=True)

    lines = body.split("\n")
    in_code = False
    linked: set[str] = set()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or stripped.startswith("#"):
            continue
        for term_lower, slug in sorted_terms:
            if term_lower in linked:
                continue
            # Word-boundary, case-insensitive, not already inside [[ ]] or [ ]( )
            pattern = re.compile(
                rf"(?<!\[)(?<!\w)({re.escape(term_lower)})(?!\w)(?!\]\()(?![^\[]*\]\])",
                re.IGNORECASE,
            )
            m = pattern.search(line)
            if m:
                matched = m.group(1)
                line = line[: m.start()] + f"[[{slug}|{matched}]]" + line[m.end():]
                lines[idx] = line
                linked.add(term_lower)
    return prefix + "\n".join(lines)


async def handle_write_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Create a new documentation file in the output directory."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    filename = arguments["filename"]
    page_type = arguments.get("page_type", "module")
    frontmatter_extra = arguments.get("frontmatter_extra") or None

    doc_path = _safe_doc_path(session, filename, page_type=page_type)
    if doc_path is None:
        return json.dumps({"error": "Filename escapes output directory."})

    content = read_param(arguments, "content")
    if content is None:
        return json.dumps({"error": "content or content_file is required."}, ensure_ascii=False)

    _ensure_parent_dirs(doc_path)

    if doc_path.exists():
        return json.dumps({
            "error": f"File already exists: {filename}. Use edit_doc_file to modify it."
        })

    # OKF: inject YAML frontmatter from session metadata
    content = _inject_frontmatter(
        session, filename, content,
        page_type=page_type,
        frontmatter_extra=frontmatter_extra,
    )

    doc_path.write_text(content, encoding="utf-8")
    session.docs_written += 1

    # Mermaid validation
    mermaid_result = await _validate_mermaid(str(doc_path), filename)

    # LLM Wiki: wiki-link injection ([[slug|display]]) opt-in via schema.wiki_link_syntax
    try:
        schema = load_schema(session.output_dir)
        if schema.get("wiki_link_syntax", False):
            terms = _collect_wiki_terms(Path(session.output_dir), exclude=doc_path)
            raw = doc_path.read_text(encoding="utf-8")
            linked = _inject_wiki_links(raw, terms)
            if linked != raw:
                doc_path.write_text(linked, encoding="utf-8")
    except Exception:
        pass

    # LLM Wiki: crosslink injection (opt-in via schema.yaml auto_crosslink)
    crosslink_info = _inject_crosslinks(session, filename, doc_path)

    # LLM Wiki: inject source-file links for CamelCase symbols
    try:
        from codewiki.mcp.tools.knowledge_loop import _inject_symbol_links
        raw = doc_path.read_text(encoding="utf-8")
        depth = compute_depth(doc_path, session.output_dir)
        # symbol_map paths are relative to repo root; add extra levels to
        # escape output_dir (e.g. docs/) up to the repository root.
        try:
            extra = len(Path(session.output_dir).resolve().relative_to(
                Path(session.repo_path).resolve()).parts)
        except (ValueError, AttributeError):
            extra = 0
        linked = _inject_symbol_links(raw, Path(session.output_dir), depth=depth + extra, session=session)
        if linked != raw:
            doc_path.write_text(linked, encoding="utf-8")
    except Exception:
        pass

    result = {
        "status": "created",
        "path": str(doc_path),
        "filename": filename,
        "page_type": page_type,
        "lines": content.count("\n") + 1,
        "mermaid_validation": mermaid_result,
    }
    if crosslink_info:
        result["crosslinks"] = crosslink_info

    # LLM Wiki: update index.md and log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(session.output_dir, "write_doc_file", f"创建 {filename}")
        rebuild_index(session.output_dir)
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)

    # Update BM25 search index (SQLite-backed when session available)
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(session.output_dir, doc_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)

    return json.dumps(result, indent=2, ensure_ascii=False)


async def handle_edit_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Edit an existing documentation file (str_replace, insert, or undo)."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    filename = arguments["filename"]
    page_type = arguments.get("page_type", "module")
    doc_path = _safe_doc_path(session, filename, page_type=page_type)
    if doc_path is None:
        return json.dumps({"error": "Filename escapes output directory."})

    command = arguments["command"]

    if command == "undo":
        # Undo via registry history
        history = session.registry.get("file_history", {})
        if isinstance(history, str):
            history = json.loads(history)
        path_history = history.get(str(doc_path), [])
        if not path_history:
            return json.dumps({"error": f"No edit history found for {filename}."})
        old_content = path_history.pop()
        history[str(doc_path)] = path_history
        session.registry["file_history"] = history
        doc_path.write_text(old_content, encoding="utf-8")

        # Validate Mermaid after undo
        mermaid_result = await _validate_mermaid(str(doc_path), filename)

        # LLM Wiki: update log.md (undo changes file content)
        try:
            from codewiki.mcp.tools.wiki_index import append_log
            append_log(session.output_dir, "edit_doc_file", f"撤销 {filename}")
        except Exception:
            pass

        # Update BM25 search index after undo (SQLite-backed when session available)
        try:
            from codewiki.mcp.tools.wiki_search import update_file
            update_file(session.output_dir, doc_path, session=session)
        except Exception:
            pass

        return json.dumps({
            "status": "undone",
            "filename": filename,
            "mermaid_validation": mermaid_result,
        }, ensure_ascii=False)

    if not doc_path.exists():
        return json.dumps({"error": f"File not found: {filename}. Use write_doc_file to create it."})

    current_content = doc_path.read_text(encoding="utf-8")

    if command == "str_replace":
        old_str = read_param(arguments, "old_str")
        new_str = read_param(arguments, "new_str") or ""
        if old_str is None:
            return json.dumps({"error": "old_str is required for str_replace."})

        occurrences = current_content.count(old_str)
        if occurrences == 0:
            return json.dumps({"error": f"old_str not found in {filename}."})
        if occurrences > 1:
            return json.dumps({"error": f"old_str appears {occurrences} times in {filename}. Make it unique."})

        new_content = current_content.replace(old_str, new_str, 1)
        # Save history only for edits that actually happen, so undo never
        # pops a no-op entry left behind by a failed/rejected command.
        _save_history(session, doc_path, current_content)
        doc_path.write_text(new_content, encoding="utf-8")

        # Snippet around the edit
        replacement_line = current_content.split(old_str)[0].count("\n")
        lines = new_content.split("\n")
        start = max(0, replacement_line - 4)
        end = min(len(lines), start + new_str.count("\n") + 9)
        snippet = "\n".join(f"{i + 1:6}\t{lines[i]}" for i in range(start, end))

    elif command == "insert":
        insert_line = arguments.get("insert_line", 0)
        new_str = read_param(arguments, "new_str") or ""
        if not new_str:
            return json.dumps({"error": "new_str is required for insert."})

        lines = current_content.split("\n")
        insert_line = max(0, min(insert_line, len(lines)))
        new_str_lines = new_str.split("\n")
        lines = lines[:insert_line] + new_str_lines + lines[insert_line:]
        new_content = "\n".join(lines)
        _save_history(session, doc_path, current_content)
        doc_path.write_text(new_content, encoding="utf-8")

        start = max(0, insert_line - 4)
        end = min(len(lines), start + len(new_str_lines) + 8)
        snippet = "\n".join(f"{i + 1:6}\t{lines[i]}" for i in range(start, end))

    else:
        return json.dumps({"error": f"Unknown command: {command}. Use str_replace, insert, or undo."})

    session.docs_written += 1

    # LLM Wiki: re-parse source_refs/chunk_refs from body after edit
    try:
        raw = doc_path.read_text(encoding="utf-8")
        resynced = _resync_source_refs(raw)
        if resynced != raw:
            doc_path.write_text(resynced, encoding="utf-8")
    except Exception:
        pass

    # Mermaid validation
    mermaid_result = await _validate_mermaid(str(doc_path), filename)

    # LLM Wiki: inject source-file links for CamelCase symbols
    try:
        from codewiki.mcp.tools.knowledge_loop import _inject_symbol_links
        raw = doc_path.read_text(encoding="utf-8")
        depth = compute_depth(doc_path, session.output_dir)
        # symbol_map paths are relative to repo root; add extra levels to
        # escape output_dir (e.g. docs/) up to the repository root.
        try:
            extra = len(Path(session.output_dir).resolve().relative_to(
                Path(session.repo_path).resolve()).parts)
        except (ValueError, AttributeError):
            extra = 0
        linked = _inject_symbol_links(raw, Path(session.output_dir), depth=depth + extra, session=session)
        if linked != raw:
            doc_path.write_text(linked, encoding="utf-8")
    except Exception:
        pass

    result = {
        "status": "edited",
        "command": command,
        "filename": filename,
        "snippet": snippet,
        "mermaid_validation": mermaid_result,
    }

    # LLM Wiki: update index.md and log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(session.output_dir, "edit_doc_file",
                   f"更新 {filename} ({command})")
        rebuild_index(session.output_dir)
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)

    # Update BM25 search index (SQLite-backed when session available)
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(session.output_dir, doc_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)

    return json.dumps(result, indent=2, ensure_ascii=False)
