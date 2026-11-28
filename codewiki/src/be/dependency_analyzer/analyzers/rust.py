"""Tree-sitter Rust 源码分析器。

提取 struct/union/enum/trait、自由函数与 impl/trait 方法，并建立字段类型、
trait 实现、结构体实例化和调用边。组件 ID 沿用 ``相对路径::逻辑名``；
方法使用 ``Type.method``，避免与路径分隔符 ``::`` 冲突。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import get_parser

logger = logging.getLogger(__name__)

_TYPE_NODES = ("struct_item", "union_item", "enum_item", "trait_item")
_FUNCTION_NODES = ("function_item", "function_signature_item")
_TYPE_MAPPING = {
    "struct_item": ("struct", "struct"),
    "union_item": ("struct", "union"),
    "enum_item": ("class", "enum"),
    "trait_item": ("interface", "trait"),
}
_EXTERNAL_ROOTS = frozenset({"std", "core", "alloc"})
_PRIMITIVE_TYPES = frozenset(
    {
        "i8",
        "i16",
        "i32",
        "i64",
        "i128",
        "isize",
        "u8",
        "u16",
        "u32",
        "u64",
        "u128",
        "usize",
        "f32",
        "f64",
        "bool",
        "char",
        "str",
        "String",
        "Self",
        "Vec",
        "VecDeque",
        "Option",
        "Result",
        "Box",
        "Rc",
        "Arc",
        "Weak",
        "RefCell",
        "Cell",
        "Mutex",
        "RwLock",
        "HashMap",
        "HashSet",
        "BTreeMap",
        "BTreeSet",
        "BinaryHeap",
        "Cow",
        "PhantomData",
        "Pin",
        "Path",
        "PathBuf",
        "Duration",
        "Instant",
        "Error",
    }
)
_CALL_NOISE = frozenset(
    {
        "Some",
        "Ok",
        "Err",
        "Box",
        "drop",
        "unwrap",
        "unwrap_or",
        "unwrap_or_else",
        "unwrap_or_default",
        "expect",
        "clone",
        "cloned",
        "copied",
        "to_string",
        "to_owned",
        "into",
        "from",
        "try_into",
        "try_from",
        "as_ref",
        "as_mut",
        "as_str",
        "as_slice",
        "borrow",
        "borrow_mut",
        "deref",
        "iter",
        "iter_mut",
        "into_iter",
        "map",
        "map_err",
        "and_then",
        "or_else",
        "ok",
        "ok_or",
        "ok_or_else",
        "filter",
        "filter_map",
        "flat_map",
        "for_each",
        "fold",
        "collect",
        "enumerate",
        "zip",
        "chain",
        "rev",
        "take",
        "skip",
        "any",
        "all",
        "find",
        "position",
        "count",
        "sum",
        "min",
        "max",
        "sort",
        "sort_by",
        "sort_by_key",
        "dedup",
        "push",
        "push_str",
        "pop",
        "insert",
        "remove",
        "get",
        "get_mut",
        "entry",
        "or_insert",
        "or_insert_with",
        "or_default",
        "contains",
        "contains_key",
        "extend",
        "retain",
        "clear",
        "len",
        "is_empty",
        "is_some",
        "is_none",
        "is_ok",
        "is_err",
        "lock",
        "read",
        "write",
        "join",
        "split",
        "trim",
        "starts_with",
        "ends_with",
        "format",
        "fmt",
        "eq",
        "cmp",
        "partial_cmp",
        "hash",
        "default",
        "new",
        "with_capacity",
    }
)


def _text(node: Any | None) -> str | None:
    return node.text.decode("utf-8", errors="replace") if node is not None else None


class TreeSitterRustAnalyzer:
    def __init__(self, file_path: str, content: str, repo_path: str | None = None):
        self.file_path = Path(file_path)
        self.content = content
        self.repo_path = repo_path or ""
        self.nodes: list[Node] = []
        self.call_relationships: list[CallRelationship] = []
        self.symbols: dict[str, Node] = {}
        self.imports: dict[str, dict[str, str]] = {}
        self.module_paths: set[str] = set()
        self.impl_bases: list[tuple[str, str, int]] = []
        self.seen_relationships: set[tuple[str, str, int | None]] = set()
        self._analyze()

    def _relative_path(self) -> str:
        if not self.repo_path:
            return str(self.file_path)
        try:
            return os.path.relpath(
                os.path.realpath(self.file_path), os.path.realpath(self.repo_path)
            ).replace(os.sep, "/")
        except ValueError:
            return str(self.file_path)

    def _analyze(self) -> None:
        # grammar 预检失败必须显式抛出，不能退化成空组件列表。
        parser = get_parser("rust")
        tree = parser.parse(self.content.encode("utf-8"))
        root = tree.root_node
        lines = self.content.splitlines()
        self.module_paths = self._collect_module_paths(root)
        self._extract_imports(root)
        self._extract_nodes(root, lines)
        self._attach_impl_bases(root)
        self._extract_relationships(root)

    @staticmethod
    def _field_text(node: Any, field: str) -> str | None:
        return _text(node.child_by_field_name(field))

    def _extract_imports(self, node: Any) -> None:
        if self._is_test_module(node):
            return
        if node.type == "use_declaration":
            argument = next(
                (
                    child
                    for child in node.named_children
                    if child.type not in ("attribute_item", "visibility_modifier")
                ),
                None,
            )
            self._record_use(argument, module=self._module_prefix(node))
            return
        for child in node.children:
            self._extract_imports(child)

    def _record_use(self, node: Any | None, base: str = "", module: str = "") -> None:
        if node is None:
            return
        imports = self.imports.setdefault(module, {})
        if node.type == "identifier":
            name = _text(node) or ""
            target = f"{base}.{name}" if base else name
            imports.setdefault(name, target)
            return
        if node.type == "self":
            if base:
                imports.setdefault(base.rsplit(".", 1)[-1], base)
            return
        if node.type == "use_as_clause":
            children = node.named_children
            if len(children) >= 2:
                raw_source = _text(children[0])
                if base and raw_source and "::" not in raw_source:
                    raw_source = f"{base}::{raw_source}"
                source = self._normalize_path(node, raw_source)
                alias = _text(children[1])
                if source and alias:
                    imports.setdefault(alias, source)
            return
        if node.type == "scoped_identifier":
            source = self._normalize_path(node, _text(node))
            if source:
                imports.setdefault(source.rsplit(".", 1)[-1], source)
            return
        if node.type == "scoped_use_list":
            children = node.named_children
            if len(children) >= 2:
                source = self._normalize_path(node, _text(children[0]))
                self._record_use(children[1], source or "", module)
            return
        if node.type == "use_list":
            for child in node.named_children:
                self._record_use(child, base, module)

    @staticmethod
    def _preceding(node: Any) -> list[Any]:
        result = []
        sibling = node.prev_sibling
        while sibling is not None and sibling.type in (
            "attribute_item",
            "line_comment",
            "block_comment",
        ):
            result.append(sibling)
            sibling = sibling.prev_sibling
        return result

    def _is_test_module(self, node: Any) -> bool:
        if node.type != "mod_item":
            return False
        for attr in self._preceding(node):
            compact = "".join((_text(attr) or "").split())
            if compact.startswith("#[cfg(") and re.search(r"(?<![\w])test(?![\w])", compact):
                return not bool(re.search(r"not\(test\)", compact))
        return False

    def _file_module_prefix(self) -> str:
        relative = Path(self._relative_path()).with_suffix("")
        parts = list(relative.parts)
        if not parts or parts[0] != "src":
            return ""
        parts.pop(0)
        if parts and parts[-1] in ("lib", "main", "mod"):
            parts.pop()
        return ".".join(parts)

    def _collect_module_paths(self, node: Any) -> set[str]:
        paths: set[str] = set()
        if self._is_test_module(node):
            return paths
        if node.type == "mod_item":
            name = self._field_text(node, "name")
            if name:
                paths.add(self._qualify(node, name))
        for child in node.children:
            paths.update(self._collect_module_paths(child))
        return paths

    def _module_prefix(self, node: Any) -> str:
        modules = []
        current = node.parent
        while current is not None:
            if current.type == "mod_item":
                name = self._field_text(current, "name")
                if name:
                    modules.append(name)
            current = current.parent
        file_prefix = self._file_module_prefix()
        parts = [file_prefix, *reversed(modules)] if file_prefix else list(reversed(modules))
        return ".".join(parts)

    def _qualify(self, node: Any, name: str) -> str:
        prefix = self._module_prefix(node)
        return f"{prefix}.{name}" if prefix else name

    def _normalize_path(self, node: Any | None, raw: str | None) -> str | None:
        if not raw:
            return None
        segments = [part.split("<")[0] for part in raw.replace(" ", "").split("::") if part]
        if not segments:
            return None
        if segments[0] in _EXTERNAL_ROOTS:
            return None
        current_module = self._module_prefix(node) if node is not None else ""
        if segments[0] == "crate":
            segments.pop(0)
            prefix = ""
        elif segments[0] == "self":
            segments.pop(0)
            prefix = current_module
        elif segments[0] == "super":
            parents = 0
            while segments and segments[0] == "super":
                segments.pop(0)
                parents += 1
            module_parts = current_module.split(".") if current_module else []
            remove = max(0, len(module_parts) - parents)
            prefix = ".".join(module_parts[:remove])
        else:
            imported = self.imports.get(current_module, {}).get(segments[0])
            if imported:
                return ".".join([imported, *segments[1:]])
            if len(segments) == 1:
                prefix = current_module
            else:
                relative = ".".join([current_module, *segments]) if current_module else ""
                child_prefix = f"{current_module}." if current_module else ""
                if child_prefix and any(
                    module.startswith(child_prefix)
                    and (
                        module == relative
                        or module.startswith(f"{relative}.")
                        or relative.startswith(f"{module}.")
                    )
                    for module in self.module_paths
                ):
                    return relative
                return ".".join(segments)
        suffix = ".".join(segments)
        return f"{prefix}.{suffix}" if prefix else suffix

    def _type_name(self, node: Any | None) -> str | None:
        if node is None:
            return None
        if node.type in ("type_identifier", "identifier"):
            name = _text(node)
            if name in _PRIMITIVE_TYPES:
                return name
            return self._normalize_path(node, name)
        if node.type in ("generic_type", "reference_type", "pointer_type"):
            return self._type_name(node.child_by_field_name("type"))
        if node.type in ("scoped_type_identifier", "scoped_identifier"):
            path = node.child_by_field_name("path")
            name = self._field_text(node, "name")
            raw = f"{_text(path)}::{name}" if path is not None and name else name
            return self._normalize_path(node, raw)
        return None

    def _owner_name(self, node: Any) -> str | None:
        name = (
            self._type_name(node.child_by_field_name("type"))
            if node.type == "impl_item"
            else self._field_text(node, "name")
        )
        if node.type != "impl_item" and name:
            name = self._qualify(node, name)
        return name

    def _impl_trait(self, node: Any) -> str | None:
        current = node.parent if node is not None else None
        while current is not None:
            if current.type == "impl_item":
                return self._type_name(current.child_by_field_name("trait"))
            if current.type in _FUNCTION_NODES or current.type == "mod_item":
                return None
            current = current.parent
        return None

    def _method_name(self, node: Any, owner: str, name: str) -> str:
        trait = self._impl_trait(node)
        return f"{owner}.{trait}.{name}" if trait else f"{owner}.{name}"

    def _containing_type(self, node: Any) -> str | None:
        current = node.parent
        while current is not None:
            if current.type in _FUNCTION_NODES:
                return None
            if current.type in _TYPE_NODES or current.type == "impl_item":
                return self._owner_name(current)
            if current.type == "mod_item":
                return None
            current = current.parent
        return None

    def _containing_function(self, node: Any) -> Any | None:
        current = node.parent
        while current is not None:
            if current.type in _FUNCTION_NODES:
                return current
            current = current.parent
        return None

    def _context_owner(self, node: Any) -> str | None:
        function = self._containing_function(node)
        return self._containing_type(function if function is not None else node)

    def _function_name(self, node: Any) -> str | None:
        name = self._field_text(node, "name")
        if not name:
            return None
        if node.type == "function_item":
            outer = self._containing_function(node.parent)
            if outer is not None:
                outer_name = self._function_name(outer)
                return f"{outer_name}.{name}" if outer_name else name
        owner = self._containing_type(node)
        return self._method_name(node, owner, name) if owner else self._qualify(node, name)

    def _resolve_caller(self, node: Any) -> str | None:
        function = self._containing_function(node)
        if function is not None:
            name = self._function_name(function)
            symbol = self.symbols.get(name) if name else None
            if symbol is not None:
                return symbol.id
        owner = self._context_owner(node)
        symbol = self.symbols.get(owner) if owner else None
        return symbol.id if symbol is not None else None

    def _extract_nodes(self, node: Any, lines: list[str]) -> None:
        if self._is_test_module(node):
            return
        component_type = node_type = logical_name = class_name = None
        parameters = None
        if node.type in _TYPE_NODES:
            logical_name = self._owner_name(node)
            if logical_name:
                component_type, node_type = _TYPE_MAPPING[node.type]
        elif node.type in _FUNCTION_NODES:
            name = self._field_text(node, "name")
            if name:
                parameters = self._parameters(node)
                owner = self._containing_type(node)
                if owner:
                    component_type = node_type = "method"
                    logical_name = self._method_name(node, owner, name)
                    class_name = owner
                elif node.type == "function_item":
                    component_type = node_type = "function"
                    logical_name = self._function_name(node)
        if component_type and logical_name and node_type:
            self._add_node(
                node,
                logical_name,
                component_type,
                node_type,
                lines,
                class_name=class_name,
                parameters=parameters,
            )
        for child in node.children:
            self._extract_nodes(child, lines)

    def _parameters(self, node: Any) -> list[str] | None:
        params = node.child_by_field_name("parameters")
        if params is None:
            return None
        values = [
            (_text(child) or "").strip()
            for child in params.children
            if child.type in ("parameter", "self_parameter", "variadic_parameter")
        ]
        return values or None

    def _docstring(self, node: Any) -> str:
        comments = []
        for sibling in self._preceding(node):
            if sibling.type == "attribute_item":
                continue
            text = _text(sibling) or ""
            if not text.startswith(("///", "//!", "/**", "/*!")):
                break
            comments.append(text.strip())
        return "\n".join(reversed(comments))

    def _add_node(
        self,
        node: Any,
        logical_name: str,
        component_type: str,
        node_type: str,
        lines: list[str],
        *,
        class_name: str | None,
        parameters: list[str] | None,
    ) -> None:
        component_id = f"{self._relative_path()}::{logical_name}"
        start = node.start_point[0]
        end = node.end_point[0] + 1
        docstring = self._docstring(node)
        result = Node(
            id=component_id,
            name=logical_name,
            component_type=component_type,
            file_path=str(self.file_path),
            relative_path=self._relative_path(),
            source_code="\n".join(lines[start:end]),
            start_line=start + 1,
            end_line=node.end_point[0] + 1,
            has_docstring=bool(docstring),
            docstring=docstring,
            parameters=parameters,
            node_type=node_type,
            class_name=class_name,
            display_name=f"{node_type} {logical_name}",
            component_id=component_id,
            language="rust",
        )
        self.nodes.append(result)
        self.symbols[logical_name] = result

    def _attach_impl_bases(self, node: Any) -> None:
        if self._is_test_module(node):
            return
        if node.type == "impl_item":
            trait = self._type_name(node.child_by_field_name("trait"))
            owner = self._owner_name(node)
            symbol = self.symbols.get(owner) if owner else None
            if trait and symbol is not None:
                bases = symbol.base_classes or []
                if trait not in bases:
                    symbol.base_classes = [*bases, trait]
            if trait and owner:
                self.impl_bases.append((owner, trait, node.start_point[0] + 1))
        for child in node.children:
            self._attach_impl_bases(child)

    def _extract_relationships(self, node: Any) -> None:
        if self._is_test_module(node):
            return
        if node.type == "impl_item":
            self._impl_edge(node)
        elif node.type in ("field_declaration", "ordered_field_declaration_list"):
            self._field_edges(node)
        elif node.type == "struct_expression":
            self._instantiation_edge(node)
        elif node.type == "call_expression":
            self._call_edge(node)
        for child in node.children:
            self._extract_relationships(child)

    def _type_params(self, node: Any) -> set[str]:
        result = set()
        current = node
        while current is not None:
            params = current.child_by_field_name("type_parameters")
            if params is not None:
                for param in params.named_children:
                    name_node = param.child_by_field_name("name")
                    if name_node is None and param.type == "type_identifier":
                        name_node = param
                    name = _text(name_node)
                    if name:
                        result.add(name)
            current = current.parent
        return result

    def _collect_types(self, node: Any | None) -> list[str]:
        names: list[str] = []
        if node is None:
            return names
        generics = self._type_params(node)

        def walk(current: Any | None) -> None:
            if current is None:
                return
            name = self._type_name(current)
            if name and name not in _PRIMITIVE_TYPES and name not in generics and name not in names:
                names.append(name)
            if current.type in ("generic_type", "reference_type", "pointer_type"):
                if current.type != "generic_type":
                    walk(current.child_by_field_name("type"))
                args = current.child_by_field_name("type_arguments")
                if args is not None:
                    for arg in args.children:
                        walk(arg)
            elif current.type in ("tuple_type", "array_type"):
                for child in current.children:
                    walk(child)

        walk(node)
        return names

    def _field_owner(self, node: Any) -> str | None:
        current = node.parent
        while current is not None:
            if current.type in _TYPE_NODES:
                return self._owner_name(current)
            current = current.parent
        return None

    def _field_edges(self, node: Any) -> None:
        owner = self._field_owner(node)
        symbol = self.symbols.get(owner) if owner else None
        caller = symbol.id if symbol is not None else None
        if not caller:
            return
        type_nodes = (
            [node.child_by_field_name("type")]
            if node.type == "field_declaration"
            else node.children_by_field_name("type")
        )
        for type_node in type_nodes:
            for name in self._collect_types(type_node):
                self._type_edge(caller, name, node.start_point[0] + 1)

    def _impl_edge(self, node: Any) -> None:
        trait = self._type_name(node.child_by_field_name("trait"))
        owner = self._owner_name(node)
        symbol = self.symbols.get(owner) if owner else None
        if trait and symbol is not None and trait not in _PRIMITIVE_TYPES:
            self._type_edge(symbol.id, trait, node.start_point[0] + 1)

    def _instantiation_edge(self, node: Any) -> None:
        caller = self._resolve_caller(node)
        if not caller:
            return
        name_node = node.child_by_field_name("name")
        name = self._type_name(name_node)
        if name == "Self":
            name = self._context_owner(node)
        if name and name not in _PRIMITIVE_TYPES:
            self._type_edge(caller, name, node.start_point[0] + 1)

    def _call_edge(self, node: Any) -> None:
        caller = self._resolve_caller(node)
        function = node.child_by_field_name("function")
        if not caller or function is None:
            return
        if function.type == "generic_function":
            function = function.child_by_field_name("function")
        if function is None:
            return
        line = node.start_point[0] + 1
        if function.type == "identifier":
            name = _text(function)
            if name:
                self._bare_call(caller, name, node, line)
        elif function.type == "scoped_identifier":
            self._path_call(caller, function, node, line)
        elif function.type == "field_expression":
            self._method_call(caller, function, node, line)

    def _resolve(self, *names: str | None) -> str | None:
        for name in names:
            symbol = self.symbols.get(name) if name else None
            if symbol is not None:
                return symbol.id
        return None

    def _bare_call(self, caller: str, name: str, node: Any, line: int) -> None:
        owner = self._context_owner(node)
        imported = self.imports.get(self._module_prefix(node), {}).get(name)
        function = self._containing_function(node)
        function_name = self._function_name(function) if function is not None else None
        candidates = [
            f"{function_name}.{name}" if function_name else None,
            self._qualify(node, name),
            imported,
            f"{owner}.{name}" if owner else None,
            name,
        ]
        resolved = self._resolve(*candidates)
        if resolved:
            self._edge(caller, resolved, line, True)
        elif name not in _CALL_NOISE:
            self._edge(caller, name, line, False)

    @staticmethod
    def _segments(node: Any) -> list[str]:
        return [part for part in (_text(node) or "").replace(" ", "").split("::") if part]

    def _method_symbol(self, owner: str | None, name: str) -> Node | None:
        if not owner:
            return None
        inherent = self.symbols.get(f"{owner}.{name}")
        if inherent is not None:
            return inherent
        prefix = f"{owner}."
        matches = [
            symbol
            for logical, symbol in self.symbols.items()
            if logical.startswith(prefix)
            and logical.endswith(f".{name}")
            and symbol.component_type == "method"
            and symbol.class_name == owner
        ]
        return matches[0] if len(matches) == 1 else None

    def _method_edge(self, caller: str, owner: str | None, name: str, node: Any, line: int) -> None:
        if not owner:
            return
        resolved = self._method_symbol(owner, name)
        if resolved is not None:
            self._edge(caller, resolved.id, line, True)
        elif name not in _CALL_NOISE or owner not in _PRIMITIVE_TYPES:
            self._edge(caller, f"{owner}.{name}", line, False)

    def _path_call(self, caller: str, function: Any, node: Any, line: int) -> None:
        raw_segments = [
            part.split("<")[0] for part in self._segments(function) if not part.startswith("<")
        ]
        raw_segments = [part for part in raw_segments if part]
        if not raw_segments or raw_segments[0] in _EXTERNAL_ROOTS:
            return
        qualifier = None
        if len(raw_segments) >= 2 and raw_segments[-2] == "Self":
            qualifier = self._context_owner(node)
        elif len(raw_segments) >= 2 and raw_segments[-2][:1].isupper():
            qualifier = self._normalize_path(node, "::".join(raw_segments[:-1]))
            if qualifier in _PRIMITIVE_TYPES:
                return
        name = raw_segments[-1]
        if qualifier:
            self._method_edge(caller, qualifier, name, node, line)
            return
        normalized = self._normalize_path(node, "::".join(raw_segments))
        resolved = self._resolve(normalized, self._qualify(node, normalized or ""))
        if resolved:
            self._edge(caller, resolved, line, True)
        elif name not in _CALL_NOISE:
            self._edge(caller, "::".join(raw_segments), line, False)

    def _method_call(self, caller: str, function: Any, node: Any, line: int) -> None:
        receiver = function.child_by_field_name("value")
        method = _text(function.child_by_field_name("field"))
        if receiver is None or not method:
            return
        owner = self._context_owner(node)
        if receiver.type == "self":
            self._method_edge(caller, owner, method, node, line)
            return
        var_type = None
        if receiver.type == "identifier":
            var_type = self._variable_type(node, _text(receiver))
        elif receiver.type == "field_expression":
            var_type = self._self_field_type(node, receiver)
        self._method_edge(caller, var_type, method, node, line)

    def _self_field_type(self, node: Any, expression: Any) -> str | None:
        value = expression.child_by_field_name("value")
        field = _text(expression.child_by_field_name("field"))
        if value is None or value.type != "self" or not field:
            return None
        owner = self._context_owner(node)
        if owner not in self.symbols:
            return None
        root = node
        while root.parent is not None:
            root = root.parent
        stack = [root]
        while stack:
            current = stack.pop()
            if current.type == "struct_item" and self._owner_name(current) == owner:
                body = current.child_by_field_name("body")
                if body is not None:
                    for decl in body.children:
                        if (
                            decl.type == "field_declaration"
                            and self._field_text(decl, "name") == field
                        ):
                            names = self._collect_types(decl.child_by_field_name("type"))
                            return names[0] if names else None
                return None
            stack.extend(current.children)
        return None

    def _variable_type(self, node: Any, name: str | None) -> str | None:
        if not name:
            return None
        function = self._containing_function(node)
        if function is None:
            return None
        block = node.parent
        while block is not None and block is not function:
            if block.type == "block":
                for child in reversed(block.children):
                    if child.start_byte >= node.start_byte:
                        continue
                    if (
                        child.type == "let_declaration"
                        and self._field_text(child, "pattern") == name
                    ):
                        return self._let_type(child, node)
            block = block.parent
        params = function.child_by_field_name("parameters")
        if params is not None:
            for param in params.children:
                if param.type == "parameter" and self._field_text(param, "pattern") == name:
                    names = self._collect_types(param.child_by_field_name("type"))
                    return names[0] if names else None
        return None

    def _let_type(self, declaration: Any, use: Any) -> str | None:
        names = self._collect_types(declaration.child_by_field_name("type"))
        if names:
            return names[0]
        value = declaration.child_by_field_name("value")
        while value is not None and value.type in ("try_expression", "await_expression"):
            value = value.named_children[0] if value.named_children else None
        if value is None:
            return None
        if value.type == "struct_expression":
            name = self._type_name(value.child_by_field_name("name"))
            if name == "Self":
                return self._containing_type(use)
            return name if name and name not in _PRIMITIVE_TYPES else None
        if value.type == "identifier":
            name = self._type_name(value)
            return name if name and name not in _PRIMITIVE_TYPES else None
        if value.type == "call_expression":
            function = value.child_by_field_name("function")
            if function is not None and function.type == "scoped_identifier":
                segments = self._segments(function)
                if len(segments) >= 2:
                    qualifier = self._normalize_path(function, "::".join(segments[:-1]))
                    if qualifier == "Self":
                        return self._containing_type(use)
                    if qualifier and qualifier.split(".")[-1][:1].isupper():
                        if qualifier not in _PRIMITIVE_TYPES:
                            return qualifier
        return None

    def _type_edge(self, caller: str, name: str, line: int) -> None:
        resolved = self._resolve(name)
        self._edge(caller, resolved or name, line, resolved is not None)

    def _edge(self, caller: str, callee: str, line: int, resolved: bool) -> None:
        key = (caller, callee, line)
        if caller == callee or key in self.seen_relationships:
            return
        self.seen_relationships.add(key)
        self.call_relationships.append(
            CallRelationship(caller=caller, callee=callee, call_line=line, is_resolved=resolved)
        )


def analyze_rust_file(
    file_path: str,
    content: str,
    repo_path: str | None = None,
    impl_bases: list[tuple[str, str, int]] | None = None,
) -> tuple[list[Node], list[CallRelationship]]:
    analyzer = TreeSitterRustAnalyzer(file_path, content, repo_path)
    if impl_bases is not None:
        impl_bases.extend(analyzer.impl_bases)
    return analyzer.nodes, analyzer.call_relationships
