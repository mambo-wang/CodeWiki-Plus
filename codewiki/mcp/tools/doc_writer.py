"""MCP tools: write_doc_file + edit_doc_file.

These tools create and edit markdown documentation files in the output
directory, with automatic Mermaid diagram validation after every write.
"""

from __future__ import annotations

import json
import logging
import os
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

# Pattern for simple wikilinks: [[target]] or [[target|display]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


def _convert_wikilinks_to_md(content: str, output_dir: Path, current_file: Path) -> str:
    """Convert [[wikilink]] and [[wikilink|display]] to standard markdown links.

    Scans the wiki directory for all .md pages, builds a title→path map,
    then replaces each [[target]] with [target](relative-path.md).
    Unresolved wikilinks are left unchanged so the agent can fix them.
    """
    from codewiki.src.config import WIKI_DIR, WIKI_SYSTEM_FILES

    od = output_dir.resolve()
    wiki_dir = od / WIKI_DIR
    current_resolved = current_file.resolve()

    # Build title → relative-path mapping from existing wiki pages
    title_to_rel: Dict[str, str] = {}
    if wiki_dir.is_dir():
        for md in wiki_dir.rglob("*.md"):
            if not md.is_file() or md.name in WIKI_SYSTEM_FILES:
                continue
            rel = md.relative_to(od).as_posix()
            # Index by filename stem
            title_to_rel[md.stem.lower()] = rel
            # Also index by title from frontmatter if available
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip("\"'")
                        if title:
                            title_to_rel[title.lower()] = rel
                            title_to_rel[title.lower().replace(" ", "-")] = rel
                        break
            except OSError:
                pass

    def _replace_wikilink(m: re.Match) -> str:
        target = m.group(1).strip()
        display = m.group(2) if m.group(2) else target
        key = target.lower().replace(".md", "")
        rel_path = title_to_rel.get(key)
        if rel_path is None:
            # Try slugified match
            slug = re.sub(r"[\s_]+", "-", key).strip("-")
            rel_path = title_to_rel.get(slug)
        if rel_path is None:
            return m.group(0)  # Leave unresolved wikilinks as-is
        # Compute relative path from current file's directory to target
        target_abs = od / rel_path
        try:
            from_current = os.path.relpath(str(target_abs), str(current_resolved.parent)).replace("\\", "/")
        except ValueError:
            from_current = rel_path
        return f"[{display}]({from_current})"

    return _WIKILINK_RE.sub(_replace_wikilink, content)


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


def _split_frontmatter(content: str) -> tuple:
    """Split *content* into ``(frontmatter_block, body)``.

    The frontmatter block keeps its ``---`` delimiters.  Documents without a
    leading frontmatter return ``("", content)``.  Used by edit operations so
    that a sentence echoed inside ``description:`` does not block editing the
    same sentence in the body.
    """
    if content.startswith("---"):
        lines = content.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[: i + 1]), "\n".join(lines[i + 1:])
    return "", content


def _find_doc_by_basename(output_dir: str, filename: str) -> Path | None:
    """Locate an existing wiki document by its basename under ``wiki/``.

    Lets :func:`handle_edit_doc_file` find ``wiki/queries/Foo.md`` even when
    the caller passed ``page_type="module"`` (which would otherwise route to
    ``wiki/modules/Foo.md`` and report "File not found").
    """
    base = filename.rsplit("/", 1)[-1]
    if not base.endswith(".md"):
        base += ".md"
    wiki_dir = Path(output_dir) / "wiki"
    if not wiki_dir.is_dir():
        return None
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.is_file() and md_file.name == base:
            return md_file
    return None


