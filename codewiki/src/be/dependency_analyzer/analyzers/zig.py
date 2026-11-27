"""基于独立 ``tree-sitter-zig`` wheel 的仓库内依赖分析。

组件保持 ``<relative_path>::<logical_name>`` 身份。容器、泛型容器、
函数与方法均可成文档；边只来自可验证的仓库内声明。未知 receiver 不退化
成裸方法名，外部 import、test 块和 Zig 缓存目录不进入组件图。

该 wheel 的 AST 使用 ``variable_declaration`` / ``function_declaration`` /
``call_expression``，与 language-pack 的新版 ``Decl`` / ``SuffixExpr``
不同；本实现按实际 wheel 形态遍历，不依赖运行时下载 grammar。
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import get_parser

logger = logging.getLogger(__name__)

_CONTAINER_MAPPING = {
    "struct": ("struct", "struct"),
    "enum": ("class", "enum"),
    "union": ("class", "union"),
    "opaque": ("class", "opaque"),
}
_EXTERNAL_IMPORTS = {"std", "builtin", "root"}
_CONSTRUCTOR_NAMES = {"init", "initCapacity", "create", "new", "open", "parse"}
_ZIG_SKIPPED_DIRS = {"zig-cache", ".zig-cache", "zig-out"}
_ADD_MODULE_RE = re.compile(
    r"addModule\(\s*\"([^\"]+)\"\s*,\s*\.\{[^;]*?root_source_file\s*=\s*"
    r"(?:b\.path\(\s*|\.\{\s*\.path\s*=\s*)\"([^\"]+)\"",
    re.DOTALL,
)

# 解析目标：file=文件命名空间；decl=仓库声明；value=已知/未知类型的值。
_EXTERNAL = ("external",)
_UNKNOWN = ("unknown",)


def is_skipped_zig_file(relative_path: str) -> bool:
    """Zig 构建产物不参与源码分析。"""
    return any(part in _ZIG_SKIPPED_DIRS for part in Path(relative_path).parts[:-1])


def _is_within_repo(repo_path: str, path: str | Path) -> bool:
    """realpath 层面判断路径是否位于仓库内，符号链接逃逸也算越界。"""
    if not repo_path:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path(repo_path).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def _safe_repo_file(repo_path: str, relative: str) -> Optional[str]:
    """把仓库内相对路径解析为安全绝对路径；绝对、越界与符号链接逃逸返回 None。"""
    if not repo_path or not relative or "\\" in relative:
        return None
    if relative.startswith("/") or PureWindowsPath(relative).drive:
        return None
    normalized = posixpath.normpath(relative)
    if normalized in {".", ".."} or normalized.startswith("../"):
        return None
    try:
        root = Path(repo_path).resolve()
        candidate = (root / Path(*normalized.split("/"))).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.is_relative_to(root):
        return None
    return str(candidate)


def _safe_repo_relative(repo_path: str, relative: str) -> Optional[str]:
    """返回仓库内 realpath 对应的相对路径，保持与组件 ID 的路径身份一致。"""
    safe_path = _safe_repo_file(repo_path, relative)
    if safe_path is None:
        return None
    try:
        return Path(safe_path).resolve().relative_to(Path(repo_path).resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


@lru_cache(maxsize=64)
def _parse_build_zig(path: str, mtime_ns: int) -> tuple[tuple[str, str], ...]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return tuple((name, posixpath.normpath(root)) for name, root in _ADD_MODULE_RE.findall(text))


def _build_zig_modules(repo_path: str) -> dict[str, str]:
    if not repo_path:
        return {}
    path = os.path.join(repo_path, "build.zig")
    try:
        mtime_ns = os.stat(path).st_mtime_ns
    except OSError:
        return {}
    modules: dict[str, str] = {}
    for name, root in _parse_build_zig(path, mtime_ns):
        safe_relative = _safe_repo_relative(repo_path, root)
        if safe_relative is not None:
            modules[name] = safe_relative
    return modules


@lru_cache(maxsize=4096)
def _file_aliases(path: str, mtime_ns: int, repo_path: str) -> dict[str, tuple]:
    """读取另一文件的顶层别名，供仓库内 re-export 闭包使用。"""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    analyzer = TreeSitterZigAnalyzer(path, content, repo_path, components_only=True)
    return dict(analyzer.aliases)


@lru_cache(maxsize=4096)
def _file_components(path: str, mtime_ns: int, repo_path: str) -> frozenset[str]:
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    analyzer = TreeSitterZigAnalyzer(path, content, repo_path, components_only=True)
    return frozenset(analyzer.components)


@dataclass
class _Container:
    node: Any
    logical: str
    parent: Optional[str]
    decls: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)


class TreeSitterZigAnalyzer:
    """分析单个 Zig 文件；grammar/parser 错误必须显式失败。"""

    def __init__(
        self,
        file_path: str,
        content: str,
        repo_path: Optional[str] = None,
        *,
        components_only: bool = False,
    ):
        self.file_path = Path(file_path)
        self.content = content
        self.repo_path = repo_path or ""
        self.nodes: list[Node] = []
        self.call_relationships: list[CallRelationship] = []
        self.components: dict[str, Node] = {}
        self.aliases: dict[str, tuple] = {}
        self.seen_relationships: set[tuple[str, str]] = set()
        self.relative_path = Path(self._get_relative_path()).as_posix()
        self._containers: dict[str, _Container] = {}
        self._returns: dict[str, tuple[Any, str]] = {}
        self._alias_cache: dict[tuple[str, str], Any] = {}
        self._return_cache: dict[str, Any] = {}
        self._components_only = components_only
        if self.repo_path and not _is_within_repo(self.repo_path, self.file_path):
            return
        if is_skipped_zig_file(self.relative_path):
            return
        self._analyze()

    def _get_relative_path(self) -> str:
        if self.repo_path:
            try:
                return os.path.relpath(
                    os.path.realpath(str(self.file_path)), os.path.realpath(self.repo_path)
                )
            except ValueError:
                pass
        return str(self.file_path)

    def _get_component_id(self, logical: str) -> str:
        return f"{self.relative_path}::{logical}"

    @staticmethod
    def _text(node: Any) -> str:
        return node.text.decode("utf8", errors="replace") if node is not None else ""

    @staticmethod
    def _qualify(owner: str, name: str) -> str:
        return f"{owner}.{name}" if owner else name

    @staticmethod
    def _descendants(node: Any, node_type: str):
        stack = list(reversed(node.children))
        while stack:
            current = stack.pop()
            if current.type == node_type:
                yield current
            stack.extend(reversed(current.children))

    def _analyze(self) -> None:
        # 不捕获 GrammarUnavailableError，也不把 parser 故障吞成空组件。
        root = get_parser("zig").parse(bytes(self.content, "utf8")).root_node
        lines = self.content.splitlines()
        self._collect_container(root, "", None, lines)
        if self._components_only:
            return
        for container in list(self._containers.values()):
            self._extract_container_relationships(container)

    # ---- 组件与词法容器 ------------------------------------------------

    def _collect_container(self, node: Any, logical: str, parent: Optional[str], lines) -> None:
        container = _Container(node, logical, parent)
        self._containers[logical] = container
        for child in node.children:
            if child.type == "container_field":
                name = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name is not None and type_node is not None:
                    container.fields[self._text(name)] = type_node
            elif child.type in ("function_declaration", "variable_declaration"):
                self._collect_decl(child, container, lines)

    def _collect_decl(self, decl: Any, container: _Container, lines) -> None:
        if decl.type == "function_declaration":
            name_node = decl.child_by_field_name("name")
            body = decl.child_by_field_name("body")
            # extern 函数和函数声明没有可文档化的实现。
            if name_node is None or body is None:
                return
            name = self._text(name_node)
            logical = self._qualify(container.logical, name)
            return_type = decl.child_by_field_name("type")
            if return_type is not None:
                self._returns[logical] = (return_type, container.logical)
            generic = self._generic_container(decl)
            if generic is not None:
                self._add_container_component(decl, generic, logical, container, lines)
                return
            container.decls[name] = logical
            is_method = bool(container.logical)
            self._add_node(
                decl,
                logical,
                "method" if is_method else "function",
                "method" if is_method else "function",
                lines,
                class_name=container.logical or None,
                parameters=self._parameters(decl),
            )
            return

        name_node = next((c for c in decl.children if c.type == "identifier"), None)
        if name_node is None:
            return
        name = self._text(name_node)
        value = self._var_value(decl)
        chain = self._alias_chain(decl)
        if chain is not None:
            self.aliases[name] = chain
        nested = self._container_decl(value)
        if nested is not None:
            self._add_container_component(
                decl, nested, self._qualify(container.logical, name), container, lines
            )
            return
        container.aliases[name] = decl
        if chain is not None and not container.logical:
            self.aliases[name] = chain

    def _add_container_component(self, decl, nested, logical, container, lines) -> None:
        name = logical.rpartition(".")[2]
        container.decls[name] = logical
        component_type, node_type = _CONTAINER_MAPPING[nested.type.removesuffix("_declaration")]
        generic = decl.type == "function_declaration"
        self._add_node(
            decl,
            logical,
            component_type,
            node_type,
            lines,
            parameters=self._parameters(decl) if generic else None,
            display_name=f"{'generic ' if generic else ''}{node_type} {logical}",
        )
        self._collect_container(nested, logical, container.logical, lines)

    def _generic_container(self, decl: Any) -> Any:
        return_type = decl.child_by_field_name("type")
        if return_type is None or self._text(return_type).strip() != "type":
            return None
        body = decl.child_by_field_name("body")
        if body is None:
            return None
        for node in self._descendants(body, "return_expression"):
            for child in node.named_children:
                nested = self._container_decl(child)
                if nested is not None:
                    return nested
        return None

    @staticmethod
    def _container_decl(expr: Any) -> Any:
        if expr is None:
            return None
        if expr.type in {
            "struct_declaration",
            "enum_declaration",
            "union_declaration",
            "opaque_declaration",
        }:
            return expr
        for child in expr.named_children:
            if child.type in {
                "struct_declaration",
                "enum_declaration",
                "union_declaration",
                "opaque_declaration",
            }:
                return child
        return None

    @staticmethod
    def _var_value(decl: Any) -> Any:
        children = list(decl.children)
        for index, child in enumerate(children):
            if child.type == "=":
                return next((c for c in children[index + 1 :] if c.is_named), None)
        return None

    def _parameters(self, decl: Any) -> Optional[list[str]]:
        params = next((c for c in decl.children if c.type == "parameters"), None)
        if params is None:
            return None
        names = []
        for param in params.named_children:
            if param.type == "parameter":
                name = param.child_by_field_name("name")
                if name is not None:
                    names.append(self._text(name))
        return names or None

    def _extract_docstring(self, decl: Any) -> str:
        comments = []
        sibling = decl.prev_sibling
        while sibling is not None and sibling.type in {"comment", "line_comment", "doc_comment"}:
            comments.append(self._text(sibling))
            sibling = sibling.prev_sibling
        lines = []
        for block in reversed(comments):
            for line in block.splitlines():
                line = line.strip()
                if line.startswith("///"):
                    lines.append(line[3:].strip())
        return "\n".join(lines)

    def _add_node(
        self,
        decl: Any,
        logical: str,
        component_type: str,
        node_type: str,
        lines: list[str],
        class_name: Optional[str] = None,
        parameters: Optional[list[str]] = None,
        display_name: Optional[str] = None,
    ) -> None:
        if logical in self.components:
            return
        component_id = self._get_component_id(logical)
        docstring = self._extract_docstring(decl)
        start = decl.start_point[0]
        end = decl.end_point[0] + 1
        node = Node(
            id=component_id,
            name=logical,
            component_type=component_type,
            file_path=str(self.file_path),
            relative_path=self.relative_path,
            source_code="\n".join(lines[start:end]),
            start_line=decl.start_point[0] + 1,
            end_line=end,
            has_docstring=bool(docstring),
            docstring=docstring,
            parameters=parameters,
            node_type=node_type,
            class_name=class_name,
            display_name=display_name or f"{node_type} {logical}",
            component_id=component_id,
            language="zig",
        )
        self.nodes.append(node)
        self.components[logical] = node

    # ---- import / 名称解析 ---------------------------------------------

    def _resolve_import(self, spec: str, importer: Optional[str] = None) -> Any:
        if spec in _EXTERNAL_IMPORTS:
            return _EXTERNAL
        if not spec.endswith(".zig"):
            root = _build_zig_modules(self.repo_path).get(spec)
            return ("file", root) if root else _EXTERNAL
        importer = importer or self.relative_path
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        if joined.startswith("../") or joined == ".." or posixpath.isabs(joined):
            return _EXTERNAL
        if not self.repo_path:
            return ("file", joined)
        safe_path = _safe_repo_file(self.repo_path, joined)
        if safe_path is None or not os.path.isfile(safe_path):
            return _EXTERNAL
        safe_relative = _safe_repo_relative(self.repo_path, joined)
        return ("file", safe_relative) if safe_relative is not None else _EXTERNAL

    def _lookup(self, name: str, scope: str, locals_: Optional[dict]) -> Any:
        if locals_ is not None and name in locals_:
            target = locals_[name]
            if target == _EXTERNAL:
                return _EXTERNAL
            return ("value", target) if target is not None else _UNKNOWN
        current: Optional[str] = scope
        while current is not None:
            container = self._containers.get(current)
            if container is None:
                break
            if name in container.decls:
                return ("decl", self.relative_path, container.decls[name])
            if name in container.aliases:
                return self._resolve_alias(current, name)
            current = container.parent
        return None

    def _resolve_alias(self, scope: str, name: str) -> Any:
        key = (scope, name)
        if key in self._alias_cache:
            return self._alias_cache[key]
        self._alias_cache[key] = None
        decl = self._containers[scope].aliases[name]
        type_node = next(
            (c for c in decl.children if c.type not in {"identifier", "const", "var", ":", "="}),
            None,
        )
        has_colon = any(c.type == ":" for c in decl.children)
        target = self._type_target(type_node, scope) if has_colon and type_node else None
        if target is None:
            target = self._expr_target(decl, scope, None, None)
        self._alias_cache[key] = target
        return target

    def _reexport(self, path: str, name: str, depth: int = 0) -> Any:
        if depth > 8 or not self.repo_path:
            return None
        safe_relative = _safe_repo_relative(self.repo_path, path)
        if safe_relative is None:
            return None
        abs_path = _safe_repo_file(self.repo_path, safe_relative)
        if abs_path is None:
            return None
        try:
            mtime_ns = os.stat(abs_path).st_mtime_ns
        except OSError:
            return None
        chain = _file_aliases(abs_path, mtime_ns, self.repo_path).get(name)
        if chain is None:
            return None
        (kind, value), fields = chain
        target = (
            self._resolve_import(value, importer=safe_relative)
            if kind == "import"
            else self._reexport(safe_relative, value, depth + 1) or ("decl", safe_relative, value)
        )
        for member in fields:
            target = self._member(target, member, depth + 1)
        return target

    def _member(self, target: Any, name: str, depth: int = 0) -> Any:
        if target is None or target == _UNKNOWN:
            return target
        kind = target[0]
        if kind == "external":
            return target
        if kind == "file":
            if target[1] != self.relative_path:
                reexported = self._reexport(target[1], name, depth)
                if reexported is not None:
                    return reexported
            return ("decl", target[1], name)
        if kind == "decl":
            return ("decl", target[1], self._qualify(target[2], name))
        if kind == "value":
            type_target = target[1]
            if type_target is None:
                return _UNKNOWN
            if type_target == _EXTERNAL:
                return _EXTERNAL
            if type_target[1] != self.relative_path:
                return _UNKNOWN
            container = self._containers.get(type_target[2])
            if container is not None and name in container.fields:
                return ("value", self._type_target(container.fields[name], container.logical))
            return _UNKNOWN
        return None

    def _method_of(self, target: Any, name: str) -> Any:
        if target is None or target == _UNKNOWN:
            return None
        if target[0] == "value":
            type_target = target[1]
            if type_target is None:
                return None
            if type_target == _EXTERNAL:
                return _EXTERNAL
            return ("decl", type_target[1], self._qualify(type_target[2], name))
        return self._member(target, name)

    def _call_result(self, callee: Any) -> Any:
        if callee == _EXTERNAL:
            return _EXTERNAL
        if callee is None or callee[0] != "decl":
            return _UNKNOWN
        path, logical = callee[1], callee[2]
        if (path == self.relative_path and logical in self._containers) or (
            path != self.relative_path and logical.rpartition(".")[2][:1].isupper()
        ):
            return callee
        if path == self.relative_path and logical in self._returns:
            return ("value", self._function_return(logical))
        owner, _, method = logical.rpartition(".")
        if owner and method in _CONSTRUCTOR_NAMES:
            return ("value", ("decl", path, owner))
        return _UNKNOWN

    def _function_return(self, logical: str) -> Any:
        if logical not in self._return_cache:
            self._return_cache[logical] = None
            type_node, scope = self._returns[logical]
            self._return_cache[logical] = self._type_target(type_node, scope)
        return self._return_cache[logical]

    def _type_target(self, type_node: Any, scope: str) -> Any:
        if type_node is None:
            return None
        if type_node.type in {"pointer_type", "nullable_type", "optional_type", "error_union_type"}:
            for child in type_node.named_children:
                target = self._type_target(child, scope)
                if target is not None:
                    return target
            return None
        if type_node.type == "builtin_function" and self._text(type_node).startswith("@This"):
            return ("decl", self.relative_path, scope) if scope else None
        target = self._expr_target(type_node, scope, None, None)
        if target == _EXTERNAL:
            return _EXTERNAL
        return target if target is not None and target[0] == "decl" else None

    def _expr_target(
        self, holder: Any, scope: str, locals_: Optional[dict], caller_id: Optional[str]
    ) -> Any:
        if holder is None:
            return None
        if holder.type == "variable_declaration":
            target = self._expr_target(self._var_value(holder), scope, locals_, caller_id)
            return target
        if holder.type in {
            "return_expression",
            "expression_statement",
            "try_expression",
            "await_expression",
        }:
            return self._expr_target(
                next((c for c in holder.named_children if c.type != "comment"), None),
                scope,
                locals_,
                caller_id,
            )
        if holder.type == "identifier":
            return self._lookup(self._text(holder), scope, locals_)
        if holder.type == "builtin_function":
            name = next((c for c in holder.children if c.type == "builtin_identifier"), None)
            builtin = self._text(name)
            if builtin == "@This":
                return ("decl", self.relative_path, scope) if scope else None
            if builtin == "@import":
                literal = next(self._descendants(holder, "string_content"), None)
                return self._resolve_import(self._text(literal)) if literal else _EXTERNAL
            return None
        if holder.type == "field_expression":
            base = holder.child_by_field_name("object")
            member = holder.child_by_field_name("member")
            return self._member(
                self._expr_target(base, scope, locals_, caller_id), self._text(member)
            )
        if holder.type == "call_expression":
            return self._eval_call(holder, scope, locals_, caller_id)
        if holder.type == "struct_initializer":
            constructor = next(
                (c for c in holder.named_children if c.type != "initializer_list"), None
            )
            target = self._expr_target(constructor, scope, locals_, caller_id)
            if caller_id is not None and target is not None and target[0] == "decl":
                self._emit(caller_id, target, holder)
            self._walk_initializer(holder.child_by_field_name("value"), scope, locals_, caller_id)
            return ("value", target) if target is not None and target[0] == "decl" else _UNKNOWN
        return None

    def _eval_call(
        self, node: Any, scope: str, locals_: Optional[dict], caller_id: Optional[str]
    ) -> Any:
        function = node.child_by_field_name("function")
        if function is not None and function.type == "field_expression":
            base = function.child_by_field_name("object")
            member = function.child_by_field_name("member")
            callee = self._method_of(
                self._expr_target(base, scope, locals_, caller_id), self._text(member)
            )
        else:
            callee = self._expr_target(function, scope, locals_, caller_id)
        self._emit(caller_id, callee, function or node)
        for child in node.named_children:
            if child != function:
                self._walk(child, scope, locals_, caller_id)
        return self._call_result(callee)

    def _walk_initializer(
        self, node: Any, scope: str, locals_: Optional[dict], caller_id: Optional[str]
    ) -> None:
        if node is None:
            return
        if node.type == "assignment_expression":
            value = node.child_by_field_name("right")
            self._walk(value, scope, locals_, caller_id)
            return
        for child in node.named_children:
            self._walk_initializer(child, scope, locals_, caller_id)

    def _alias_chain(self, decl: Any) -> Optional[tuple]:
        value = self._var_value(decl)
        if value is None:
            return None
        fields: list[str] = []
        current = value
        while current is not None and current.type == "field_expression":
            member = current.child_by_field_name("member")
            if member is None:
                return None
            fields.append(self._text(member))
            current = current.child_by_field_name("object")
        if current is None:
            return None
        if current.type == "identifier":
            base = ("name", self._text(current))
        elif current.type == "builtin_function" and self._text(current).startswith("@import"):
            literal = next(self._descendants(current, "string_content"), None)
            if literal is None:
                return None
            base = ("import", self._text(literal))
        else:
            return None
        return base, tuple(reversed(fields))

    # ---- 边提取 ---------------------------------------------------------

    def _emit(self, caller_id: Optional[str], target: Any, anchor: Any) -> None:
        if caller_id is None or target is None or target[0] != "decl" or not target[2]:
            return
        path, logical = target[1], target[2]
        if path == self.relative_path:
            if logical not in self.components:
                return
            callee = self._get_component_id(logical)
            resolved = True
        elif self._declared_in(path, logical):
            callee = f"{path}::{logical}"
            resolved = False
        else:
            return
        if caller_id == callee or (caller_id, callee) in self.seen_relationships:
            return
        self.seen_relationships.add((caller_id, callee))
        self.call_relationships.append(
            CallRelationship(
                caller=caller_id,
                callee=callee,
                call_line=anchor.start_point[0] + 1,
                is_resolved=resolved,
            )
        )

    def _declared_in(self, path: str, logical: str) -> bool:
        if not self.repo_path:
            return True
        abs_path = _safe_repo_file(self.repo_path, path)
        if abs_path is None:
            return False
        try:
            mtime_ns = os.stat(abs_path).st_mtime_ns
        except OSError:
            return False
        return logical in _file_components(abs_path, mtime_ns, self.repo_path)

    def _emit_type_refs(self, type_node: Any, scope: str, caller_id: Optional[str]) -> None:
        if caller_id is None or type_node is None:
            return
        for node in [
            type_node,
            *self._descendants(type_node, "identifier"),
            *self._descendants(type_node, "field_expression"),
        ]:
            if node.type not in {"identifier", "field_expression"}:
                continue
            target = self._type_target(node, scope)
            self._emit(caller_id, target, node)

    def _extract_container_relationships(self, container: _Container) -> None:
        scope = container.logical
        container_id = self._get_component_id(scope) if scope else None
        for type_node in container.fields.values():
            self._emit_type_refs(type_node, scope, container_id)
        for child in container.node.children:
            if child.type == "function_declaration":
                body = child.child_by_field_name("body")
                name = child.child_by_field_name("name")
                if body is None or name is None:
                    continue
                logical = self._qualify(scope, self._text(name))
                if logical in self._containers:
                    continue
                self._extract_function(child, body, logical, scope)
            elif child.type == "variable_declaration" and container_id is not None:
                value = self._var_value(child)
                if value is not None and self._container_decl(value) is None:
                    self._walk(child, scope, None, container_id)

    def _extract_function(self, decl: Any, body: Any, logical: str, scope: str) -> None:
        caller_id = self._get_component_id(logical)
        locals_: dict[str, Any] = {}
        params = next((c for c in decl.children if c.type == "parameters"), None)
        if params is not None:
            for param in params.named_children:
                if param.type != "parameter":
                    continue
                name = param.child_by_field_name("name")
                type_node = param.child_by_field_name("type")
                if name is None:
                    continue
                locals_[self._text(name)] = self._type_target(type_node, scope)
                self._emit_type_refs(type_node, scope, caller_id)
        return_type = decl.child_by_field_name("type")
        self._emit_type_refs(return_type, scope, caller_id)
        self._walk(body, scope, locals_, caller_id)

    def _walk(
        self, node: Any, scope: str, locals_: Optional[dict], caller_id: Optional[str]
    ) -> None:
        if node is None:
            return
        if node.type in {
            "test_declaration",
            "struct_declaration",
            "enum_declaration",
            "union_declaration",
            "opaque_declaration",
        }:
            return
        if node.type == "block" and locals_ is not None:
            outer_locals = locals_.copy()
            for child in node.named_children:
                self._walk(child, scope, locals_, caller_id)
            locals_.clear()
            locals_.update(outer_locals)
            return
        if node.type == "call_expression":
            self._eval_call(node, scope, locals_, caller_id)
            return
        if node.type == "variable_declaration":
            name = next((c for c in node.children if c.type == "identifier"), None)
            children = list(node.children)
            colon = next((i for i, c in enumerate(children) if c.type == ":"), None)
            type_node = (
                next((c for c in children[colon + 1 :] if c.is_named), None)
                if colon is not None
                else None
            )
            value = self._var_value(node)
            if type_node is not None:
                self._emit_type_refs(type_node, scope, caller_id)
                type_target = self._type_target(type_node, scope)
            else:
                target = self._expr_target(value, scope, locals_, caller_id)
                type_target = target[1] if target is not None and target[0] == "value" else target
            if name is not None and locals_ is not None:
                locals_[self._text(name)] = type_target
            self._walk(value, scope, locals_, caller_id)
            return
        for child in node.named_children:
            self._walk(child, scope, locals_, caller_id)


def analyze_zig_file(
    file_path: str, content: str, repo_path: Optional[str] = None
) -> tuple[list[Node], list[CallRelationship]]:
    analyzer = TreeSitterZigAnalyzer(file_path, content, repo_path)
    return analyzer.nodes, analyzer.call_relationships
