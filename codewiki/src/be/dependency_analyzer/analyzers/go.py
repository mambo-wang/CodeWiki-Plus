"""Tree-sitter based Go source code analyzer.

Extracts structs, interfaces, functions, methods and their call relationships
from Go source files for the CodeWiki dependency graph.
"""

import logging
from typing import List, Optional, Tuple, Set
from pathlib import Path
import os

from tree_sitter import Parser, Language
import tree_sitter_go
from codewiki.src.be.dependency_analyzer.models.core import Node, CallRelationship

logger = logging.getLogger(__name__)

# Go built-in types and common standard-library types to filter out
GO_PRIMITIVE_TYPES: Set[str] = {
    "bool", "byte", "rune", "string", "error",
    "int", "int8", "int16", "int32", "int64",
    "uint", "uint8", "uint16", "uint32", "uint64", "uintptr",
    "float32", "float64", "complex64", "complex128",
    "any", "comparable",
    "Context", "Writer", "Reader", "Handler", "Request", "Response",
    "Mutex", "RWMutex", "WaitGroup", "Once", "Pool",
    "Buffer", "StringsBuilder",
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
        self._analyze()

    def _get_relative_path(self) -> str:
        if self.repo_path:
            try:
                return os.path.relpath(str(self.file_path), self.repo_path)
            except ValueError:
                return str(self.file_path)
        return str(self.file_path)

    def _get_component_id(self, name: str, receiver: Optional[str] = None) -> str:
        rel_path = self._get_relative_path()
        if receiver:
            return f"{rel_path}::{receiver}.{name}"
        return f"{rel_path}::{name}"

    def _analyze(self):
        try:
            language_capsule = tree_sitter_go.language()
            go_language = Language(language_capsule)
            parser = Parser(go_language)
            tree = parser.parse(bytes(self.content, "utf8"))
            root = tree.root_node
            lines = self.content.splitlines()
            self._extract_package_name(root)
            top_level_names: dict = {}
            self._extract_nodes(root, top_level_names, lines)
            self._extract_relationships(root, top_level_names)
        except Exception as e:
            logger.error(f"Error parsing Go file {self.file_path}: {e}")

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
                    (c for c in type_spec.children
                     if c.type in ("struct_type", "interface_type")),
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
            name_node = next(
                (c for c in node.children if c.type == "identifier"), None
            )
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
            )
            self.nodes.append(node_obj)
            top_level_names[node_name] = node_obj
            if receiver_name:
                top_level_names[f"{receiver_name}.{node_name}"] = node_obj

        for child in node.children:
            self._extract_nodes(child, top_level_names, lines)

    def _extract_relationships(self, node, top_level_names: dict):
        if node.type == "type_declaration":
            for type_spec in node.children:
                if type_spec.type != "type_spec":
                    continue
                name_node = next(
                    (c for c in type_spec.children if c.type == "type_identifier"), None
                )
                struct_body = next(
                    (c for c in type_spec.children if c.type == "struct_type"), None
                )
                if name_node and struct_body:
                    struct_name = name_node.text.decode()
                    self._extract_struct_dependencies(
                        struct_body, struct_name, top_level_names
                    )

                iface_body = next(
                    (c for c in type_spec.children if c.type == "interface_type"), None
                )
                if name_node and iface_body:
                    iface_name = name_node.text.decode()
                    self._extract_interface_dependencies(
                        iface_body, iface_name, top_level_names
                    )

        if node.type == "call_expression":
            caller_id = self._find_containing_function(node)
            if caller_id:
                self._extract_call_target(node, caller_id, top_level_names)

        if node.type == "composite_literal":
            caller_id = self._find_containing_function(node)
            if caller_id:
                type_node = next(
                    (c for c in node.children if c.type == "type_identifier"), None
                )
                if type_node:
                    type_name = type_node.text.decode()
                    if not self._is_primitive_type(type_name):
                        self.call_relationships.append(CallRelationship(
                            caller=caller_id,
                            callee=self._get_component_id(type_name),
                            call_line=node.start_point[0] + 1,
                            is_resolved=False,
                        ))

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
            if len(children) == 1:
                embedded_type = self._resolve_type_name(children[0])
                if embedded_type and not self._is_primitive_type(embedded_type):
                    self.call_relationships.append(CallRelationship(
                        caller=self._get_component_id(struct_name),
                        callee=self._get_component_id(embedded_type),
                        call_line=field.start_point[0] + 1,
                        is_resolved=False,
                    ))
            else:
                type_node = field.children[-1] if field.children else None
                if type_node:
                    field_type = self._resolve_type_name(type_node)
                    if field_type and not self._is_primitive_type(field_type):
                        self.call_relationships.append(CallRelationship(
                            caller=self._get_component_id(struct_name),
                            callee=self._get_component_id(field_type),
                            call_line=field.start_point[0] + 1,
                            is_resolved=False,
                        ))

    def _extract_interface_dependencies(self, iface_body, iface_name: str, top_level_names: dict):
        method_list = next(
            (c for c in iface_body.children if c.type == "method_spec_list"), None
        )
        if not method_list:
            return
        for spec in method_list.children:
            if spec.type == "type_identifier":
                embedded = spec.text.decode()
                if not self._is_primitive_type(embedded):
                    self.call_relationships.append(CallRelationship(
                        caller=self._get_component_id(iface_name),
                        callee=self._get_component_id(embedded),
                        call_line=spec.start_point[0] + 1,
                        is_resolved=False,
                    ))

    def _extract_call_target(self, call_node, caller_id: str, top_level_names: dict):
        func_node = call_node.children[0] if call_node.children else None
        if func_node is None:
            return

        if func_node.type == "identifier":
            callee_name = func_node.text.decode()
            if not self._is_primitive_type(callee_name):
                self.call_relationships.append(CallRelationship(
                    caller=caller_id,
                    callee=self._get_component_id(callee_name),
                    call_line=call_node.start_point[0] + 1,
                    is_resolved=False,
                ))

        elif func_node.type == "selector_expression":
            operand = next(
                (c for c in func_node.children if c.type in ("identifier", "selector_expression", "call_expression", "parenthesized_expression")),
                None,
            )
            field = next(
                (c for c in func_node.children if c.type == "field_identifier"), None
            )
            if operand and field:
                method_name = field.text.decode()
                operand_name = operand.text.decode()
                if self._is_stdlib_package(operand_name):
                    return
                if operand_name in top_level_names:
                    target_type = operand_name
                else:
                    target_type = self._find_variable_type(
                        call_node, operand_name, top_level_names
                    )
                if target_type and not self._is_primitive_type(target_type):
                    self.call_relationships.append(CallRelationship(
                        caller=caller_id,
                        callee=self._get_component_id(method_name, target_type),
                        call_line=call_node.start_point[0] + 1,
                        is_resolved=False,
                    ))
                else:
                    self.call_relationships.append(CallRelationship(
                        caller=caller_id,
                        callee=method_name,
                        call_line=call_node.start_point[0] + 1,
                        is_resolved=False,
                    ))

    def _get_receiver_type(self, method_node) -> Optional[str]:
        param_list = next(
            (c for c in method_node.children if c.type == "parameter_list"), None
        )
        if not param_list:
            return None
        for param in param_list.children:
            if param.type == "parameter_declaration":
                type_node = param.children[-1] if param.children else None
                if type_node:
                    return self._resolve_type_name(type_node)
        return None

    def _resolve_type_name(self, node) -> Optional[str]:
        if node.type == "type_identifier":
            return node.text.decode()
        elif node.type == "pointer_type":
            inner = next((c for c in node.children if c.type in ("type_identifier", "qualified_type", "pointer_type")), None)
            if inner:
                return self._resolve_type_name(inner)
        elif node.type == "slice_type":
            inner = next((c for c in node.children if c.type in ("type_identifier", "pointer_type", "qualified_type")), None)
            if inner:
                return self._resolve_type_name(inner)
        elif node.type == "array_type":
            inner = next((c for c in node.children if c.type in ("type_identifier", "pointer_type")), None)
            if inner:
                return self._resolve_type_name(inner)
        elif node.type == "map_type":
            children = [c for c in node.children if c.type in ("type_identifier", "pointer_type", "slice_type", "qualified_type")]
            if len(children) >= 2:
                return self._resolve_type_name(children[1])
            elif len(children) == 1:
                return self._resolve_type_name(children[0])
        elif node.type == "channel_type":
            inner = next((c for c in node.children if c.type in ("type_identifier", "pointer_type")), None)
            if inner:
                return self._resolve_type_name(inner)
        elif node.type == "qualified_type":
            type_id = next((c for c in node.children if c.type == "type_identifier"), None)
            return type_id.text.decode() if type_id else None
        elif node.type == "identifier":
            return node.text.decode()
        return None

    def _extract_parameters(self, node) -> Optional[List[str]]:
        params = []
        param_list = None
        if node.type == "function_declaration":
            param_list = next(
                (c for c in node.children if c.type == "parameter_list"), None
            )
        elif node.type == "method_declaration":
            lists = [c for c in node.children if c.type == "parameter_list"]
            if len(lists) >= 2:
                param_list = lists[1]
            elif len(lists) == 1:
                param_list = lists[0]

        if not param_list:
            return None

        for param in param_list.children:
            if param.type == "parameter_declaration":
                names = [
                    c.text.decode()
                    for c in param.children
                    if c.type == "identifier"
                ]
                type_node = param.children[-1] if param.children else None
                type_str = self._resolve_type_name(type_node) if type_node else "unknown"
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
                name_node = next(
                    (c for c in current.children if c.type == "identifier"), None
                )
                if name_node:
                    return self._get_component_id(name_node.text.decode())
            elif current.type == "method_declaration":
                method_name_node = next(
                    (c for c in current.children if c.type == "field_identifier"), None
                )
                if method_name_node:
                    recv = self._get_receiver_type(current)
                    return self._get_component_id(
                        method_name_node.text.decode(), recv
                    )
            current = current.parent
        return None

    def _find_variable_type(
        self, node, variable_name: str, top_level_names: dict
    ) -> Optional[str]:
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
                lhs = next(
                    (c for c in child.children if c.type == "expression_list"), None
                )
                rhs_nodes = [
                    c for c in child.children if c.type == "expression_list"
                ]
                rhs = rhs_nodes[1] if len(rhs_nodes) >= 2 else None

                if lhs and rhs:
                    names = [c for c in lhs.children if c.type == "identifier"]
                    calls = [c for c in rhs.children if c.type in ("call_expression", "composite_literal")]
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
            "fmt", "log", "os", "io", "net", "http", "json", "xml",
            "strings", "strconv", "math", "time", "context", "errors",
            "sync", "path", "filepath", "regexp", "sort", "bytes",
            "bufio", "encoding", "reflect", "runtime", "testing",
            "crypto", "database", "sql", "html", "text", "flag",
            "exec", "signal", "syscall", "unsafe", "atomic",
            "rand", "hash", "compress", "archive", "container",
        }
        return name in stdlib


def analyze_go_file(
    file_path: str, content: str, repo_path: Optional[str] = None
) -> Tuple[List[Node], List[CallRelationship]]:
    """Entry point for the Go analyzer."""
    analyzer = TreeSitterGoAnalyzer(file_path, content, repo_path)
    return analyzer.nodes, analyzer.call_relationships
