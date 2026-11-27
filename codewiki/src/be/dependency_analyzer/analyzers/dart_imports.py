"""Dart 指令、package URI 与 library visible-scope 解析。

Dart 的 ``import`` 只引入目标 library 导出的名字，``part`` 与所属 library
共享同一可见域，``_`` 开头成员不得跨 library。这里只做确定性的名字解析，
不执行 Dart analyzer，也不尝试完整类型推导。
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.dependency_analyzer.utils.grammars import get_parser
from codewiki.src.be.dependency_analyzer.utils.security import safe_open_text

DART_REF_PREFIX = "dart:"
_PUBSPEC_NAME_RE = re.compile(r"^name:\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_GENERATED_SUFFIXES = (".g.dart", ".freezed.dart", ".gen.dart")


def is_generated_dart_path(path: str) -> bool:
    normalized = Path(path).as_posix()
    return normalized.endswith(_GENERATED_SUFFIXES) or "/.dart_tool/" in f"/{normalized}"


def dart_ref(callee: str) -> str:
    return f"{DART_REF_PREFIX}{callee}"


@dataclass(frozen=True)
class DartDirective:
    kind: str
    uri: Optional[str] = None
    prefix: Optional[str] = None
    show: tuple[str, ...] = ()
    hide: tuple[str, ...] = ()
    library_name: Optional[str] = None
    line: int = 0


@dataclass(frozen=True)
class NameFilter:
    include: Optional[frozenset[str]] = None
    exclude: frozenset[str] = field(default_factory=frozenset)

    def allows(self, name: str) -> bool:
        return (self.include is None or name in self.include) and name not in self.exclude

    def intersect(self, other: "NameFilter") -> "NameFilter":
        if self.include is None:
            include = other.include
        elif other.include is None:
            include = self.include
        else:
            include = self.include & other.include
        return NameFilter(include, self.exclude | other.exclude)


_OPEN_FILTER = NameFilter()


def _extend_filter_paths(
    paths: tuple[NameFilter, ...], restriction: NameFilter
) -> tuple[NameFilter, ...]:
    """把下一条 export/import 限制沿每条已有路径继续传播。"""
    return tuple(path.intersect(restriction) for path in paths)


def _merge_filter_paths(
    left: tuple[NameFilter, ...], right: tuple[NameFilter, ...]
) -> tuple[NameFilter, ...]:
    """同一目标的不同路径取并集，不能把 show Foo 与 show Bar 交叉成空集。"""
    return tuple(dict.fromkeys((*left, *right)))


def _allows_any(filters: tuple[NameFilter, ...], name: str) -> bool:
    return any(name_filter.allows(name) for name_filter in filters)


def _text(node) -> str:
    return node.text.decode("utf8", errors="replace") if node is not None else ""


def _first_child(node, *types):
    if node is None:
        return None
    return next((child for child in node.named_children if child.type in types), None)


def _string_value(node) -> Optional[str]:
    current = node
    while current is not None:
        if current.type == "string_literal":
            return _text(current).lstrip("r").strip("'\"")
        if current.type == "uri":
            current = _first_child(current, "string_literal")
        else:
            current = _first_child(current, "uri", "configurable_uri")
    return None


def _combinators(node) -> tuple[tuple[str, ...], tuple[str, ...]]:
    shown: list[str] = []
    hidden: list[str] = []
    for child in node.named_children:
        if child.type != "combinator":
            continue
        values = tuple(_text(item) for item in child.named_children if item.type == "identifier")
        if child.children and _text(child.children[0]) == "show":
            shown.extend(values)
        elif child.children and _text(child.children[0]) == "hide":
            hidden.extend(values)
    return tuple(shown), tuple(hidden)


def parse_directives(root) -> list[DartDirective]:
    directives: list[DartDirective] = []
    for child in root.named_children:
        line = child.start_point[0] + 1
        if child.type == "library_name":
            name = _text(child).strip().removesuffix(";").strip()
            directives.append(DartDirective("library", library_name=name or None, line=line))
        elif child.type == "import_or_export":
            for sub in child.named_children:
                if sub.type not in {"library_import", "library_export"}:
                    continue
                spec = (
                    _first_child(sub, "import_specification")
                    if sub.type == "library_import"
                    else sub
                )
                uri_node = _first_child(spec, "configurable_uri", "uri")
                show, hide = _combinators(spec)
                if sub.type == "library_import":
                    prefix_node = _first_child(spec, "identifier")
                    directives.append(
                        DartDirective(
                            "import",
                            _string_value(uri_node),
                            _text(prefix_node) or None,
                            show,
                            hide,
                            line=line,
                        )
                    )
                else:
                    directives.append(
                        DartDirective(
                            "export", _string_value(uri_node), show=show, hide=hide, line=line
                        )
                    )
        elif child.type == "part_directive":
            directives.append(
                DartDirective("part", _string_value(_first_child(child, "uri")), line=line)
            )
        elif child.type == "part_of_directive":
            uri = _string_value(_first_child(child, "uri"))
            named = _first_child(child, "dotted_identifier_list", "identifier")
            directives.append(
                DartDirective(
                    "part_of",
                    uri,
                    library_name=_text(named).strip() or None,
                    line=line,
                )
            )
    return directives


def _read_package_name(path: Path) -> Optional[str]:
    try:
        match = _PUBSPEC_NAME_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return match.group(1) if match else None


class DartPackageResolver:
    def __init__(self, packages: dict[str, Optional[str]]):
        self.packages = packages

    @classmethod
    def from_files(cls, repo_dir: str, dart_relpaths: Iterable[str]) -> "DartPackageResolver":
        packages: dict[str, Optional[str]] = {}
        seen: set[str] = set()
        root = Path(repo_dir)
        for relpath in dart_relpaths:
            directory = posixpath.dirname(Path(relpath).as_posix())
            while directory not in seen:
                seen.add(directory)
                pubspec = root / directory / "pubspec.yaml"
                if pubspec.is_file():
                    name = _read_package_name(pubspec)
                    if name and name not in packages:
                        packages[name] = directory
                    elif name and packages.get(name) not in (None, directory):
                        # 多个 package 根同名时 ``package:name/...`` 没有唯一目标。
                        packages[name] = None
                if not directory:
                    break
                directory = posixpath.dirname(directory)
        return cls(packages)

    def resolve(self, uri: Optional[str], from_relpath: str) -> Optional[str]:
        if not uri or uri.startswith("dart:") or "://" in uri or uri.startswith("/"):
            return None
        if uri.startswith("package:"):
            name, _, rest = uri[len("package:") :].partition("/")
            package_root = self.packages.get(name)
            if package_root is None or not rest:
                return None
            target = posixpath.normpath(posixpath.join(package_root, "lib", rest))
        else:
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(Path(from_relpath).as_posix()), uri)
            )
        if target == ".." or target.startswith("../"):
            return None
        return target


@dataclass
class DartScopes:
    visible: dict[str, set[str]]
    library_members: dict[str, set[str]]
    exposed: dict[str, dict[str, dict[str, tuple[NameFilter, ...]]]] = field(default_factory=dict)


def build_scopes(
    directives_by_file: dict[str, list[DartDirective]],
    resolver: DartPackageResolver,
    known_files: set[str],
) -> DartScopes:
    library_of: dict[str, str] = {}
    parts_of: dict[str, set[str]] = defaultdict(set)
    library_names: dict[str, Optional[str]] = {}
    for path, directives in directives_by_file.items():
        for directive in directives:
            if directive.kind == "library" and directive.library_name:
                name = directive.library_name
                if name not in library_names:
                    library_names[name] = path
                elif library_names[name] != path:
                    library_names[name] = None

    # ``part`` 是权威边；只有未声明 part 目标时才使用 ``part of``。
    # 同一 part 被多个 library 认领时语义不唯一，两边都弃权。
    part_claims: dict[str, set[str]] = defaultdict(set)
    for path, directives in directives_by_file.items():
        for directive in directives:
            if directive.kind == "part":
                target = resolver.resolve(directive.uri, path)
                if target in known_files:
                    part_claims[target].add(path)
    for path, directives in directives_by_file.items():
        for directive in directives:
            if directive.kind == "part":
                target = resolver.resolve(directive.uri, path)
                if target in known_files and part_claims[target] == {path}:
                    library_of[target] = path
                    parts_of[path].add(target)
    for path, directives in directives_by_file.items():
        if path in library_of:
            continue
        for directive in directives:
            if directive.kind != "part_of":
                continue
            target = (
                resolver.resolve(directive.uri, path)
                if directive.uri
                else library_names.get(directive.library_name or "")
            )
            if target in known_files:
                library_of[path] = target
                parts_of[target].add(path)

    # 环形 ``part of`` 没有可信根 library；整环弃权，避免错误共享可见域。
    cyclic: set[str] = set()
    for start in library_of:
        chain: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in library_of and current not in positions:
            positions[current] = len(chain)
            chain.append(current)
            current = library_of[current]
        if current in positions:
            cyclic.update(chain[positions[current] :])
    for path in cyclic:
        library_of.pop(path, None)
    parts_of = defaultdict(set)
    for part, library in library_of.items():
        parts_of[library].add(part)

    def members(path: str) -> set[str]:
        library = library_of.get(path, path)
        return {library} | parts_of.get(library, set())

    def targets(path: str, kind: str) -> list[tuple[str, DartDirective]]:
        found: list[tuple[str, DartDirective]] = []
        for member in members(path):
            for directive in directives_by_file.get(member, []):
                if directive.kind != kind:
                    continue
                target = resolver.resolve(directive.uri, member)
                if target in known_files:
                    found.append((target, directive))
        return found

    def export_closure(start: str) -> dict[str, tuple[NameFilter, ...]]:
        result: dict[str, tuple[NameFilter, ...]] = {
            path: (_OPEN_FILTER,) for path in members(start)
        }
        changed = True
        while changed:
            changed = False
            for source in list(result):
                source_filters = result[source]
                for target, directive in targets(source, "export"):
                    restriction = NameFilter(
                        frozenset(directive.show) if directive.show else None,
                        frozenset(directive.hide),
                    )
                    # 沿 export 链累积过滤；菱形路径仍在合并时取并集。
                    incoming = _extend_filter_paths(source_filters, restriction)
                    if target not in result:
                        result[target] = incoming
                        changed = True
                    else:
                        merged = _merge_filter_paths(result[target], incoming)
                        if set(merged) != set(result[target]):
                            result[target] = merged
                            changed = True
        return result

    closure_cache: dict[str, dict[str, tuple[NameFilter, ...]]] = {}

    def closure(path: str) -> dict[str, tuple[NameFilter, ...]]:
        library = library_of.get(path, path)
        if library not in closure_cache:
            closure_cache[library] = export_closure(library)
        return closure_cache[library]

    visible: dict[str, set[str]] = {}
    library_members: dict[str, set[str]] = {}
    exposed: dict[str, dict[str, dict[str, tuple[NameFilter, ...]]]] = {}
    for path in directives_by_file:
        own = members(path)
        imports: dict[str, dict[str, tuple[NameFilter, ...]]] = {"": {}}
        for target, directive in targets(path, "import"):
            prefix = directive.prefix or ""
            restriction = NameFilter(
                frozenset(directive.show) if directive.show else None,
                frozenset(directive.hide),
            )
            destination = imports.setdefault(prefix, {})
            for exported, exported_filters in closure(target).items():
                merged = _extend_filter_paths(exported_filters, restriction)
                if exported in destination:
                    merged = _merge_filter_paths(destination[exported], merged)
                destination[exported] = merged
        visible[path] = set(own)
        for destination in imports.values():
            visible[path].update(destination)
        library_members[path] = own
        exposed[path] = imports
    return DartScopes(visible, library_members, exposed)


def is_private_dart_name(name: str) -> bool:
    if not name or "::" in name:
        return False
    return any(segment.startswith("_") for segment in name.split("."))


def _declared_field_types(root, relpath: str) -> dict[tuple[str, str, str], str]:
    """收集 library 内显式字段类型，用于跨文件 ``receiver.field.method``。"""
    result: dict[tuple[str, str, str], str] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in {
            "class_definition",
            "mixin_declaration",
            "extension_declaration",
            "enum_declaration",
        }:
            owner = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            if owner and body is not None:
                for declaration in body.named_children:
                    if declaration.type != "declaration":
                        continue
                    declared = ".".join(
                        _text(child)
                        for child in declaration.named_children
                        if child.type == "type_identifier"
                    )
                    if not declared:
                        continue
                    for holder in declaration.named_children:
                        if holder.type not in {
                            "initialized_identifier_list",
                            "static_final_declaration_list",
                        }:
                            continue
                        for item in holder.named_children:
                            if item.type not in {
                                "initialized_identifier",
                                "static_final_declaration",
                            }:
                                continue
                            name = _text(_first_child(item, "identifier"))
                            if name:
                                result[(relpath, owner, name)] = declared
        stack.extend(reversed(node.named_children))
    return result


class DartScopeIndex:
    """用全部 library 指令与当前组件表裁决 Dart 引用。"""

    def __init__(
        self,
        nodes: dict[str, Node],
        scopes: DartScopes,
        field_types: Optional[dict[tuple[str, str, str], str]] = None,
    ):
        self.nodes = nodes
        self.scopes = scopes
        self.field_types = field_types or {}
        self.by_file: dict[str, list[Node]] = defaultdict(list)
        for node in nodes.values():
            self.by_file[Path(node.relative_path).as_posix()].append(node)

    @classmethod
    def from_repo(
        cls,
        repo_dir: str,
        dart_relpaths: Iterable[str],
        nodes: dict[str, Node],
    ) -> "DartScopeIndex":
        root = Path(repo_dir)
        paths = sorted(
            {Path(path).as_posix() for path in dart_relpaths if not is_generated_dart_path(path)}
        )
        resolver = DartPackageResolver.from_files(repo_dir, paths)
        directives: dict[str, list[DartDirective]] = {}
        field_types: dict[tuple[str, str, str], str] = {}
        for relpath in paths:
            try:
                content = safe_open_text(root, root / relpath)
            except (OSError, ValueError):
                continue
            parsed_root = get_parser("dart").parse(content.encode("utf8")).root_node
            directives[relpath] = parse_directives(parsed_root)
            field_types.update(_declared_field_types(parsed_root, relpath))
        return cls(nodes, build_scopes(directives, resolver, set(paths)), field_types)

    def _candidates(self, name: str, caller_path: str, prefix: str = "") -> list[str]:
        imports = self.scopes.exposed.get(caller_path, {})
        candidates: list[str] = []
        if not prefix:
            for member_path in self.scopes.library_members.get(caller_path, {caller_path}):
                candidates.extend(
                    node.id for node in self.by_file.get(member_path, []) if node.name == name
                )
        for relpath, name_filters in imports.get(prefix, {}).items():
            if not _allows_any(name_filters, name.partition(".")[0]):
                continue
            if is_private_dart_name(name) and relpath not in self.scopes.library_members.get(
                caller_path, set()
            ):
                continue
            candidates.extend(
                node.id for node in self.by_file.get(relpath, []) if node.name == name
            )
        return candidates

    @staticmethod
    def _unique(candidates: list[str]) -> Optional[str]:
        return candidates[0] if len(set(candidates)) == 1 else None

    def _member_candidates(self, current_id: str, member: str) -> list[str]:
        """Find an owned or inherited member without falling back to bare names."""
        pending = [current_id]
        seen: set[str] = set()
        while pending:
            type_id = pending.pop(0)
            if type_id in seen:
                continue
            seen.add(type_id)
            current = self.nodes[type_id]
            current_path = Path(current.relative_path).as_posix()
            candidates = self._candidates(f"{current.name}.{member}", current_path)
            if candidates:
                return candidates
            for base in current.base_classes or []:
                base_id = self._unique(self._candidates(base, current_path))
                if base_id is not None:
                    pending.append(base_id)
        return []

    def resolve(self, raw_callee: str, caller: Node) -> Optional[str]:
        if "::" in raw_callee:
            return raw_callee if raw_callee in self.nodes else None
        caller_path = Path(caller.relative_path).as_posix()
        imports = self.scopes.exposed.get(caller_path, {})
        prefix = ""
        name = raw_callee
        head, separator, rest = raw_callee.partition(".")
        if separator and head in imports and head != "":
            prefix, name = head, rest
        segments = name.split(".")
        current_id = self._unique(self._candidates(segments[0], caller_path, prefix))
        if current_id is None:
            return None
        for field_name in segments[1:-1]:
            current = self.nodes[current_id]
            current_path = Path(current.relative_path).as_posix()
            field_type = self.field_types.get((current_path, current.name, field_name))
            if not field_type:
                return None
            # 字段类型在接收者所属 library 的命名空间中解析。
            current_id = self._unique(self._candidates(field_type, current_path))
            if current_id is None:
                return None
        current = self.nodes[current_id]
        final_name = f"{current.name}.{segments[-1]}" if len(segments) > 1 else current.name
        if len(segments) == 1:
            return current_id
        current_path = Path(current.relative_path).as_posix()
        if is_private_dart_name(final_name) and current_path not in self.scopes.library_members.get(
            caller_path, set()
        ):
            return None
        return self._unique(self._member_candidates(current_id, segments[-1]))

    def cached_edge_is_valid(self, caller: Node, callee_id: str) -> bool:
        """旧缓存没有原始引用时弃权，不能仅凭目标名猜测绑定。"""
        references = [
            reference
            for values in caller.metadata.get("dart_raw_dependencies", {}).values()
            for reference in values
        ]
        return any(self.resolve(reference, caller) == callee_id for reference in references)


def resolve_dart_callee(raw_callee: str, caller: Node, index: DartScopeIndex) -> Optional[str]:
    return index.resolve(raw_callee.removeprefix(DART_REF_PREFIX), caller)
