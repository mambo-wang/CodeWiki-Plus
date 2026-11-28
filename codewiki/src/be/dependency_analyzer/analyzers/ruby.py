"""Ruby 的保守 tree-sitter 适配。

组件身份使用 ``Namespace::Type#instance_method`` 与
``Namespace::Type.singleton_method``，避免同名类和单例方法互相覆盖。接收者只按
调用点之前、同一词法执行路径上的 ``Const.new`` 赋值推断；条件分支和未知赋值
不会被当成确定类型。动态派发与属性宏不凭空生成组件或调用边。
"""

import logging
import os
from typing import Any

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import (
    GrammarUnavailableError,
    get_parser,
)

logger = logging.getLogger(__name__)

MAX_RECURSION_DEPTH = 100
_MIXIN_METHODS = frozenset({"include", "extend", "prepend"})
RUBY_IMPLICIT_PREFIX = "ruby:implicit:"


class TreeSitterRubyAnalyzer:
    def __init__(
        self,
        file_path: str,
        content: str,
        repo_path: str | None = None,
        *,
        defer_implicit: bool = False,
    ):
        self.file_path = file_path
        self.content = content
        self.repo_path = repo_path or ""
        self.defer_implicit = defer_implicit
        self.relative_path = self._relative_path()
        self.nodes: list[Node] = []
        self.call_relationships: list[CallRelationship] = []
        self.symbols: dict[str, Node] = {}
        self.seen_relationships: set[tuple[str, str, int | None]] = set()
        self._analyze()

    def _relative_path(self) -> str:
        if not self.repo_path:
            return str(self.file_path)
        try:
            return os.path.relpath(str(self.file_path), self.repo_path).replace(os.sep, "/")
        except ValueError:
            return str(self.file_path)

    def _component_id(self, logical_name: str) -> str:
        return f"{self.relative_path}::{logical_name}"

    def _analyze(self) -> None:
        try:
            tree = get_parser("ruby").parse(self.content.encode("utf-8"))
            lines = self.content.splitlines()
            self._extract_nodes(tree.root_node, (), lines, False, 0)
            self._extract_relationships(tree.root_node, None, (), False, 0)
        except GrammarUnavailableError:
            raise
        except RecursionError:
            logger.error("Ruby 语法树递归上限：%s", self.file_path)
        except Exception as exc:  # noqa: BLE001 - 单文件坏语法不能中止仓库扫描
            logger.error("Ruby 文件分析失败 %s：%s", self.file_path, exc)

    # ------------------------------------------------------------------
    # Pass 1: components
    # ------------------------------------------------------------------

    def _extract_nodes(
        self, node: Any, scope: tuple[str, ...], lines: list[str], singleton: bool, depth: int
    ) -> None:
        if depth > MAX_RECURSION_DEPTH:
            return
        if node.type in ("class", "module"):
            name_node = node.child_by_field_name("name")
            qualified = self._qualified_constant(name_node, scope)
            if not qualified:
                return
            logical = qualified.lstrip(":")
            existing = self.symbols.get(logical)
            if existing is None:
                base_classes = [base.lstrip(":") for base in self._base_classes(node, scope)]
                existing = self._add_node(
                    node,
                    logical,
                    node.type,
                    lines,
                    base_classes=base_classes,
                    qualified_name=logical.replace(".", "::"),
                )
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    self._extract_nodes(child, tuple(logical.split(".")), lines, False, depth + 1)
            return

        if node.type == "singleton_class":
            owner = self._singleton_owner(node, scope)
            if owner is None:
                return
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    self._extract_nodes(
                        child,
                        tuple(owner.lstrip(":").split(".")),
                        lines,
                        True,
                        depth + 1,
                    )
            return

        if node.type == "method":
            name = self._text(node.child_by_field_name("name"))
            if name:
                self._add_method(node, name, scope, lines, singleton)
            return

        if node.type == "singleton_method":
            name = self._text(node.child_by_field_name("name"))
            obj = node.child_by_field_name("object")
            if not name:
                return
            if obj is not None and obj.type == "self":
                owner = ".".join(scope)
            elif obj is not None and obj.type in ("constant", "scope_resolution"):
                owner = self._resolve_constant(self._constant_text(obj) or "", scope)
            else:
                return
            owner_scope = tuple(owner.split(".")) if owner else ()
            self._add_method(node, name, owner_scope, lines, True)
            return

        for child in node.named_children:
            self._extract_nodes(child, scope, lines, singleton, depth + 1)

    def _add_method(
        self,
        node: Any,
        name: str,
        scope: tuple[str, ...],
        lines: list[str],
        singleton: bool,
    ) -> None:
        owner = ".".join(scope)
        logical = self._method_logical(owner, name, singleton)
        qualified = (
            f"{owner.replace('.', '::')}{'.' if singleton else '#'}{name}"
            if owner
            else f"{'.' if singleton else '#'}{name}"
        )
        self._add_node(
            node,
            logical,
            "method",
            lines,
            parameters=self._method_parameters(node),
            class_name=owner or None,
            qualified_name=qualified if owner else name,
        )
        # Nested `def` is dynamic in Ruby; do not recursively invent static owners.

    @staticmethod
    def _method_logical(owner: str, name: str, singleton: bool) -> str:
        marker = "." if singleton else "#"
        return f"{owner}{marker}{name}" if owner else f"{marker}{name}"

    def _add_node(
        self,
        node: Any,
        logical: str,
        component_type: str,
        lines: list[str],
        *,
        parameters: list[str] | None = None,
        base_classes: list[str] | None = None,
        class_name: str | None = None,
        qualified_name: str | None = None,
    ) -> Node:
        existing = self.symbols.get(logical)
        if existing is not None:
            return existing
        component_id = self._component_id(logical)
        docstring = self._docstring(node)
        start = node.start_point[0]
        end = node.end_point[0] + 1
        result = Node(
            id=component_id,
            name=logical,
            component_type=component_type,
            file_path=str(self.file_path),
            relative_path=self.relative_path,
            source_code="\n".join(lines[start:end]),
            start_line=start + 1,
            end_line=node.end_point[0] + 1,
            has_docstring=bool(docstring),
            docstring=docstring,
            parameters=parameters,
            node_type=component_type,
            base_classes=base_classes,
            class_name=class_name,
            display_name=f"{component_type} {logical}",
            component_id=component_id,
            language="ruby",
            qualified_name=qualified_name or logical,
        )
        self.nodes.append(result)
        self.symbols[logical] = result
        return result

    def _docstring(self, node: Any) -> str:
        comments: list[str] = []
        sibling = node.prev_sibling
        while sibling is not None and sibling.type == "comment":
            comments.append(self._text(sibling) or "")
            sibling = sibling.prev_sibling
        return "\n".join(reversed(comments))

    def _method_parameters(self, node: Any) -> list[str] | None:
        params = node.child_by_field_name("parameters")
        if params is None:
            return None
        accepted = {
            "identifier",
            "optional_parameter",
            "keyword_parameter",
            "splat_parameter",
            "hash_splat_parameter",
            "block_parameter",
        }
        values = [self._text(child) for child in params.named_children if child.type in accepted]
        return [value for value in values if value] or None

    # ------------------------------------------------------------------
    # Pass 2: relationships
    # ------------------------------------------------------------------

    def _extract_relationships(
        self, node: Any, caller: str | None, scope: tuple[str, ...], singleton: bool, depth: int
    ) -> None:
        if depth > MAX_RECURSION_DEPTH:
            return
        if node.type in ("class", "module"):
            qualified = self._qualified_constant(node.child_by_field_name("name"), scope)
            if not qualified:
                return
            class_id = self._component_id(qualified.lstrip(":"))
            for base in self._base_classes(node, scope):
                self._add_relationship(
                    caller=class_id, callee=base, call_line=node.start_point[0] + 1
                )
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    self._extract_relationships(
                        child, class_id, tuple(qualified.lstrip(":").split(".")), False, depth + 1
                    )
            return

        if node.type == "singleton_class":
            owner = self._singleton_owner(node, scope)
            if owner is None:
                return
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    self._extract_relationships(
                        child,
                        caller
                        if owner == ".".join(scope)
                        else self._component_id(owner.lstrip(":")),
                        tuple(owner.lstrip(":").split(".")),
                        True,
                        depth + 1,
                    )
            return

        if node.type in ("method", "singleton_method"):
            method_singleton = singleton or node.type == "singleton_method"
            method_id = self._method_id(node, scope, method_singleton)
            if method_id is None:
                return
            body = node.child_by_field_name("body")
            if body is not None:
                self._extract_relationships(body, method_id, scope, method_singleton, depth + 1)
            return

        if node.type == "call":
            self._extract_call(node, caller, scope, singleton)
            method_node = node.child_by_field_name("method")
            for child in node.named_children:
                if method_node is None or not (
                    child.start_byte == method_node.start_byte
                    and child.end_byte == method_node.end_byte
                ):
                    self._extract_relationships(child, caller, scope, singleton, depth + 1)
            return

        if node.type in ("assignment", "multiple_assignment", "operator_assignment"):
            right = node.child_by_field_name("right")
            if right is not None:
                self._extract_relationships(right, caller, scope, singleton, depth + 1)
            return

        if node.type == "identifier" and caller is not None:
            name = self._text(node)
            if name and not self._is_local_reference(node, name, scope):
                target = self._implicit_target(caller, scope, singleton, name)
                if target is None and self.defer_implicit:
                    current_singleton = singleton or self._is_type_component(caller)
                    target = f"{RUBY_IMPLICIT_PREFIX}{'.' if current_singleton else '#'}{name}"
                if target is not None:
                    self._add_relationship(caller, target, node.start_point[0] + 1)

        for child in node.named_children:
            self._extract_relationships(child, caller, scope, singleton, depth + 1)

    def _method_id(self, node: Any, scope: tuple[str, ...], singleton: bool) -> str | None:
        name = self._text(node.child_by_field_name("name"))
        if not name:
            return None
        owner = ".".join(scope)
        if node.type == "singleton_method":
            obj = node.child_by_field_name("object")
            if obj is not None and obj.type == "self":
                owner = ".".join(scope)
            elif obj is not None and obj.type in ("constant", "scope_resolution"):
                owner = self._resolve_constant(self._constant_text(obj) or "", scope)
            else:
                return None
            singleton = True
        logical = self._method_logical(owner, name, singleton)
        return self._component_id(logical)

    def _extract_call(
        self, node: Any, caller: str | None, scope: tuple[str, ...], singleton: bool
    ) -> None:
        if caller is None:
            return
        method_node = node.child_by_field_name("method")
        receiver = node.child_by_field_name("receiver")
        if method_node is None:
            method_node = next(
                (child for child in node.named_children if child.type == "identifier"), None
            )
            receiver = None
        method = self._text(method_node)
        if not method:
            return
        line = node.start_point[0] + 1
        current_singleton = singleton or self._is_type_component(caller)

        if receiver is None and method in _MIXIN_METHODS:
            for argument in self._call_arguments(node):
                constant = self._constant_text(argument)
                if constant:
                    self._add_relationship(caller, self._resolve_constant(constant, scope), line)
            return
        if receiver is None and method == "require_relative":
            target = self._string_argument(node)
            if target:
                self._add_relationship(caller, f"require_relative:{target}", line)
            return
        if receiver is None or receiver.type == "self":
            target = self._implicit_target(caller, scope, current_singleton, method)
            if target is None and self.defer_implicit:
                target = f"{RUBY_IMPLICIT_PREFIX}{'.' if current_singleton else '#'}{method}"
            self._add_relationship(caller, target or method, line)
            return
        if receiver.type in ("constant", "scope_resolution"):
            owner = self._resolve_constant(self._constant_text(receiver) or "", scope)
            self._add_relationship(caller, owner if method == "new" else f"{owner}.{method}", line)
            return
        if receiver.type == "identifier":
            name = self._text(receiver)
            bound, receiver_owner = self._binding_before(node, name or "", scope)
            if bound and receiver_owner:
                self._add_relationship(caller, f"{receiver_owner}#{method}", line)
            elif not bound:
                self._add_relationship(caller, f"{name}.{method}", line)
            return
        if receiver.type == "call":
            receiver_owner = self._constructor_class(receiver, scope)
            if receiver_owner:
                self._add_relationship(caller, f"{receiver_owner}#{method}", line)

    def _implicit_target(
        self, caller: str, scope: tuple[str, ...], singleton: bool, name: str
    ) -> str | None:
        owner = ".".join(scope)
        if owner:
            candidate = f"{owner}{'.' if singleton else '#'}{name}"
            if candidate in self.symbols:
                return candidate
        candidate = f"{'.' if singleton else '#'}{name}"
        return candidate if candidate in self.symbols else None

    def _is_type_component(self, component_id: str) -> bool:
        logical = component_id.split("::", 1)[-1]
        node = self.symbols.get(logical)
        return node is not None and node.component_type in ("class", "module")

    def _is_local_reference(self, node: Any, name: str, scope: tuple[str, ...]) -> bool:
        bound, _ = self._binding_before(node, name, scope)
        return bound

    def _add_relationship(self, caller: str, callee: str, call_line: int) -> None:
        target = self.symbols.get(callee.lstrip(":"))
        resolved = target is not None
        destination = target.id if target is not None else callee
        key = (caller, destination, call_line)
        if caller == destination or key in self.seen_relationships:
            return
        self.seen_relationships.add(key)
        self.call_relationships.append(
            CallRelationship(
                caller=caller,
                callee=destination,
                call_line=call_line,
                is_resolved=resolved,
            )
        )

    # ------------------------------------------------------------------
    # Conservative name and receiver resolution
    # ------------------------------------------------------------------

    def _singleton_owner(self, node: Any, scope: tuple[str, ...]) -> str | None:
        obj = next(
            (
                child
                for child in node.named_children
                if child.type in ("self", "constant", "scope_resolution")
            ),
            None,
        )
        if obj is None or obj.type == "self":
            return ".".join(scope)
        return self._resolve_constant(self._constant_text(obj) or "", scope)

    def _constant_text(self, node: Any | None) -> str | None:
        if node is None:
            return None
        if node.type == "constant":
            return self._text(node)
        if node.type == "scope_resolution":
            return (self._text(node) or "").replace("::", ".")
        return None

    def _qualified_constant(self, node: Any | None, scope: tuple[str, ...]) -> str | None:
        """Resolve a declaration name without discarding its lexical namespace."""
        text = self._constant_text(node)
        if not text:
            return None
        normalized = text.replace("::", ".")
        if normalized.startswith("."):
            return normalized.lstrip(".")
        parts = normalized.split(".")
        if len(parts) == 1:
            return ".".join((*scope, *parts)) if scope else normalized
        head = self._resolve_constant(parts[0], scope).lstrip(":")
        return ".".join((*head.split("."), *parts[1:]))

    def _resolve_constant(self, text: str, scope: tuple[str, ...]) -> str:
        normalized = text.replace("::", ".")
        if normalized.startswith("."):
            return f"::{normalized.lstrip('.')}"
        parts = normalized.split(".")
        # Once the first constant is found lexically, the remaining qualified
        # path belongs to that namespace even when the final symbol is absent.
        for length in range(len(scope), -1, -1):
            candidate = ".".join((*scope[:length], parts[0]))
            if candidate in self.symbols:
                return ".".join((*scope[:length], *parts))
        return normalized

    def _inheritance_constant(self, text: str, scope: tuple[str, ...]) -> str:
        normalized = text.replace("::", ".")
        resolved = self._resolve_constant(normalized, scope)
        if resolved != normalized:
            return resolved
        if scope and ".".join(scope) in self.symbols:
            # A superclass expression is evaluated in the enclosing lexical
            # scope, not in the namespace of the class being declared.
            return ".".join((*scope, *normalized.split(".")))
        return f"::{normalized}"

    def _base_classes(self, node: Any, scope: tuple[str, ...]) -> list[str]:
        if node.type != "class":
            return []
        superclass = node.child_by_field_name("superclass")
        if superclass is None:
            return []
        for child in superclass.named_children:
            constant = self._constant_text(child)
            if constant:
                return [self._inheritance_constant(constant, scope)]
        constant = self._constant_text(superclass)
        return [self._inheritance_constant(constant, scope)] if constant else []

    def _constructor_class(self, node: Any, scope: tuple[str, ...]) -> str | None:
        while node.type in ("parentheses", "begin"):
            named = node.named_children
            if len(named) != 1:
                return None
            node = named[0]
        if node.type != "call":
            return None
        if self._text(node.child_by_field_name("method")) != "new":
            return None
        receiver = node.child_by_field_name("receiver")
        constant = self._constant_text(receiver)
        return self._resolve_constant(constant, scope) if constant else None

    def _binding_before(
        self, node: Any, name: str, scope: tuple[str, ...]
    ) -> tuple[bool, str | None]:
        """Return (definitely_bound, constructor_type) on the path to *node*."""
        child = node
        current = node.parent
        while current is not None:
            if current.type in ("method", "singleton_method", "lambda", "block"):
                for parameter in self._parameter_nodes(current):
                    if name in self._parameter_names(parameter):
                        return True, self._constructor_class(parameter, scope)
            if current.type in ("body_statement", "block", "block_body"):
                found = False
                owner: str | None = None
                for sibling in current.named_children:
                    if sibling.start_byte >= child.start_byte:
                        break
                    if sibling.type in ("assignment", "operator_assignment"):
                        left = sibling.child_by_field_name("left")
                        if left is None or left.type != "identifier" or self._text(left) != name:
                            continue
                        found = True
                        right = sibling.child_by_field_name("right")
                        owner = (
                            self._constructor_class(right, scope)
                            if sibling.type == "assignment" and right is not None
                            else None
                        )
                    elif self._may_assign(sibling, name):
                        # A conditional mutation destroys a definite type unless
                        # every path is known; staying conservative avoids false edges.
                        found = True
                        owner = None
                if found:
                    return True, owner
            if current.type in ("method", "singleton_method", "lambda"):
                break
            child = current
            current = current.parent
        return False, None

    def _parameter_nodes(self, node: Any) -> list[Any]:
        if node.type in ("method", "singleton_method", "lambda"):
            params = node.child_by_field_name("parameters")
            return list(params.named_children) if params is not None else []
        params = next(
            (child for child in node.named_children if child.type == "block_parameters"), None
        )
        return list(params.named_children) if params is not None else []

    def _parameter_names(self, node: Any) -> set[str]:
        """Collect only binding names, not identifiers in defaults or types."""
        if node.type == "identifier":
            name = self._text(node)
            return {name} if name else set()
        if node.type in ("optional_argument", "keyword_parameter"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                name_node = next(
                    (child for child in node.named_children if child.type == "identifier"),
                    None,
                )
            return self._parameter_names(name_node) if name_node is not None else set()
        if node.type in (
            "splat_parameter",
            "hash_splat_parameter",
            "block_parameter",
            "destructured_parameter",
        ):
            return {name for child in node.named_children for name in self._parameter_names(child)}
        return set()

    def _contains_name(self, node: Any, name: str) -> bool:
        if node.type == "identifier":
            return self._text(node) == name
        return any(self._contains_name(child, name) for child in node.named_children)

    def _may_assign(self, node: Any, name: str) -> bool:
        """Conservatively detect writes without crossing independent scopes."""
        if node.type in ("assignment", "multiple_assignment", "operator_assignment"):
            left = node.child_by_field_name("left")
            if left is not None:
                return self._contains_name(left, name)
            for child in node.named_children:
                if child.type == "=":
                    break
                if self._contains_name(child, name):
                    return True
            return False
        if node.type in (
            "method",
            "singleton_method",
            "lambda",
            "class",
            "module",
            "singleton_class",
        ):
            return False
        return any(self._may_assign(child, name) for child in node.named_children)

    def _call_arguments(self, node: Any) -> list[Any]:
        arguments = node.child_by_field_name("arguments")
        return list(arguments.named_children) if arguments is not None else []

    def _string_argument(self, node: Any) -> str | None:
        for argument in self._call_arguments(node):
            if argument.type != "string":
                continue
            for child in argument.named_children:
                if child.type == "string_content":
                    return self._text(child)
        return None

    @staticmethod
    def _text(node: Any | None) -> str | None:
        return node.text.decode("utf-8") if node is not None else None


def analyze_ruby_file(
    file_path: str,
    content: str,
    repo_path: str | None = None,
    *,
    defer_implicit: bool = False,
) -> tuple[list[Node], list[CallRelationship]]:
    analyzer = TreeSitterRubyAnalyzer(file_path, content, repo_path, defer_implicit=defer_implicit)
    return analyzer.nodes, analyzer.call_relationships