def _is_within(path: Path, base: Path) -> bool:
    """Return True if *path* resolves to somewhere inside *base*."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_doc_path(
    output_dir: str,
    filename: str,
    page_type: str = "module",
) -> Path | None:
    """Resolve *filename* within *output_dir* using the page type routing table.

    Routes the file to the correct wiki subdirectory based on *page_type*
    (e.g. ``wiki/entities/`` for ``page_type="entity"``).  Guards against
    directory traversal.  Returns ``None`` if the path escapes output_dir.
    """
    schema = load_schema(output_dir)
    try:
        return resolve_doc_path(filename, page_type, output_dir, schema)
    except ValueError:
        return None


def _title_from_filename(name: str) -> str:
    """Derive a human-readable title from a filename stem.

    If the name is already CamelCase (starts with uppercase and has internal
    uppercase letters), keep it as-is to preserve names like TestEntityPage.
    Only apply title-casing to snake_case or kebab-case names.
    """
    # Strip extension if present
    name = name.replace(".md", "")
    # Detect CamelCase: starts with uppercase and has at least one internal uppercase
    if name[0:1].isupper() and any(c.isupper() for c in name[1:]):
        return name
    # For snake_case or kebab-case, convert to title case
    return name.replace("_", " ").replace("-", " ").title()


def _build_okf_frontmatter(
    session: SessionState,
    filename: str,
    content: str,
    page_type: str = "module",
    frontmatter_extra: dict | None = None,
    user_title: str | None = None,
    user_description: str | None = None,
    user_tags: list | None = None,
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

    mod_name = _title_from_filename(filename)
    if user_title:
        mod_name = user_title
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
        # BUG-16: strip dangling punctuation after truncation
        if len(line) > 200:
            description = description.rstrip("，,、。；;：: ")
            description += "…"
        break
    if user_description:
        description = user_description

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

    # User-provided tags take priority over auto-generated
    if user_tags:
        tags = list(user_tags)

    # Build frontmatter lines
    fm_parts = [
        "---",
        f"type: {doc_type}",
        f"title: {mod_name}",
        f'description: "{description}"' if description else f"description: {mod_name}",
        f"resource: {resource}",
        f"tags: [{', '.join(tags)}]",
    ]

    # Roadmap 1.4: record code version for freshness tracking
    _gen_from = ""
    if session.repo_path:
        try:
            import subprocess
            _sha = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=session.repo_path, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if _sha:
                _gen_from = _sha
        except Exception:
            pass
    if not _gen_from:
        from datetime import datetime, timezone
        _gen_from = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_parts.append(f"generated_from: {_gen_from}")

    # Merge frontmatter_extra
    extra = frontmatter_extra or {}
    # Default alias keeps the doc discoverable by its slug, so the linter's
    # missing_aliases check stays quiet for generated docs.
    aliases = extra.get("aliases")
    if not aliases:
        aliases = [filename.replace(".md", "")]
    aliases_str = ", ".join(f'"{a}"' for a in aliases)
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
    user_title: str | None = None,
    user_description: str | None = None,
    user_tags: list | None = None,
) -> str:
    """Prepend OKF frontmatter to content if not already present and enabled in schema."""
    schema = load_schema(session.output_dir)
    if not schema.get("conventions", {}).get("okf_frontmatter", True):
        return content

    frontmatter = _build_okf_frontmatter(
        session, filename, content,
        page_type=page_type,
        frontmatter_extra=frontmatter_extra,
        user_title=user_title,
        user_description=user_description,
        user_tags=user_tags,
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


def _auto_fix_mermaid(content: str) -> tuple[str, list[str]]:
    """Apply mechanical auto-fixes to Mermaid blocks in *content*.

    Returns (fixed_content, fixes_list).  When *fixes_list* is empty the
    content is returned unchanged.
    """
    try:
        from codewiki.src.be.utils import auto_fix_mermaid_blocks
        return auto_fix_mermaid_blocks(content)
    except Exception:
        return content, []


def _save_history(output_dir: str, doc_path: Path, content: str) -> None:
    """Append *content* to edit history for *doc_path*, capped at _MAX_HISTORY_PER_FILE.

    History is persisted to ``output_dir/.meta/edit_history.json``.
    """
    from codewiki.src.config import meta_join
    history_path = Path(meta_join(output_dir, "edit_history.json"))
    history: dict = {}
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    key = str(doc_path)
    entry: list = history.setdefault(key, [])
    entry.append(content)
    if len(entry) > _MAX_HISTORY_PER_FILE:
        del entry[: len(entry) - _MAX_HISTORY_PER_FILE]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


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

    # Inverted index: component id -> module name (built once, O(components))
    comp_to_module: dict[str, str] = {}
    for name, info in module_tree.items():
        for cid in info.get("components", []):
            comp_to_module.setdefault(cid, name)
        children = info.get("children", {})
        if isinstance(children, dict):
            for cname, cinfo in children.items():
                for cid in cinfo.get("components", []):
                    comp_to_module.setdefault(cid, cname)

    def _comp_to_module(comp_id: str) -> str | None:
        return comp_to_module.get(comp_id)

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

    # Filter out modules whose doc page does not exist yet (BUG-4 fix)
    from codewiki.src.config import WIKI_DIR, PAGE_TYPE_DIRS
    od = Path(session.output_dir).resolve()
    modules_dir = od / WIKI_DIR / PAGE_TYPE_DIRS["module"]

    def _module_doc_exists(mod: str) -> bool:
        target = modules_dir / f"{mod.lower().replace(' ', '_')}.md"
        return target.is_file()

    depends_on_modules = {m for m in depends_on_modules if _module_doc_exists(m)}
    depended_by_modules = {m for m in depended_by_modules if _module_doc_exists(m)}

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


def _resolve_doc_path_safe(output_dir: Path, filename: str, page_type: str = "module") -> Path | None:
    """Resolve filename within output_dir using page type routing (sessionless version)."""
    try:
        return resolve_doc_path(filename, page_type, str(output_dir), load_schema(str(output_dir)))
    except ValueError:
        return None


def _inject_lightweight_frontmatter(
    filename: str,
    content: str,
    page_type: str = "module",
    frontmatter_extra: dict | None = None,
    user_title: str | None = None,
    user_description: str | None = None,
    user_tags: list | None = None,
) -> str:
    """Inject minimal YAML frontmatter when no session is available."""
    if content.startswith("---"):
        return content  # Already has frontmatter

    mod_name = _title_from_filename(filename)
    _TYPE_MAP = {
        "module": "Module", "entity": "Entity", "concept": "Concept",
        "source": "Source", "comparison": "Comparison", "query": "Query",
    }
    doc_type = _TYPE_MAP.get(page_type, page_type.capitalize())
    if user_title:
        mod_name = user_title

    # Extract description from first paragraph
    description = ""
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("```") or line.startswith("---"):
            continue
        description = line[:200]
        # BUG-16: strip dangling punctuation after truncation
        if len(line) > 200:
            description = description.rstrip("，,、。；;：: ")
            description += "…"
        break
    if user_description:
        description = user_description

    fm_lines = [
        "---",
        f"title: \"{mod_name}\"",
        f"type: {doc_type}",
        f"description: \"{description}\"" if description else f"description: {mod_name}",
    ]

    # Default alias keeps the doc discoverable by its slug.
    aliases = (frontmatter_extra or {}).get("aliases")
    if not aliases:
        aliases = [filename.replace(".md", "")]
    fm_lines.append(f"aliases: [{', '.join(str(v) for v in aliases)}]")

    # User-provided tags
    if user_tags:
        fm_lines.append(f"tags: [{', '.join(str(t) for t in user_tags)}]")

    # Merge frontmatter_extra
    if frontmatter_extra:
        for key, value in frontmatter_extra.items():
            if key == "aliases":
                continue
            if isinstance(value, list):
                fm_lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
            elif isinstance(value, str):
                fm_lines.append(f"{key}: \"{value}\"")
            else:
                fm_lines.append(f"{key}: {value}")

    fm_lines.append("---")
    fm_lines.append("")
    return "\n".join(fm_lines) + content


async def handle_write_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Create a new documentation file in the output directory."""
    # Resolve output directory from output_dir or repo_path (schema contract)
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    repo_path = None
    if rp:
        repo_path = str(Path(rp).expanduser().resolve()) if Path(rp).is_absolute() else str((Path.cwd() / rp).expanduser().resolve())

    # Try to find/restore an active session (rich frontmatter, crosslinks, symbol links)
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)

    if od:
        output_dir = Path(od).expanduser().resolve()
    elif session:
        # Prefer the session's output_dir (honours custom output_dir from analyze_repo)
        output_dir = Path(session.output_dir).expanduser().resolve()
    elif repo_path:
        output_dir = Path(repo_path) / "repowiki"
    else:
        return json.dumps({"error": "output_dir or repo_path is required."})

    if session and repo_path is None:
        repo_path = session.repo_path

    filename = arguments["filename"]
    page_type = arguments.get("page_type", "module")
    frontmatter_extra = arguments.get("frontmatter_extra") or None
    strict = bool(arguments.get("strict", False))

    # Resolve document path using page type routing
    doc_path = _resolve_doc_path_safe(output_dir, filename, page_type=page_type)
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

    # OKF: inject YAML frontmatter (only when session is available)
    user_title = arguments.get("title") or None
    user_description = arguments.get("description") or None
    user_tags = arguments.get("tags") or None
    if session:
        content = _inject_frontmatter(
            session, filename, content,
            page_type=page_type,
            frontmatter_extra=frontmatter_extra,
            user_title=user_title,
            user_description=user_description,
            user_tags=user_tags,
        )
    else:
        # Lightweight frontmatter for sessionless mode
        content = _inject_lightweight_frontmatter(
            filename, content, page_type=page_type,
            frontmatter_extra=frontmatter_extra,
            user_title=user_title,
            user_description=user_description,
            user_tags=user_tags,
        )

    # Auto-fix common Mermaid syntax errors before writing
    content, mermaid_fixes = _auto_fix_mermaid(content)

    doc_path.write_text(content, encoding="utf-8")
    if session:
        session.docs_written += 1

    # LLM Wiki: convert [[wikilink]] to standard markdown links [text](path)
    try:
        raw = doc_path.read_text(encoding="utf-8")
        linked = _convert_wikilinks_to_md(raw, output_dir, doc_path)
        if linked != raw:
            doc_path.write_text(linked, encoding="utf-8")
    except Exception:
        pass

    # Mermaid validation (on auto-fixed content)
    mermaid_result = await _validate_mermaid(str(doc_path), filename)

    # strict mode: block the write if Mermaid validation STILL has errors after auto-fix
    if strict and "syntax errors" in mermaid_result.lower():
        try:
            doc_path.unlink()
        except OSError:
            pass
        return json.dumps({
            "error": "Mermaid validation failed in strict mode (even after auto-fix). File was not written.",
            "mermaid_warnings": mermaid_result,
            "mermaid_auto_fixes": mermaid_fixes,
        }, ensure_ascii=False)

    # LLM Wiki: wiki-link injection ([[slug|display]]) opt-in via schema.wiki_link_syntax
    try:
        schema = load_schema(str(output_dir))
        if schema.get("wiki_link_syntax", False):
            terms = _collect_wiki_terms(output_dir, exclude=doc_path)
            raw = doc_path.read_text(encoding="utf-8")
            linked = _inject_wiki_links(raw, terms)
            if linked != raw:
                doc_path.write_text(linked, encoding="utf-8")
    except Exception:
        pass

    # LLM Wiki: crosslink injection (opt-in via schema.yaml auto_crosslink)
    crosslink_info = None
    if session:
        crosslink_info = _inject_crosslinks(session, filename, doc_path)

    # LLM Wiki: inject source-file links for CamelCase symbols (only with session)
    if session and repo_path:
        try:
            from codewiki.mcp.tools.knowledge_loop import _inject_symbol_links
            raw = doc_path.read_text(encoding="utf-8")
            depth = compute_depth(doc_path, str(output_dir))
            try:
                extra = len(Path(output_dir).resolve().relative_to(
                    Path(repo_path).resolve()).parts)
            except (ValueError, AttributeError):
                extra = 0
            linked = _inject_symbol_links(raw, output_dir, depth=depth + extra, session=session)
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
        "mermaid_auto_fixes": mermaid_fixes,
    }
    # BUG-17: surface Mermaid warnings prominently in the response
    if "syntax errors" in mermaid_result.lower():
        result["mermaid_warnings"] = mermaid_result
    if crosslink_info:
        result["crosslinks"] = crosslink_info

    # LLM Wiki: update index.md and log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(str(output_dir), "write_doc_file", f"创建 {filename}")
        rebuild_index(str(output_dir))
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)

    # Update BM25 search index (SQLite-backed when session available)
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(str(output_dir), doc_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)

    return json.dumps(result, indent=2, ensure_ascii=False)


