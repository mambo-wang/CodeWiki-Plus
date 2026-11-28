"""确定性的文档反向引用索引。

Markdown 语料是唯一内容真源；本模块在仓库元数据目录中派生页面到引用对象、
引用对象到页面的缓存，不编辑页面，也不调用 LLM。
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from codewiki.mcp.tools.wiki_lint import (
    _NON_AUDIT_DIR_NAMES,
    _build_anchor_map,
    _collect_linked_targets,
    _strip_code_blocks,
)

logger = logging.getLogger(__name__)

INDEX_FILENAME = "reference_index.json"
SCHEMA_VERSION = 1

_FENCED_CODE_RE = re.compile(r"(?ms)^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_IDENTIFIER_RE = re.compile(r"(?:[^\W\d]|[$])(?:\w|[$])*", re.UNICODE)
_TOKEN_RE = re.compile(r"[^\s`\[\](){}<>]+")
_TRAILING_PUNCTUATION = ".,;:!?。，；：！？、\"'"


def reference_index_path(repo_path: str | Path, output_dir: str | Path) -> Path:
    from codewiki.mcp.cache import resolve_analysis_meta_file

    return resolve_analysis_meta_file(Path(repo_path), Path(output_dir), INDEX_FILENAME)


def _norm(value: str) -> str:
    return value.replace("\\", "/")


def _attr(component: Any, name: str, default: Any = None) -> Any:
    if isinstance(component, Mapping):
        return component.get(name, default)
    return getattr(component, name, default)


def _iter_markdown_pages(output_dir: Path) -> Iterator[Path]:
    for md_file in output_dir.rglob("*.md"):
        if not md_file.is_file():
            continue
        rel_parts = md_file.relative_to(output_dir).parts
        if _NON_AUDIT_DIR_NAMES.intersection(rel_parts):
            continue
        if "sources" in rel_parts and "raw" in rel_parts:
            continue
        yield md_file


def _code_fragments(content: str) -> list[str]:
    fenced = list(_FENCED_CODE_RE.finditer(content))
    fragments = []
    for match in fenced:
        lines = match.group(0).splitlines()
        fragments.append("\n".join(lines[1:-1]))
    remaining = _FENCED_CODE_RE.sub("", content)
    fragments.extend(match.group(1) for match in _INLINE_CODE_RE.finditer(remaining))
    return fragments


def _extract_component_ids(content: str, known_ids: set[str]) -> set[str]:
    found: set[str] = set()
    for match in _TOKEN_RE.finditer(content):
        candidate = _norm(match.group(0)).rstrip(_TRAILING_PUNCTUATION)
        if candidate in known_ids:
            found.add(candidate)
    return found


def _extract_code_symbols(fragments: Iterable[str], symbols: Mapping[str, str]) -> set[str]:
    found: set[str] = set()
    for fragment in fragments:
        for match in _IDENTIFIER_RE.finditer(fragment):
            symbol = match.group(0)
            if symbol in symbols:
                found.add(symbols[symbol])
    return found


def _unique_symbols(components: Mapping[str, Any], historical: Mapping[str, str]) -> dict[str, str]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for component_id, component in components.items():
        name = str(_attr(component, "name", "") or "")
        if name and _IDENTIFIER_RE.fullmatch(name):
            candidates[name].add(component_id)

    symbols = {name: next(iter(ids)) for name, ids in candidates.items() if len(ids) == 1}
    for name, component_id in historical.items():
        if name not in candidates and name and component_id:
            symbols[name] = component_id
    return dict(sorted(symbols.items()))


def _load_historical_symbols(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("symbols")
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): str(component_id)
        for name, component_id in raw.items()
        if isinstance(name, str) and isinstance(component_id, str)
    }


def rebuild_index(
    repo_path: str | Path,
    output_dir: str | Path,
    components: Mapping[str, Any] | None = None,
    *,
    previous_components: Mapping[str, Any] | None = None,
    historical_symbols: Mapping[str, str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """从当前语料重建并以原子方式持久化索引。"""
    output_dir = Path(output_dir)
    path = reference_index_path(repo_path, output_dir)
    historical = _load_historical_symbols(path)
    historical.update(historical_symbols or {})

    known: dict[str, Any] = dict(previous_components or {})
    known.update(components or {})
    known_ids = {_norm(str(component_id)) for component_id in known}
    symbols = _unique_symbols(known, historical)
    anchor_map = _build_anchor_map(output_dir)

    pages: dict[str, list[str]] = {}
    references: dict[str, set[str]] = defaultdict(set)
    for md_file in sorted(
        _iter_markdown_pages(output_dir),
        key=lambda item: item.relative_to(output_dir).as_posix(),
    ):
        page_key = md_file.relative_to(output_dir).as_posix()
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        refs = {
            f"page:{_norm(str(target))}"
            for target in _collect_linked_targets(
                _strip_code_blocks(content), md_file, output_dir, anchor_map
            )
        }
        refs.update(
            f"component:{component_id}"
            for component_id in _extract_component_ids(content, known_ids)
        )
        refs.update(
            f"component:{component_id}"
            for component_id in _extract_code_symbols(_code_fragments(content), symbols)
        )
        ordered_refs = sorted(refs)
        pages[page_key] = ordered_refs
        for ref in ordered_refs:
            references[ref].add(page_key)

    index = {
        "schema_version": SCHEMA_VERSION,
        "pages": dict(sorted(pages.items())),
        "references": {ref: sorted(page_keys) for ref, page_keys in sorted(references.items())},
        "symbols": symbols,
    }

    from codewiki.src.store import atomic_write

    atomic_write(
        path,
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        stage=False,
    )
    return path, index


def referencing_pages(
    index: Mapping[str, Any],
    *,
    component_ids: Iterable[str] = (),
    page_keys: Iterable[str] = (),
) -> dict[str, dict[str, list[str]]]:
    """返回指定目标对象的确定性反向引用页面清单。"""
    references = index.get("references")
    if not isinstance(references, Mapping):
        references = {}
    return {
        "components": {
            _norm(str(component_id)): sorted(
                references.get(f"component:{_norm(str(component_id))}", [])
            )
            for component_id in sorted(set(component_ids))
        },
        "pages": {
            _norm(str(page_key)): sorted(references.get(f"page:{_norm(str(page_key))}", []))
            for page_key in sorted(set(page_keys))
        },
    }


def classify_component_changes(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """分类已删除组件，以及同一跨度内可唯一确认的改名组件。"""
    previous_ids = set(previous)
    current_ids = set(current)
    removed = previous_ids - current_ids
    added = current_ids - previous_ids

    def span_key(component_id: str, components: Mapping[str, Any]) -> tuple[Any, ...]:
        component = components[component_id]
        return (
            _norm(str(_attr(component, "relative_path", "") or "")),
            int(_attr(component, "start_line", 0) or 0),
            int(_attr(component, "end_line", 0) or 0),
            str(_attr(component, "component_type", "") or ""),
        )

    old_by_span: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    new_by_span: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for component_id in removed:
        old_by_span[span_key(component_id, previous)].append(component_id)
    for component_id in added:
        new_by_span[span_key(component_id, current)].append(component_id)

    renamed: list[dict[str, str]] = []
    for key in sorted(old_by_span.keys() & new_by_span.keys()):
        old_ids = old_by_span[key]
        new_ids = new_by_span[key]
        if len(old_ids) != 1 or len(new_ids) != 1:
            continue
        old_id, new_id = old_ids[0], new_ids[0]
        if str(_attr(previous[old_id], "name", "") or "") == str(
            _attr(current[new_id], "name", "") or ""
        ):
            continue
        renamed.append({"from": old_id, "to": new_id})
        removed.discard(old_id)
        added.discard(new_id)

    return {
        "added": sorted(added),
        "deleted": sorted(removed),
        "renamed": sorted(renamed, key=lambda item: (item["from"], item["to"])),
    }
