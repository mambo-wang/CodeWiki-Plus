"""Tree-sitter Scala 源码分析器。

Scala 的 package 是声明身份，不一定等于目录。分析器保留本地
``相对路径::逻辑名`` 组件 ID，把跨文件引用编码成 package-scoped 引用；
全部文件可见后再由 :class:`ScalaPackageIndex` 精确解析，避免按尾名跨包误绑。
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError, get_parser

logger = logging.getLogger(__name__)

SCALA_REF_PREFIX = "scala:"

_TYPE_NODES = (
    "class_definition",
    "trait_definition",
    "object_definition",
    "package_object",
    "enum_definition",
)
_FUNCTION_NODES = ("function_definition", "function_declaration")
_TYPE_MAPPING = {
    "trait_definition": ("interface", "trait"),
    "class_definition": ("class", "class"),
    "object_definition": ("class", "object"),
    "package_object": ("class", "object"),
    "enum_definition": ("class", "enum"),
}
_PRIMITIVE_TYPES = frozenset(
    {
        "Boolean",
        "Byte",
        "Char",
        "Double",
        "Float",
        "Int",
        "Long",
        "Short",
        "String",
        "Unit",
        "Any",
        "AnyRef",
        "AnyVal",
        "Nothing",
        "Null",
        "Self",
    }
)
_CALL_NOISE = frozenset(
    {
        "assert",
        "println",
        "printf",
        "print",
        "require",
        "requireMessage",
        "???",
        "identity",
        "implicitly",
        "summon",
    }
)


def scala_package_ref(package: str, symbol: str) -> str:
    """编码一个 Scala package 内符号；空 package 表示默认包。"""
    return f"{SCALA_REF_PREFIX}{package}::{symbol}"


def split_scala_package_ref(value: str) -> Optional[tuple[str, str]]:
    """解析 package 引用；组件 ID 和普通逻辑名不伪装成 package 引用。"""
    if not value.startswith(SCALA_REF_PREFIX):
        return None
    body = value[len(SCALA_REF_PREFIX) :]
    if "::" not in body:
        return None
    package, symbol = body.split("::", 1)
    return package, symbol


def scala_node_identity(node: Node) -> tuple[str, str]:
    """还原 ``(package, logical_name)``，兼容 SQLite 不持久化 component_id。"""
    component_id = node.component_id or node.id
    if component_id and "::" in component_id:
        logical_name = component_id.split("::", 1)[1]
    else:
        logical_name = node.name
        if node.class_name:
            logical_name = f"{node.class_name}.{logical_name}"
        if node.node_type == "object" and (node.qualified_name or "").endswith("$"):
            logical_name += "$"
    qualified = node.qualified_name or ""
    suffix = f".{logical_name}"
    package = qualified[: -len(suffix)] if qualified.endswith(suffix) else ""
    return package, logical_name


@dataclass
class _Imports:
    explicit: dict[str, tuple[str, str]] = field(default_factory=dict)
    wildcards: set[str] = field(default_factory=set)

    def copy(self) -> _Imports:
        return _Imports(dict(self.explicit), set(self.wildcards))


@dataclass
class _Definition:
    ast_node: Any
    node: Node
    package: str
    parent: Optional[str]
    imports: _Imports
    variable_types: dict[str, Any]
    type_nodes: list[Any]


class ScalaPackageIndex:
    """按 ``(package, logical_name)`` 建立唯一符号索引。"""

    def __init__(self, functions: dict[str, Node]):
        self._nodes = dict(functions)
        self._symbols: dict[tuple[str, str], list[str]] = defaultdict(list)
        for component_id, node in functions.items():
            if node.language != "scala":
                continue
            package, logical_name = scala_node_identity(node)
            self._symbols[(package, logical_name)].append(component_id)

    def lookup(self, package: str, symbol: str) -> Optional[str]:
        matches = self._symbols.get((package, symbol), [])
        return matches[0] if len(matches) == 1 else None

    def node(self, component_id: str) -> Optional[Node]:
        return self._nodes.get(component_id)

    def is_object_method(self, package: str, symbol: str) -> bool:
        component_id = self.lookup(package, symbol)
        if component_id is None:
            return False
        method = self._nodes.get(component_id)
        if method is None:
            return False
        owner_id = self.lookup(package, method.class_name or "")
        owner = self._nodes.get(owner_id) if owner_id else None
        return owner is not None and owner.node_type == "object"

    def field_type(self, package: str, owner: str, field: str) -> Optional[str]:
        """读取持久化的类构造参数；字段链不依赖缓存源码正文。"""
        owner_id = self.lookup(package, owner)
        node = self._nodes.get(owner_id) if owner_id else None
        if node is None:
            return None
        for parameter in node.parameters or []:
            name, separator, type_name = parameter.partition(":")
            if separator and name.strip() == field:
                return type_name.strip().split("[", 1)[0] or None
        return None


def resolve_scala_callee(callee: str, caller: Node, index: ScalaPackageIndex) -> Optional[str]:
    """只解析 package 引用；调用者身份用于阻止非 Scala 引用进入此解析器。"""
    parsed = split_scala_package_ref(callee)
    if parsed is None:
        return None
    package, target = parsed

    def lookup(candidate_package: str, symbol: str) -> Optional[str]:
        if not candidate_package.startswith("@wild:"):
            return index.lookup(candidate_package, symbol)
        matches = {
            found
            for name in candidate_package[len("@wild:") :].split("|")
            if (found := index.lookup(name, symbol)) is not None
        }
        return next(iter(matches)) if len(matches) == 1 else None

    if target.startswith("@fallback:"):
        try:
            fallback = json.loads(target[len("@fallback:") :])
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(fallback, list) or len(fallback) < 2:
            return None
        name, primaries = fallback[0], fallback[1:]
        if not isinstance(name, str) or not all(isinstance(item, str) for item in primaries):
            return None
        for primary in primaries:
            if resolve_scala_callee(primary, caller, index) is not None:
                return None
        return lookup(package, name)
    if target.startswith("@type:"):
        return lookup(package, target.removeprefix("@type:"))
    if target.startswith("@companion:"):
        name = target.removeprefix("@companion:")
        applied = lookup(package, f"{name}$.apply")
        if applied is not None:
            return applied
        packages = (
            package[len("@wild:") :].split("|") if package.startswith("@wild:") else [package]
        )
        if any(index.lookup(candidate, f"{name}$") is not None for candidate in packages):
            return None
        return lookup(package, name)
    if target.startswith("@chain:"):
        root, fields, method = target[len("@chain:") :].split("|", 2)
        owner_id = lookup(package, root)
        if owner_id is None:
            return None
        owner_node = index.node(owner_id)
        if owner_node is None:
            return None
        owner_package, owner = scala_node_identity(owner_node)
        for field in fields.split("."):
            field_type = index.field_type(owner_package, owner, field)
            if field_type is None:
                return None
            if "." in field_type:
                owner_package, owner = field_type.rsplit(".", 1)
            else:
                owner = field_type
        return lookup(owner_package, f"{owner}.{method}")
    if target.startswith("@static:"):
        symbol = target.removeprefix("@static:")
        receiver, _, method = symbol.rpartition(".")
        if receiver:
            companion = lookup(package, f"{receiver.strip('$')}$.{method}")
            if companion:
                return companion
        direct = lookup(package, symbol)
        if direct and (
            not receiver
            or all(
                index.is_object_method(candidate, symbol)
                for candidate in (
                    package[len("@wild:") :].split("|")
                    if package.startswith("@wild:")
                    else [package]
                )
                if index.lookup(candidate, symbol) is not None
            )
        ):
            return direct
        return None
    return lookup(package, target)


class TreeSitterScalaAnalyzer:
    """分析单个 Scala 2/3 文件。grammar 缺失必须显式抛出。"""

    def __init__(self, file_path: str, content: str, repo_path: Optional[str] = None):
        self.file_path = Path(file_path)
        self.content = content
        self.repo_path = repo_path or ""
        self.relative_path = Path(self._get_relative_path()).as_posix()
        self.nodes: list[Node] = []
        self.call_relationships: list[CallRelationship] = []
        self._definitions: list[_Definition] = []
        self._owner_methods: set[tuple[str, str, str]] = set()
        self._top_level_names: set[tuple[str, str]] = set()
        self._seen_relationships: set[tuple[str, str, int | None]] = set()
        self._analyze()

    def _get_relative_path(self) -> str:
        if self.repo_path:
            try:
                real_file = os.path.realpath(str(self.file_path))
                real_repo = os.path.realpath(self.repo_path)
                return os.path.relpath(real_file, real_repo).replace(os.sep, "/")
            except ValueError:
                pass
        return str(self.file_path).replace(os.sep, "/")

    def _component_id(self, logical_name: str) -> str:
        return f"{self.relative_path}::{logical_name}"

    def _owner_base_classes(self, definition: _Definition) -> list[str]:
        if not definition.parent:
            return []
        owner_id = self._component_id(definition.parent)
        return next(
            (node.base_classes or [] for node in self.nodes if node.id == owner_id),
            [],
        )

    def _analyze(self) -> None:
        try:
            tree = get_parser("scala").parse(bytes(self.content, "utf8"))
            self._extract_root(tree.root_node)
            self._extract_relationships()
            self._drop_ambiguous_component_ids()
        except GrammarUnavailableError:
            raise
        except Exception as exc:
            logger.error("Error parsing Scala file %s: %s", self.file_path, exc)

    def _extract_root(self, root: Any) -> None:
        """按顶层 package 子句切分作用域，并处理 ``package x { ... }``。"""
        package = ""
        imports = _Imports()
        segment: list[Any] = []

        def flush() -> None:
            if segment:
                self._extract_container(segment, package, None, imports)
                segment.clear()

        for child in root.named_children:
            if child.type == "package_clause":
                name_node = child.child_by_field_name("name")
                body = child.child_by_field_name("body")
                declared = name_node.text.decode("utf8") if name_node is not None else ""
                if declared.startswith("_root_."):
                    declared = declared[len("_root_.") :]
                flush()
                if body is not None:
                    self._extract_container(body.named_children, declared, None, imports.copy())
                else:
                    package = declared
                    imports = _Imports()
                continue
            segment.append(child)
        flush()

    def _extract_container(
        self,
        children: Iterable[Any],
        package: str,
        parent: Optional[str],
        inherited_imports: _Imports,
        inherited_variable_types: Optional[dict[str, Any]] = None,
    ) -> None:
        children = list(children)
        imports = inherited_imports.copy()
        for child in children:
            if child.type == "import_declaration":
                self._register_import(child, imports)
            elif child.type == "package_clause":
                body = child.child_by_field_name("body")
                name_node = child.child_by_field_name("name")
                if body is not None and name_node is not None:
                    raw = name_node.text.decode("utf8")
                    absolute = raw.startswith("_root_.")
                    declared = raw.removeprefix("_root_.")
                    if package and not absolute:
                        declared = f"{package}.{declared}"
                    self._extract_container(body.named_children, declared, parent, imports)

        variable_types: dict[str, Any] = dict(inherited_variable_types or {})
        for child in children:
            if child.type in {"val_definition", "var_definition"}:
                self._register_field_type(child, variable_types)

        for child in children:
            if child.type in _TYPE_NODES:
                self._extract_type(child, package, parent, imports)
            elif child.type in _FUNCTION_NODES:
                self._extract_function(child, package, parent, imports, variable_types)
            elif self._nested_package_object_parts(child) is not None:
                self._extract_nested_package_object(child, package, parent, imports)

    def _nested_package_object_parts(self, node: Any) -> Optional[tuple[Any, Any]]:
        """兼容 grammar 把 package 块内的 ``package object`` 解析成 infix。"""
        if node.type != "infix_expression":
            return None
        left = node.child_by_field_name("left")
        operator = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if (
            left is None
            or operator is None
            or right is None
            or left.text.decode("utf8") != "package"
            or operator.text.decode("utf8") != "object"
            or right.type != "call_expression"
        ):
            return None
        name_node = right.child_by_field_name("function")
        body = right.child_by_field_name("arguments")
        if name_node is None or body is None:
            return None
        return name_node, body

    def _extract_nested_package_object(
        self, node: Any, package: str, parent: Optional[str], imports: _Imports
    ) -> None:
        parts = self._nested_package_object_parts(node)
        if parts is None:
            return
        name_node, body = parts
        name = name_node.text.decode("utf8")
        logical_name = f"{parent}.{name}" if parent else name
        component_id = self._component_id(logical_name)
        node_obj = self._make_node(
            node, component_id, name, "class", "object", package, logical_name
        )
        self.nodes.append(node_obj)
        self._definitions.append(
            _Definition(node, node_obj, package, parent, imports.copy(), {}, [])
        )
        self._extract_container(body.named_children, package, logical_name, imports)

    def _register_import(self, node: Any, imports: _Imports) -> None:
        path_nodes = node.children_by_field_name("path")
        path = [part.text.decode("utf8") for part in path_nodes if part.type == "identifier"]
        if not path:
            return
        if path[0] == "_root_":
            path = path[1:]
        selectors = next((c for c in node.named_children if c.type == "namespace_selectors"), None)
        if selectors is not None:
            base = ".".join(path)
            for selector in selectors.named_children:
                if selector.type == "identifier":
                    name = selector.text.decode("utf8")
                    imports.explicit[name] = (base, name)
                elif selector.type == "arrow_renamed_identifier":
                    original = selector.child_by_field_name("name")
                    alias = selector.child_by_field_name("alias")
                    if original is None or alias is None:
                        continue
                    original_name = original.text.decode("utf8")
                    alias_name = alias.text.decode("utf8")
                    if alias_name != "_":
                        imports.explicit[alias_name] = (base, original_name)
                elif selector.type == "namespace_wildcard":
                    imports.wildcards.add(base)
            return

        has_wildcard = any(c.type == "namespace_wildcard" for c in node.named_children)
        if has_wildcard:
            imports.wildcards.add(".".join(path))
        if len(path) >= 2:
            name = path[-1]
            imports.explicit[name] = (".".join(path[:-1]), name)

    def _register_field_type(self, node: Any, variable_types: dict[str, Any]) -> None:
        name_node = node.child_by_field_name("pattern")
        if name_node is None:
            name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        if name_node is not None and type_node is not None:
            variable_types[name_node.text.decode("utf8")] = type_node

    def _extract_type(
        self, node: Any, package: str, parent: Optional[str], imports: _Imports
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf8")
        logical_name = f"{parent}.{name}" if parent else name
        if node.type == "object_definition":
            logical_name = f"{logical_name}$"
        component_type, node_type = _TYPE_MAPPING[node.type]
        component_id = self._component_id(logical_name)
        type_nodes: list[Any] = []
        variable_types: dict[str, Any] = {}
        parameters: list[str] = []

        type_parameters = node.child_by_field_name("type_parameters")
        if type_parameters is not None:
            type_nodes.extend(self._type_parameter_bounds(type_parameters))
        class_parameters = node.child_by_field_name("class_parameters")
        if class_parameters is not None:
            for parameter in class_parameters.named_children:
                if parameter.type != "class_parameter":
                    continue
                parameter_name = parameter.child_by_field_name("name")
                parameter_type = parameter.child_by_field_name("type")
                if parameter_name is not None and parameter_type is not None:
                    persisted_type = self._persisted_type_name(parameter_type, package, imports)
                    variable_types[parameter_name.text.decode("utf8")] = parameter_type
                    parameters.append(f"{parameter_name.text.decode('utf8')}: {persisted_type}")
                    type_nodes.append(parameter_type)
        extend = node.child_by_field_name("extend")
        if extend is not None:
            type_nodes.append(extend)
        body = node.child_by_field_name("body")
        if body is not None:
            for field_node in body.named_children:
                if field_node.type in {"val_definition", "var_definition"}:
                    field_type = field_node.child_by_field_name("type")
                    if field_type is not None:
                        type_nodes.append(field_type)

        node_obj = self._make_node(
            node,
            component_id,
            name,
            component_type,
            node_type,
            package,
            logical_name,
            parameters=parameters,
        )
        self.nodes.append(node_obj)
        self._definitions.append(
            _Definition(node, node_obj, package, parent, imports.copy(), variable_types, type_nodes)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            self._extract_container(
                body.named_children, package, logical_name, imports, variable_types
            )

    def _extract_function(
        self,
        node: Any,
        package: str,
        parent: Optional[str],
        imports: _Imports,
        inherited_variable_types: dict[str, Any],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf8")
        component_type = "method" if parent else "function"
        node_type = "method" if parent else "function"
        logical_name = f"{parent}.{name}" if parent else name
        component_id = self._component_id(logical_name)
        parameters, variable_types, type_nodes = self._parameters(node)
        variable_types = {**inherited_variable_types, **variable_types}
        return_type = node.child_by_field_name("return_type")
        if return_type is not None:
            type_nodes.append(return_type)
        node_obj = self._make_node(
            node,
            component_id,
            name,
            component_type,
            node_type,
            package,
            logical_name,
            parent=parent,
            parameters=parameters,
        )
        self.nodes.append(node_obj)
        self._definitions.append(
            _Definition(node, node_obj, package, parent, imports.copy(), variable_types, type_nodes)
        )
        if parent:
            self._owner_methods.add((package, parent, name))
        else:
            self._top_level_names.add((package, name))

    def _parameters(self, node: Any) -> tuple[list[str], dict[str, Any], list[Any]]:
        parameters: list[str] = []
        variable_types: dict[str, Any] = {}
        type_nodes: list[Any] = []
        for group in node.children_by_field_name("parameters"):
            for parameter in group.named_children:
                if parameter.type != "parameter":
                    continue
                name_node = parameter.child_by_field_name("name")
                type_node = parameter.child_by_field_name("type")
                if name_node is None:
                    continue
                name = name_node.text.decode("utf8")
                type_text = type_node.text.decode("utf8") if type_node is not None else ""
                parameters.append(f"{name}: {type_text}" if type_text else name)
                if type_node is not None:
                    variable_types[name] = type_node
                    type_nodes.append(type_node)
        return parameters, variable_types, type_nodes

    def _type_parameter_bounds(self, node: Any) -> list[Any]:
        bounds: list[Any] = []
        for parameter in node.named_children:
            bound = parameter.child_by_field_name("bound")
            if bound is not None:
                bounds.append(bound)
        return bounds

    def _collect_local_variable_types(self, node: Any, variable_types: dict[str, Any]) -> None:
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in {"val_definition", "var_definition"}:
                self._register_field_type(current, variable_types)
            stack.extend(reversed(current.named_children))

    def _make_node(
        self,
        node: Any,
        component_id: str,
        name: str,
        component_type: str,
        node_type: str,
        package: str,
        logical_name: str,
        parent: Optional[str] = None,
        parameters: Optional[list[str]] = None,
    ) -> Node:
        lines = self.content.splitlines()
        start = node.start_point[0]
        end = node.end_point[0]
        source_code = "\n".join(lines[start : end + 1])
        docstring = self._docstring(node)
        base_classes = None
        if node.type in _TYPE_NODES:
            extend = node.child_by_field_name("extend")
            if extend is not None:
                base_classes = []
                for type_node in extend.children_by_field_name("type"):
                    if not type_node.is_named:
                        continue
                    text = type_node.text.decode("utf8").strip()
                    base = text.split("[", 1)[0].strip().removeprefix("_root_.")
                    if base and base not in base_classes:
                        base_classes.append(base)
        return Node(
            id=component_id,
            name=name,
            component_type=component_type,
            file_path=str(self.file_path),
            relative_path=self.relative_path,
            source_code=source_code,
            start_line=start + 1,
            end_line=end + 1,
            has_docstring=bool(docstring),
            docstring=docstring,
            parameters=parameters,
            node_type=node_type,
            base_classes=base_classes,
            class_name=parent,
            display_name=f"{component_type} {logical_name}",
            component_id=component_id,
            language="scala",
            qualified_name=f"{package}.{logical_name}" if package else logical_name,
        )

    def _docstring(self, node: Any) -> str:
        comments: list[str] = []
        previous = node.prev_sibling
        while previous is not None and previous.type in {"block_comment", "line_comment"}:
            comments.append(previous.text.decode("utf8"))
            previous = previous.prev_sibling
        if not comments:
            return ""
        cleaned: list[str] = []
        for raw in reversed(comments):
            text = raw.strip()
            if text.startswith("/**"):
                text = text[3:]
            if text.endswith("*/"):
                text = text[:-2]
            text = text.strip()
            if text.startswith("*"):
                text = text[1:].lstrip()
            if text.startswith("//"):
                text = text[2:].lstrip()
            if text:
                cleaned.append(text)
        return "\n".join(cleaned)

    def _drop_ambiguous_component_ids(self) -> None:
        """组件 ID 不含签名；同名重载全部弃权，避免后声明覆盖先声明。"""
        counts: dict[str, int] = {}
        for item in self.nodes:
            counts[item.id] = counts.get(item.id, 0) + 1
        ambiguous = {component_id for component_id, count in counts.items() if count > 1}
        if not ambiguous:
            return
        self.nodes = [item for item in self.nodes if item.id not in ambiguous]
        self._definitions = [
            definition for definition in self._definitions if definition.node.id not in ambiguous
        ]
        self.call_relationships = [
            relationship
            for relationship in self.call_relationships
            if relationship.caller not in ambiguous and relationship.callee not in ambiguous
        ]
        self._owner_methods = {
            (package, parent, name)
            for package, parent, name in self._owner_methods
            if self._component_id(f"{parent}.{name}") not in ambiguous
        }
        self._top_level_names = {
            (package, name)
            for package, name in self._top_level_names
            if self._component_id(name) not in ambiguous
        }

    def _extract_relationships(self) -> None:
        for definition in self._definitions:
            caller = definition.node.id
            for type_node in definition.type_nodes:
                for reference in self._type_references(
                    type_node, definition.package, definition.imports
                ):
                    self._add_relationship(
                        caller, reference, definition.ast_node.start_point[0] + 1
                    )
            if definition.node.component_type not in {"method", "function"}:
                continue
            body = definition.ast_node.child_by_field_name("body")
            if body is not None:
                self._extract_body_relationships(body, definition)

    def _extract_body_relationships(
        self,
        node: Any,
        definition: _Definition,
        variable_types: Optional[dict[str, Any]] = None,
    ) -> None:
        # block / lambda 是词法作用域：子作用域的 val/var 不得污染兄弟 block。
        scope = definition.variable_types if variable_types is None else variable_types
        if node.type in {"block", "lambda_expression", "function_expression"}:
            scope = dict(scope)
        if node.type in {"val_definition", "var_definition"}:
            self._register_field_type(node, scope)
        if node.type == "instance_expression":
            type_node = next(
                (
                    child
                    for child in node.named_children
                    if child.type in {"type_identifier", "generic_type", "stable_identifier"}
                ),
                None,
            )
            if type_node is not None:
                for reference in self._type_references(
                    type_node, definition.package, definition.imports
                ):
                    self._add_relationship(definition.node.id, reference, node.start_point[0] + 1)
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                self._extract_call(function, node, definition, scope)
        for child in node.named_children:
            child_scope = (
                dict(scope)
                if child.type
                in {
                    "block",
                    "lambda_expression",
                    "function_expression",
                }
                else scope
            )
            self._extract_body_relationships(child, definition, child_scope)

    @staticmethod
    def _receiver_chain(receiver: Any) -> Optional[tuple[Any, list[str]]]:
        fields: list[str] = []
        current = receiver
        while current.type == "field_expression":
            field = current.child_by_field_name("field")
            value = current.child_by_field_name("value")
            if field is None or value is None:
                return None
            fields.append(field.text.decode("utf8"))
            current = value
        if current.type != "identifier":
            return None
        return current, list(reversed(fields))

    def _extract_call(
        self,
        function: Any,
        call: Any,
        definition: _Definition,
        variable_types: dict[str, Any],
    ) -> None:
        if function.type == "identifier":
            name = function.text.decode("utf8")
            if name in _CALL_NOISE:
                return
            if name[:1].isupper():
                references = self._visible_refs(
                    definition.package, definition.imports, name, kind="@companion"
                )
            elif (
                definition.parent
                and (
                    definition.package,
                    definition.parent,
                    name,
                )
                in self._owner_methods
            ):
                references = {scala_package_ref(definition.package, f"{definition.parent}.{name}")}
            elif definition.parent and len(self._owner_base_classes(definition)) == 1:
                # 单一继承基类的成员先于同包顶层函数；多基类线性化不在本切片内。
                references = set()
                base = self._owner_base_classes(definition)[0]
                for packages, symbol in self._type_candidates(
                    base, definition.package, definition.imports
                ):
                    references.add(self._candidate_ref(packages, f"{symbol}.{name}"))
                # 顶层函数仅作后备：任一继承成员解析成功时不得再绑定。
                if (definition.package, name) in self._top_level_names:
                    fallback = json.dumps([name, *sorted(references)], separators=(",", ":"))
                    references.add(scala_package_ref(definition.package, f"@fallback:{fallback}"))
            elif (definition.package, name) in self._top_level_names:
                references = {scala_package_ref(definition.package, name)}
            elif name in definition.imports.explicit or definition.imports.wildcards:
                references = self._visible_refs(definition.package, definition.imports, name)
                if not references:
                    references = {scala_package_ref(definition.package, name)}
            else:
                references = {scala_package_ref(definition.package, name)}
            for reference in references:
                self._add_relationship(definition.node.id, reference, call.start_point[0] + 1)
            return

        if function.type != "field_expression":
            return
        receiver = function.child_by_field_name("value")
        field_node = function.child_by_field_name("field")
        if receiver is None or field_node is None:
            return
        method = field_node.text.decode("utf8")
        receiver_name = receiver.text.decode("utf8") if receiver.type == "identifier" else ""
        if receiver.type in {"this", "super"} or receiver_name in {"this", "super"}:
            if not definition.parent:
                return
            if receiver.type == "this" or receiver_name == "this":
                self._add_relationship(
                    definition.node.id,
                    scala_package_ref(definition.package, f"{definition.parent}.{method}"),
                    call.start_point[0] + 1,
                )
                return
            bases = self._owner_base_classes(definition)
            if len(bases) != 1:
                return
            for packages, symbol in self._type_candidates(
                bases[0], definition.package, definition.imports
            ):
                self._add_relationship(
                    definition.node.id,
                    self._candidate_ref(packages, f"{symbol}.{method}"),
                    call.start_point[0] + 1,
                )
            return
        if receiver.type == "identifier":
            receiver_name = receiver.text.decode("utf8")
            type_node = variable_types.get(receiver_name)
            if type_node is not None:
                for reference in self._method_references(
                    type_node, method, definition.package, definition.imports
                ):
                    self._add_relationship(definition.node.id, reference, call.start_point[0] + 1)
                return
            if receiver_name[:1].isupper():
                for reference in self._visible_refs(
                    definition.package,
                    definition.imports,
                    f"{receiver_name}.{method}",
                    kind="@static",
                ):
                    self._add_relationship(definition.node.id, reference, call.start_point[0] + 1)
            return
        if receiver.type in {"field_expression", "stable_identifier", "stable_type_identifier"}:
            chain = self._receiver_chain(receiver) if receiver.type == "field_expression" else None
            if chain is not None:
                root, fields = chain
                root_name = root.text.decode("utf8")
                root_type = variable_types.get(root_name)
                if root_type is not None:
                    for name in self._type_names(root_type):
                        for packages, symbol in self._type_candidates(
                            name, definition.package, definition.imports
                        ):
                            reference = self._candidate_ref(
                                packages, f"@chain:{symbol}|{'.'.join(fields)}|{method}"
                            )
                            self._add_relationship(
                                definition.node.id, reference, call.start_point[0] + 1
                            )
                    return
            names = (
                {receiver.text.decode("utf8").strip().removeprefix("_root_.")}
                if receiver.type == "field_expression"
                else self._type_names(receiver)
            )
            for name in names:
                for packages, symbol in self._type_candidates(
                    name, definition.package, definition.imports
                ):
                    reference = self._candidate_ref(packages, f"{symbol.rstrip('$')}$.{method}")
                    self._add_relationship(definition.node.id, reference, call.start_point[0] + 1)

    def _type_references(self, type_node: Any, package: str, imports: _Imports) -> set[str]:
        references: set[str] = set()
        for name in self._type_names(type_node):
            if name in _PRIMITIVE_TYPES:
                continue
            for packages, symbol in self._type_candidates(name, package, imports):
                references.add(self._candidate_ref(packages, f"@type:{symbol}"))
        return references

    def _method_references(
        self, type_node: Any, method: str, package: str, imports: _Imports
    ) -> set[str]:
        references: set[str] = set()
        for name in self._type_names(type_node):
            if name in _PRIMITIVE_TYPES:
                continue
            for packages, symbol in self._type_candidates(name, package, imports):
                references.add(self._candidate_ref(packages, f"{symbol}.{method}"))
        return references

    def _type_candidates(
        self, name: str, package: str, imports: _Imports
    ) -> list[tuple[list[str], str]]:
        if "." not in name:
            imported = imports.explicit.get(name)
            if imported is not None:
                imported_package, symbol = imported
                return [([imported_package], symbol)]
            return [([package, *sorted(imports.wildcards)], name)]

        first, remainder = name.split(".", 1)
        imported = imports.explicit.get(first)
        if imported is not None:
            imported_package, imported_symbol = imported
            return [([imported_package], f"{imported_symbol}.{remainder}")]
        return [([".".join(name.split(".")[:-1])], name.rsplit(".", 1)[-1])]

    def _persisted_type_name(self, type_node: Any, package: str, imports: _Imports) -> str:
        """把可唯一确定的字段类型固化为 package 路径，避免增量时误绑同包同名类。"""
        names = self._type_names(type_node)
        if len(names) != 1:
            return ""
        candidates = self._type_candidates(next(iter(names)), package, imports)
        if len(candidates) != 1:
            return ""
        packages, symbol = candidates[0]
        unique = sorted(set(packages))
        if len(unique) != 1:
            return ""
        return f"{unique[0]}.{symbol}" if unique[0] else symbol

    @staticmethod
    def _candidate_ref(packages: list[str], symbol: str) -> str:
        unique = sorted(set(packages))
        package = unique[0] if len(unique) == 1 else f"@wild:{'|'.join(unique)}"
        return scala_package_ref(package, symbol)

    def _type_names(self, node: Any) -> set[str]:
        names: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in {"stable_identifier", "stable_type_identifier"}:
                text = current.text.decode("utf8").strip().removeprefix("_root_.")
                if text:
                    names.add(text)
                continue
            if current.type == "type_identifier":
                text = current.text.decode("utf8").strip()
                if text:
                    names.add(text)
            stack.extend(reversed(current.named_children))
        return names

    def _visible_refs(self, package: str, imports: _Imports, name: str, kind: str = "") -> set[str]:
        references: set[str] = set()
        prefix = f"{kind}:" if kind else ""
        if "." in name:
            parts = name.split(".")
            first, remainder = parts[0], ".".join(parts[1:])
            imported = imports.explicit.get(first)
            if imported is not None:
                imported_package, imported_symbol = imported
                symbol = f"{imported_symbol}.{remainder}" if remainder else imported_symbol
                references.add(scala_package_ref(imported_package, f"{prefix}{symbol}"))
            elif kind == "@static" and len(parts) >= 2:
                references.add(
                    scala_package_ref(".".join(parts[:-1]), f"{prefix}{parts[-2]}.{parts[-1]}")
                )
            else:
                references.add(scala_package_ref(".".join(parts[:-1]), f"{prefix}{parts[-1]}"))
            return references

        imported = imports.explicit.get(name)
        if imported is not None:
            imported_package, imported_symbol = imported
            references.add(scala_package_ref(imported_package, f"{prefix}{imported_symbol}"))
            return references

        if name[:1].isupper() or kind or imports.wildcards:
            references.add(
                self._candidate_ref([package, *sorted(imports.wildcards)], f"{prefix}{name}")
            )
        return references

    def _add_relationship(self, caller: str, callee: str, line: int) -> None:
        key = (caller, callee, line)
        if key in self._seen_relationships:
            return
        self._seen_relationships.add(key)
        self.call_relationships.append(
            CallRelationship(caller=caller, callee=callee, call_line=line, is_resolved=False)
        )


def analyze_scala_file(
    file_path: str, content: str, repo_path: Optional[str] = None
) -> tuple[list[Node], list[CallRelationship]]:
    """函数式入口，保持与其他语言薄适配一致的契约。"""
    analyzer = TreeSitterScalaAnalyzer(file_path, content, repo_path=repo_path)
    return analyzer.nodes, analyzer.call_relationships