async def handle_edit_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Edit an existing documentation file (str_replace, insert, or undo)."""
    # Resolve output directory from output_dir or repo_path
    od = arguments.get("output_dir")
    rp = arguments.get("repo_path")
    repo_path = None
    if rp:
        repo_path = str(Path(rp).expanduser().resolve()) if Path(rp).is_absolute() else str((Path.cwd() / rp).expanduser().resolve())

    # Try to find active session for caching purposes (optional)
    from codewiki.mcp.tools.workspace_result import resolve_session
    session = resolve_session(arguments, store)

    if od:
        output_dir = str(Path(od).expanduser().resolve())
    elif session:
        # Prefer the session's output_dir (honours custom output_dir from analyze_repo)
        output_dir = str(Path(session.output_dir).expanduser().resolve())
    elif repo_path:
        output_dir = str(Path(repo_path) / "repowiki")
    else:
        return json.dumps({"error": "output_dir or repo_path is required."})

    if session and repo_path is None:
        repo_path = session.repo_path

    filename = arguments["filename"]
    page_type = arguments.get("page_type", "module")
    doc_path = _safe_doc_path(output_dir, filename, page_type=page_type)
    if doc_path is None:
        return json.dumps({"error": "Filename escapes output directory."})

    # Tolerance: when the page_type-routed path does not exist, locate the
    # file by basename across the wiki tree so an omitted/incorrect page_type
    # does not block editing an existing document.
    if not doc_path.exists():
        located = _find_doc_by_basename(output_dir, filename)
        if located is not None:
            doc_path = located

    command = arguments["command"]

    if command == "undo":
        # Undo via disk-based history
        from codewiki.src.config import meta_join
        history_path = Path(meta_join(output_dir, "edit_history.json"))
        history: dict = {}
        if history_path.exists():
            try:
                history = json.loads(history_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        path_history: list = history.get(str(doc_path), [])
        if not path_history:
            return json.dumps({"error": f"No edit history found for {filename}."})
        old_content = path_history.pop()
        history[str(doc_path)] = path_history
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")

        # Defensive repair: fix frontmatter/body concatenation if the history
        # snapshot was saved from corrupted content (e.g. "---# Title" instead
        # of "---\n# Title").
        if old_content.startswith("---"):
            _lines = old_content.split("\n")
            for _i in range(1, len(_lines)):
                if _lines[_i].strip() == "---":
                    break  # Proper closing delimiter found, no repair needed
                if _lines[_i].startswith("---") and len(_lines[_i]) > 3:
                    # Corrupted: closing --- concatenated with body line
                    remainder = _lines[_i][3:]
                    _lines[_i] = "---"
                    _lines.insert(_i + 1, remainder)
                    old_content = "\n".join(_lines)
                    break

        doc_path.write_text(old_content, encoding="utf-8")

        # Validate Mermaid after undo
        mermaid_result = await _validate_mermaid(str(doc_path), filename)

        # LLM Wiki: update log.md (undo changes file content)
        try:
            from codewiki.mcp.tools.wiki_index import append_log
            append_log(output_dir, "edit_doc_file", f"撤销 {filename}")
        except Exception:
            pass

        # Update BM25 search index after undo (SQLite-backed when session available)
        try:
            from codewiki.mcp.tools.wiki_search import update_file
            update_file(output_dir, doc_path, session=session)
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

        # Frontmatter (e.g. the auto-generated ``description:``) may echo a
        # sentence from the body; count occurrences against the body only so
        # editing the body is not blocked by its own frontmatter copy.
        fm, body = _split_frontmatter(current_content)
        occurrences = body.count(old_str)
        if occurrences == 0:
            # Fall back to a whole-document search (e.g. editing frontmatter).
            occurrences = current_content.count(old_str)
            if occurrences == 0:
                return json.dumps({"error": f"old_str not found in {filename}."})
            new_content = current_content.replace(old_str, new_str, 1)
        elif occurrences > 1:
            return json.dumps({"error": f"old_str appears {occurrences} times in {filename}. Make it unique."})
        else:
            new_content = fm + "\n" + body.replace(old_str, new_str, 1)
        # Calculate edit position BEFORE replacement so snippet shows the
        # actual edit location (find() on new_content may hit a wrong match
        # or fail entirely for deletions where new_str is empty).
        if occurrences == 1:
            edit_line = body.split(old_str)[0].count("\n")
        else:
            edit_line = current_content.split(old_str)[0].count("\n")
        # Save history only for edits that actually happen, so undo never
        # pops a no-op entry left behind by a failed/rejected command.
        _save_history(output_dir, doc_path, current_content)
        doc_path.write_text(new_content, encoding="utf-8")

        # Convert [[wikilink]] to markdown links
        try:
            raw = doc_path.read_text(encoding="utf-8")
            linked = _convert_wikilinks_to_md(raw, Path(output_dir), doc_path)
            if linked != raw:
                doc_path.write_text(linked, encoding="utf-8")
        except Exception:
            pass

        # Snippet around the edit (use pre-computed edit_line)
        fm_line_count = fm.count("\n") + 1 if fm else 0
        replacement_line = fm_line_count + edit_line
        lines = new_content.split("\n")
        start = max(0, replacement_line - 4)
        end = min(len(lines), start + max(new_str.count("\n"), 0) + 9)
        snippet = "\n".join(f"{i + 1:6}\t{lines[i]}" for i in range(start, end))

    elif command == "insert":
        insert_line = arguments.get("insert_line", 0)
        new_str = read_param(arguments, "new_str") or ""
        if not new_str:
            return json.dumps({"error": "new_str is required for insert."})

        lines = current_content.split("\n")
        insert_line = max(0, min(insert_line, len(lines)))

        # Guard: reject inserts that would corrupt YAML frontmatter
        if current_content.startswith("---"):
            fm_end = None
            for _fi in range(1, len(lines)):
                if lines[_fi].strip() == "---":
                    fm_end = _fi
                    break
            if fm_end is not None and insert_line <= fm_end:
                return json.dumps({
                    "error": f"insert_line falls within YAML frontmatter (lines 0-{fm_end}). "
                             f"Use insert_line >= {fm_end + 1} to insert into the body."
                })

        new_str_lines = new_str.split("\n")
        lines = lines[:insert_line] + new_str_lines + lines[insert_line:]
        new_content = "\n".join(lines)
        _save_history(output_dir, doc_path, current_content)
        doc_path.write_text(new_content, encoding="utf-8")

        # Convert [[wikilink]] to markdown links
        try:
            raw = doc_path.read_text(encoding="utf-8")
            linked = _convert_wikilinks_to_md(raw, Path(output_dir), doc_path)
            if linked != raw:
                doc_path.write_text(linked, encoding="utf-8")
        except Exception:
            pass

        start = max(0, insert_line - 4)
        end = min(len(lines), start + len(new_str_lines) + 8)
        snippet = "\n".join(f"{i + 1:6}\t{lines[i]}" for i in range(start, end))

    else:
        return json.dumps({"error": f"Unknown command: {command}. Use str_replace, insert, or undo."})

    if session is not None:
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
        depth = compute_depth(doc_path, output_dir)
        # symbol_map paths are relative to repo root; add extra levels to
        # escape output_dir (e.g. docs/) up to the repository root.
        extra = 0
        if repo_path:
            try:
                extra = len(Path(output_dir).resolve().relative_to(
                    Path(repo_path).resolve()).parts)
            except (ValueError, AttributeError):
                pass
        linked = _inject_symbol_links(raw, Path(output_dir), depth=depth + extra, session=session)
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
    # BUG-17: surface Mermaid warnings prominently in the response
    if "syntax errors" in mermaid_result.lower():
        result["mermaid_warnings"] = mermaid_result

    # LLM Wiki: update index.md and log.md
    try:
        from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
        append_log(output_dir, "edit_doc_file",
                   f"更新 {filename} ({command})")
        rebuild_index(output_dir)
    except Exception as e:
        logger.warning("Index/log update failed (non-fatal): %s", e)

    # Update BM25 search index (SQLite-backed when session available)
    try:
        from codewiki.mcp.tools.wiki_search import update_file
        update_file(output_dir, doc_path, session=session)
    except Exception as e:
        logger.warning("Search index update failed (non-fatal): %s", e)

    return json.dumps(result, indent=2, ensure_ascii=False)
