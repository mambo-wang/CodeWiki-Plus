"""Tree-sitter based Go source code analyzer.

Extracts structs, interfaces, functions, methods and their call relationships
from Go source files for the CodeWiki dependency graph.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import (
    GrammarUnavailableError,
    get_parser,
)
from codewiki.src.be.dependency_analyzer.analyzers.go_package import (
    default_import_names,
    go_package_ref,
    is_skipped_go_file,
    package_name_in_dir,
    resolve_repository_import,
)

logger = logging.getLogger(__name__)

# Go predeclared types. Standard-library names such as context.Context are
# deliberately absent: a project may declare its own Context/Reader/Handler.
GO_PRIMITIVE_TYPES: Set[str] = {
    "bool",
    "byte",
    "rune",
    "string",
    "error",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintptr",
    "float32",
    "float64",
    "complex64",
    "complex128",
    "any",
    "comparable",
}


GO_BUILTIN_FUNCS: Set[str] = {
    "append",
    "cap",
    "clear",
    "close",
    "complex",
    "copy",
    "delete",
    "imag",
    "len",
    "make",
    "max",
    "min",
    "new",
    "panic",
    "print",
    "println",
    "real",
    "recover",
}


class TreeSitterGoAnalyzer:
    """Analyze a single Go source file using Tree-sitter."""

    def __init__(self, file_path: str, content: str, repo_path: Optional[str] = None):
        self.file_path = Path(file_path)
        self.content = content
        self.repo_path = repo_path or ""
        self.nodes: List[Node] = []
        self.call_relationships: List[CallRelationship] = []
        self._package_name: Optional[str] = None
        self.relative_path = Path(self._get_relative_path()).as_posix()
        self.visible_dirs: Set[str] = set()
        self.imports: dict[str, str | None] = {}
        self._seen_relationships: Set[tuple[str, str, int | None]] = set()
        if is_skipped_go_file(self.relative_path):
            return
        self._analyze()

    def _get_relative_path(self) -> str:
        if self.repo_path:
            try:
                # BUG-21: normalize symlinks before computing relative paths.
                real_file = os.path.realpath(str(self.file_path))
                real_repo = os.path.realpath(self.repo_path)
                return os.path.relpath(real_file, real_repo).replace(os.sep, "/")
            except ValueError:
                return str(self.file_path).replace(os.sep, "/")
        return str(self.file_path).replace(os.sep, "/")

    def _get_component_id(self, name: str, receiver: Optional[str] = None) -> str:
        rel_path = self._get_relative_path()
        if receiver:
            return f"{rel_path}::{receiver}.{name}"
        return f"{rel_path}::{name}"

    def _analyze(self):
        try:
            # 独立 parser 避免跨线程共享；grammar 缺失/ABI 不兼容必须显式失败。
            tree = get_parser("go").parse(bytes(self.content, "utf8"))
            root = tree.root_node
            lines = self.content.splitlines()
            self._extract_package_name(root)
            self._collect_imports(root)
            top_level_names: dict = {}
            self._extract_nodes(root, top_level_names, lines)
            self._extract_relationships(root, top_level_names)
        except GrammarUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Error parsing Go file {self.file_path}: {e}")

    def _collect_imports(self, root):
        """Collect file aliases and the repository packages visible to this file."""
        self.visible_dirs = {self._package_directory()}
        for child in root.children:
            if child.type != "import_declaration":
                continue
            stack = [child]
            while stack:
                current = stack.pop()
                if current.type == "import_spec":
                    self._register_import(current)
                stack.extend(reversed(current.children))

    def _package_directory(self) -> str:
        return os.path.dirname(self.relative_path).replace(os.sep, "/")

    def _register_import(self, spec):
        path_node = spec.child_by_field_name("path")
        if path_node is None:
            return
        import_path = path_node.text.decode().strip('"`')
        alias_node = spec.child_by_field_name("name")
        alias = alias_node.text.decode() if alias_node is not None else None
        if alias in ("_", "."):
            return
        repo_dir = resolve_repository_import(import_path, self._package_directory(), self.repo_path)
        if repo_dir is not None:
            self.visible_dirs.add(repo_dir)
        if alias:
            names = {alias}
        else:
            names = default_import_names(import_path)
            if repo_dir is not None and self.repo_path:
                actual = package_name_in_dir(os.path.join(self.repo_path, repo_dir))
                if actual:
                    names = {actual}
        for name in names:
            # A repository package wins over an external package with the same alias.
            if name not in self.imports or self.imports[name] is None:
                self.imports[name] = repo_dir

    def _extract_package_name(self, root):
        for child in root.children:
            if child.type == "package_clause":
                for c in child.children:
                    if c.type == "package_identifier":
                        self._package_name = c.text.decode()
                        return

    def _extract_nodes(self, node, top_level_names: dict, lines):
        node_type = None
        node_name = None
        receiver_name = None

        if node.type == "type_declaration":
            for type_spec in node.children:
                if type_spec.type != "type_spec":
                    continue
                name_node = next(
                    (c for c in type_spec.children if c.type == "type_identifier"), None
                )
                type_body = next(
                    (c for c in type_spec.children if c.type in ("struct_type", "interface_type")),
                    None,
                )
                if not name_node or not type_body:
                    continue
                tname = name_node.text.decode()
                if type_body.type == "struct_type":
                    node_type = "struct"
                elif type_body.type == "interface_type":
                    node_type = "interface"
                node_name = tname

        elif node.type == "function_declaration":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                node_type = "function"
                node_name = name_node.text.decode()

        elif node.type == "method_declaration":
            method_name_node = next(
                (c for c in node.children if c.type == "field_identifier"), None
            )
            if method_name_node:
                recv = self._get_receiver_type(node)
                if recv:
                    receiver_name = recv
                node_type = "method"
                node_name = method_name_node.text.decode()

        if node_type and node_name:
            if receiver_name:
                component_id = self._get_component_id(node_name, receiver_name)
                display_name = f"{node_type} ({receiver_name}).{node_name}"
            else:
                component_id = self._get_component_id(node_name)
                display_name = f"{node_type} {node_name}"

            relative_path = self._get_relative_path()

            docstring = ""
            if node.prev_sibling and hasattr(node.prev_sibling, "type"):
                if node.prev_sibling.type == "comment":
                    docstring = node.prev_sibling.text.decode().strip()

            start_idx = node.start_point[0]
            end_idx = node.end_point[0] + 1
            code_snippet = "\n".join(lines[start_idx:end_idx]) if start_idx < len(lines) else ""
            params = self._extract_parameters(node)

            node_obj = Node(
                id=component_id,
                name=node_name,
                component_type=node_type,
                file_path=str(self.file_path),
                relative_path=relative_path,
                source_code=code_snippet,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                has_docstring=bool(docstring),
                docstring=docstring,
                parameters=params,
                node_type=node_type,
                base_classes=None,
                class_name=receiver_name,
                display_name=display_name,
                component_id=component_id,
                language="go",
                qualified_name=(
                    f"{self._package_name}.{receiver_name}.{node_name}"
                    if self._package_name and receiver_name
                    else f"{self._package_name}.{node_name}"
                    if self._package_name
                    else node_name
                ),
            )
            self.nodes.append(node_obj)
            top_level_names[node_name] = node_obj
            if receiver_name:
                top_level_names[f"{receiver_name}.{node_name}"] = node_obj
            elif node_type == "interface":
                self._extract_interface_methods(node, node_name, lines)

        for child in node.children:
            self._extract_nodes(child, top_level_names, lines)

    def _extract_interface_methods(self, type_declaration, interface_name: str, lines) -> None:
        """Record interface method signatures for implicit implementation links."""
        type_spec = next(
            (child for child in type_declaration.children if child.type == "type_spec"),
            None,
        )
        type_body = type_spec.child_by_field_name("type") if type_spec is not None else None
        if type_body is None or type_body.type != "interface_type":
            return
        for element in type_body.named_children:
            if element.type not in ("method_elem", "method_spec"):
                continue
            name_node = element.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = name_node.text.decode()
            component_id = self._get_component_id(method_name, interface_name)
            start_idx = element.start_point[0]
            end_idx = element.end_point[0] + 1
            self.nodes.append(
                Node(
                    id=component_id,
                    name=method_name,
                    component_type="method",
                    file_path=str(self.file_path),
                    relative_path=self.relative_path,
                    source_code="\n".join(lines[start_idx:end_idx]),
                    start_line=element.start_point[0] + 1,
                    end_line=element.end_point[0] + 1,
                    parameters=self._extract_parameters(element),
                    node_type="method",
                    class_name=interface_name,
                    display_name=f"method ({interface_name}).{method_name}",
                    component_id=component_id,
                    language="go",
                    qualified_name=(
                        f"{self._package_name}.{interface_name}.{method_name}"
                        if self._package_name
                        else f"{interface_name}.{method_name}"
                    ),
                )
            )

    def _add_relationship(
        self,
        caller: str,
        callee: str,
        call_line: int,
        *,
        resolved: bool = False,
    ) -> None:
        key = (caller, callee, call_line)
        if caller == callee or key in self._seen_relationships:
            return
        self._seen_relationships.add(key)
        self.call_relationships.append(
            CallRelationship(
                caller=caller,
                callee=callee,
                call_line=call_line,
                is_resolved=resolved,
            )
        )

    def _package_ref(self, name: str, package_dir: Optional[str] = None) -> str:
        return go_package_ref(
            self._package_directory() if package_dir is None else package_dir,
            name,
        )

    def _extract_relationships(self, node, top_level_names: dict):
        if node.type == "type_declaration":
            for type_spec in node.children:
                if type_spec.type != "type_spec":
                    continue
                name_node = next(
                    (c for c in type_spec.children if c.type == "type_identifier"), None
                )
                struct_body = next((c for c in type_spec.children if c.type == "struct_type"), None)
                if name_node and struct_body:
                    struct_name = name_node.text.decode()
                    self._extract_struct_dependencies(struct_body, struct_name, top_level_names)

                iface_body = next(
                    (c for c in type_spec.children if c.type == "interface_type"), None
                )
                if name_node and iface_body:
                    iface_name = name_node.text.decode()
                    self._extract_interface_dependencies(iface_body, iface_name, top_level_names)

        if node.type == "call_expression":
            caller_id = self._find_containing_function(node)
            if caller_id:
                self._extract_call_target(node, caller_id, top_level_names)

        if node.type == "composite_literal":
            caller_id = self._find_containing_function(node)
            if caller_id:
                type_node = next((c for c in node.children if c.type == "type_identifier"), None)
                if type_node:
                    type_name = type_node.text.decode()
                    if not self._is_primitive_type(type_name):
                        self._add_relationship(
                            caller_id,
                            self._package_ref(type_name),
                            node.start_point[0] + 1,
                        )

        for child in node.children:
            self._extract_relationships(child, top_level_names)

    def _extract_struct_dependencies(self, struct_body, struct_name: str, top_level_names: dict):
        field_list = next(
            (c for c in struct_body.children if c.type == "field_declaration_list"), None
        )
        if not field_list:
            return
        for field in field_list.children:
            if field.type != "field_declaration":
                continue
            children = [c for c in field.children if c.type not in ("{", "}", ",")]
            type_node = (
                children[0]
                if len(children) == 1
                else field.children[-1]
                if field.children
                else None
            )
            reference = self._resolve_type_reference(type_node)
            if not reference:
                continue
            field_type, package_dir = reference
            if self._is_primitive_type(field_type):
                continue
            self._add_relationship(
                self._get_component_id(struct_name),
                self._package_ref(field_type, package_dir),
                field.start_point[0] + 1,
            )

    def _extract_interface_dependencies(self, iface_body, iface_name: str, top_level_names: dict):
        for element in iface_body.named_children:
            if element.type != "type_elem":
                continue
            for type_node in element.named_children:
                reference = self._resolve_type_reference(type_node)
                if not reference:
                    continue
                embedded, package_dir = reference
                if self._is_primitive_type(embedded):
                    continue
                self._add_relationship(
                    self._get_component_id(iface_name),
                    self._package_ref(embedded, package_dir),
                    element.start_point[0] + 1,
                )

    def _extract_call_target(self, call_node, caller_id: str, top_level_names: dict):
        func_node = call_node.children[0] if call_node.children else None
        if func_node is None:
            return

        if func_node.type == "identifier":
            callee_name = func_node.text.decode()
            if callee_name in GO_BUILTIN_FUNCS or self._is_primitive_type(callee_name):
                return
            local_node = top_level_names.get(callee_name)
            if local_node and local_node.component_type == "function":
                self._add_relationship(
                    caller_id,
                    local_node.id,
                    call_node.start_point[0] + 1,
                    resolved=True,
                )
            else:
                self._add_relationship(
                    caller_id,
                    self._package_ref(callee_name),
                    call_node.start_point[0] + 1,
                )

        elif func_node.type == "selector_expression":
            operand = next(
                (
                    c
                    for c in func_node.children
                    if c.type
                    in (
                        "identifier",
                        "selector_expression",
                        "call_expression",
                        "parenthesized_expression",
                    )
                ),
                None,
            )
            field = next((c for c in func_node.children if c.type == "field_identifier"), None)
            if operand and field:
                method_name = field.text.decode()
                operand_name = operand.text.decode()
                if operand_name in self.imports:
                    repo_dir = self.imports[operand_name]
                    if repo_dir is not None:
                        self._add_relationship(
                            caller_id,
                            self._package_ref(method_name, repo_dir),
                            call_node.start_point[0] + 1,
                        )
                    return
                if operand_name in top_level_names:
                    target_type = operand_name
                else:
                    target_type = self._find_variable_type(call_node, operand_name, top_level_names)
                if target_type and not self._is_primitive_type(target_type):
                    local_method = top_level_names.get(f"{target_type}.{method_name}")
                    self._add_relationship(
                        caller_id,
                        local_method.id
                        if local_method
                        else self._package_ref(f"{target_type}.{method_name}"),
                        call_node.start_point[0] + 1,
                        resolved=local_method is not None,
                    )
                else:
                    self._add_relationship(
                        caller_id,
                        method_name,
                        call_node.start_point[0] + 1,
                    )

    def _get_receiver_type(self, method_node) -> Optional[str]:
        param_list = next((c for c in method_node.children if c.type == "parameter_list"), None)
        if not param_list:
            return None
        for param in param_list.children:
            if param.type == "parameter_declaration":
                type_node = param.children[-1] if param.children else None
                if type_node:
                    return self._resolve_type_name(type_node)
        return None

    def _resolve_type_reference(self, node) -> Optional[Tuple[str, Optional[str]]]:
        """Return ``(type name, repository package directory)`` for a type node.

        A missing package directory means the type is local to the current
        package. Qualified types from external packages deliberately return
        ``None`` so they cannot bind to a same-named project type.
        """
        if node is None:
            return None
        if node.type == "type_identifier":
            return node.text.decode(), None
        if node.type == "qualified_type":
            type_id = next((c for c in node.children if c.type == "type_identifier"), None)
            package_node = node.child_by_field_name("package")
            if type_id is None or package_node is None:
                return None
            package = package_node.text.decode()
            repo_dir = self.imports.get(package)
            if repo_dir is None:
                return None
            return type_id.text.decode(), repo_dir
        if node.type in (
            "pointer_type",
            "parenthesized_expression",
            "variadic_parameter_declaration",
        ):
            inner = next(
                (
                    c
                    for c in node.named_children
                    if c.type
                    in (
                        "type_identifier",
                        "qualified_type",
                        "pointer_type",
                        "slice_type",
                        "array_type",
                        "map_type",
                        "channel_type",
                    )
                ),
                None,
            )
            return self._resolve_type_reference(inner) if inner else None
        if node.type == "slice_type":
            inner = next(
                (
                    c
                    for c in node.named_children
                    if c.type in ("type_identifier", "pointer_type", "qualified_type")
                ),
                None,
            )
            return self._resolve_type_reference(inner) if inner else None
        if node.type == "array_type":
            inner = next(
                (c for c in node.named_children if c.type in ("type_identifier", "pointer_type")),
                None,
            )
            return self._resolve_type_reference(inner) if inner else None
        if node.type == "map_type":
            children = [
                c
                for c in node.named_children
                if c.type in ("type_identifier", "pointer_type", "slice_type", "qualified_type")
            ]
            if len(children) >= 2:
                return self._resolve_type_reference(children[1])
            if len(children) == 1:
                return self._resolve_type_reference(children[0])
        if node.type == "channel_type":
            inner = next(
                (c for c in node.named_children if c.type in ("type_identifier", "pointer_type")),
                None,
            )
            return self._resolve_type_reference(inner) if inner else None
        return None

    def _resolve_type_name(self, node) -> Optional[str]:
        reference = self._resolve_type_reference(node)
        if reference is None or reference[1] is not None:
            return None
        return reference[0]

    def _extract_parameters(self, node) -> Optional[List[str]]:
        params = []
        param_list = None
        if node.type == "function_declaration":
            param_list = next((c for c in node.children if c.type == "parameter_list"), None)
        elif node.type == "method_declaration":
            lists = [c for c in node.children if c.type == "parameter_list"]
            if len(lists) >= 2:
                param_list = lists[1]
            elif len(lists) == 1:
                param_list = lists[0]
        elif node.type in ("method_elem", "method_spec"):
            param_list = next((c for c in node.children if c.type == "parameter_list"), None)

        if not param_list:
            return None

        for param in param_list.children:
            if param.type == "parameter_declaration":
                names = [c.text.decode() for c in param.children if c.type == "identifier"]
                type_node = param.children[-1] if param.children else None
                type_str = type_node.text.decode() if type_node else "unknown"
                if names:
                    for n in names:
                        params.append(f"{n} {type_str}" if type_str else n)
                elif type_str:
                    params.append(type_str)
        return params if params else None

    def _find_containing_function(self, node) -> Optional[str]:
        current = node.parent
        while current:
            if current.type == "function_declaration":
                name_node = next((c for c in current.children if c.type == "identifier"), None)
                if name_node:
                    return self._get_component_id(name_node.text.decode())
            elif current.type == "method_declaration":
                method_name_node = next(
                    (c for c in current.children if c.type == "field_identifier"), None
                )
                if method_name_node:
                    recv = self._get_receiver_type(current)
                    return self._get_component_id(method_name_node.text.decode(), recv)
            current = current.parent
        return None

    def _find_variable_type(self, node, variable_name: str, top_level_names: dict) -> Optional[str]:
        func_node = node.parent
        while func_node and func_node.type not in (
            "function_declaration",
            "method_declaration",
        ):
            func_node = func_node.parent

        if func_node:
            if func_node.type == "method_declaration":
                param_lists = [c for c in func_node.children if c.type == "parameter_list"]
                if param_lists:
                    recv_list = param_lists[0]
                    for param in recv_list.children:
                        if param.type == "parameter_declaration":
                            names = [c for c in param.children if c.type == "identifier"]
                            for n in names:
                                if n.text.decode() == variable_name:
                                    type_node = param.children[-1]
                                    t = self._resolve_type_name(type_node)
                                    if t:
                                        return t
                if len(param_lists) >= 2:
                    for param in param_lists[1].children:
                        if param.type == "parameter_declaration":
                            names = [c for c in param.children if c.type == "identifier"]
                            for n in names:
                                if n.text.decode() == variable_name:
                                    type_node = param.children[-1]
                                    t = self._resolve_type_name(type_node)
                                    if t:
                                        return t
            elif func_node.type == "function_declaration":
                param_list = next(
                    (c for c in func_node.children if c.type == "parameter_list"), None
                )
                if param_list:
                    for param in param_list.children:
                        if param.type == "parameter_declaration":
                            names = [c for c in param.children if c.type == "identifier"]
                            for n in names:
                                if n.text.decode() == variable_name:
                                    type_node = param.children[-1]
                                    t = self._resolve_type_name(type_node)
                                    if t:
                                        return t

            body = next((c for c in func_node.children if c.type == "block"), None)
            if body:
                resolved = self._search_short_var_decl(body, variable_name)
                if resolved:
                    return resolved

        return None

    def _search_short_var_decl(self, block_node, variable_name: str) -> Optional[str]:
        for child in block_node.children:
            if child.type == "short_var_declaration":
                lhs = next((c for c in child.children if c.type == "expression_list"), None)
                rhs_nodes = [c for c in child.children if c.type == "expression_list"]
                rhs = rhs_nodes[1] if len(rhs_nodes) >= 2 else None

                if lhs and rhs:
                    names = [c for c in lhs.children if c.type == "identifier"]
                    calls = [
                        c
                        for c in rhs.children
                        if c.type in ("call_expression", "composite_literal")
                    ]
                    for i, name_node in enumerate(names):
                        if name_node.text.decode() == variable_name:
                            if i < len(calls):
                                call = calls[i]
                                if call.type == "call_expression":
                                    func = call.children[0] if call.children else None
                                    if func and func.type == "identifier":
                                        t = func.text.decode()
                                        if t[0:1].isupper() and not self._is_primitive_type(t):
                                            return t
                                elif call.type == "composite_literal":
                                    t_node = next(
                                        (c for c in call.children if c.type == "type_identifier"),
                                        None,
                                    )
                                    if t_node:
                                        return t_node.text.decode()
                            unary_list = [c for c in rhs.children if c.type == "unary_expression"]
                            if i < len(unary_list):
                                unary = unary_list[i]
                                inner = next(
                                    (c for c in unary.children if c.type == "composite_literal"),
                                    None,
                                )
                                if inner:
                                    t_node = next(
                                        (c for c in inner.children if c.type == "type_identifier"),
                                        None,
                                    )
                                    if t_node:
                                        return t_node.text.decode()

            elif child.type == "block":
                result = self._search_short_var_decl(child, variable_name)
                if result:
                    return result
            elif child.type in ("if_statement", "for_statement", "expression_switch_statement"):
                for sub in child.children:
                    if sub.type == "block":
                        result = self._search_short_var_decl(sub, variable_name)
                        if result:
                            return result

        return None

    @staticmethod
    def _is_primitive_type(type_name: str) -> bool:
        return type_name in GO_PRIMITIVE_TYPES

    @staticmethod
    def _is_stdlib_package(name: str) -> bool:
        stdlib = {
            "fmt",
            "log",
            "os",
            "io",
            "net",
            "http",
            "json",
            "xml",
            "strings",
            "strconv",
            "math",
            "time",
            "context",
            "errors",
            "sync",
            "path",
            "filepath",
            "regexp",
            "sort",
            "bytes",
            "bufio",
            "encoding",
            "reflect",
            "runtime",
            "testing",
            "crypto",
            "database",
            "sql",
            "html",
            "text",
            "flag",
            "exec",
            "signal",
            "syscall",
            "unsafe",
            "atomic",
            "rand",
            "hash",
            "compress",
            "archive",
            "container",
        }
        return name in stdlib


def analyze_go_file(
    file_path: str, content: str, repo_path: Optional[str] = None
) -> Tuple[List[Node], List[CallRelationship]]:
    """Entry point for the Go analyzer."""
    analyzer = TreeSitterGoAnalyzer(file_path, content, repo_path)
    return analyzer.nodes, analyzer.call_relationships
