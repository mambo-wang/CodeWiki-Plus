"""Vue 单文件组件分析器。

使用确定性的顶层块扫描器切分 ``template`` 与 ``script``，脚本内容在等长
掩码后复用现有 JavaScript/TypeScript 分析器，因此节点行号仍对应原始
``.vue`` 文件。模板只提取组件标签、指令和插值中的已知标识符，不尝试
执行模板或推断完整的 Vue 运行时语义。

边界：只解析相对路径与 ``@/`` 别名；不跟随 mixins、extends 或全局
``Vue.component`` 注册；其他 bundler 别名与包导入不形成边。
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node
from codewiki.src.be.dependency_analyzer.utils.grammars import (
    GrammarUnavailableError,
    get_parser,
)

logger = logging.getLogger(__name__)

_MEMBER_GROUPS = {"methods", "computed", "watch"}
_LIFECYCLE_HOOKS = {
    "setup",
    "beforeCreate",
    "created",
    "beforeMount",
    "mounted",
    "beforeUpdate",
    "updated",
    "beforeUnmount",
    "unmounted",
    "beforeDestroy",
    "destroyed",
    "activated",
    "deactivated",
    "errorCaptured",
    "beforeRouteEnter",
    "beforeRouteUpdate",
    "beforeRouteLeave",
    "asyncData",
    "fetch",
    "serverPrefetch",
}
_BUILTIN_TAGS = {
    "component",
    "slot",
    "template",
    "transition",
    "transition-group",
    "keep-alive",
    "teleport",
    "suspense",
    "router-link",
    "router-view",
    "client-only",
    "nuxt-link",
    "nuxt",
}
_SCRIPT_EXTS = (".vue", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_FUNCTION_VALUES = {"function_expression", "function", "arrow_function", "generator_function"}
_IDENT_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)")
_INTERPOLATION_RE = re.compile(r"\{\{([\s\S]*?)\}\}")
_ATTR_RE = re.compile(r"""([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?""")
_JS_KEYWORDS = {
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "let",
    "new",
    "null",
    "of",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "undefined",
    "var",
    "void",
    "while",
    "with",
    "yield",
}


@dataclass(frozen=True)
class _SfcBlock:
    """一个顶层 SFC 块；起止位置是原始字符串的字符下标。"""

    kind: str
    start: int
    end: int
    language: str = "js"


@dataclass(frozen=True)
class _Tag:
    name: str
    start: int
    end: int
    closing: bool
    self_closing: bool
    attributes: str


def pascal_case(name: str) -> str:
    """将 kebab-case、snake_case 等标签名转成 PascalCase。"""
    parts = [part for part in re.split(r"[-_.\s]+", name) if part]
    return "".join(part[0].upper() + part[1:] for part in parts)


def vue_component_name(relative_path: str) -> str:
    """由文件路径推导逻辑组件名；``index.vue`` 使用父目录名。"""
    path = Path(relative_path)
    stem = path.stem
    if stem.lower() == "index" and path.parent.name:
        stem = path.parent.name
    return pascal_case(stem) or stem


def _skip_interpolation(content: str, start: int) -> int:
    """跳过 ``{{ ... }}``，避免插值里的字符串或伪标签参与结构扫描。"""
    depth = 2
    quote = ""
    escaped = False
    cursor = start + 2
    while cursor < len(content):
        char = content[cursor]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return len(content)


def _next_tag(content: str, position: int) -> tuple[_Tag | None, int]:
    """查找下一个真实标签，跳过注释、声明与插值，并正确处理引号内的 ``>``。"""
    while position < len(content):
        interpolation = content.find("{{", position)
        start = content.find("<", position)
        if interpolation >= 0 and (start < 0 or interpolation < start):
            position = _skip_interpolation(content, interpolation)
            continue
        if start < 0:
            return None, len(content)
        if content.startswith("<!--", start):
            end = content.find("-->", start + 4)
            position = len(content) if end < 0 else end + 3
            continue
        if content.startswith("<!", start) or content.startswith("<?", start):
            end = content.find(">", start + 2)
            position = len(content) if end < 0 else end + 1
            continue

        quote = ""
        cursor = start + 1
        while cursor < len(content):
            char = content[cursor]
            if quote:
                if char == quote:
                    quote = ""
            elif char in {"'", '"'}:
                quote = char
            elif char == ">":
                break
            cursor += 1
        if cursor >= len(content):
            return None, len(content)

        raw = content[start : cursor + 1]
        match = re.fullmatch(r"<\s*(/?)\s*([A-Za-z][\w:.-]*)([\s\S]*?)\s*(/?)>", raw)
        if match is None:
            position = cursor + 1
            continue
        closing, name, attributes, slash = match.groups()
        return (
            _Tag(
                name=name,
                start=start,
                end=cursor + 1,
                closing=bool(closing),
                self_closing=bool(slash),
                attributes=attributes,
            ),
            cursor + 1,
        )
    return None, len(content)


def _attributes(raw: str) -> dict[str, str]:
    """解析标签属性，保留属性值原始大小写。"""
    values: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        name = match.group(1)
        value = next((part for part in match.groups()[1:] if part is not None), "")
        values[name.lower()] = value
    return values


def _scan_sfc(content: str) -> tuple[list[_SfcBlock], _SfcBlock | None]:
    """只识别顶层块；模板内部嵌套的 ``template`` 不会提前结束外层块。"""
    scripts: list[_SfcBlock] = []
    template: _SfcBlock | None = None
    position = 0
    while position < len(content):
        tag, position = _next_tag(content, position)
        if tag is None or tag.closing or tag.self_closing:
            continue
        kind = tag.name.lower()
        if kind in {"script", "style"}:
            close_re = re.compile(rf"</\s*{kind}\s*>", re.IGNORECASE)
            close = close_re.search(content, tag.end)
            end = close.start() if close is not None else len(content)
            language = "js"
            if kind == "script":
                language = _attributes(tag.attributes).get("lang", "js").strip().lower() or "js"
                scripts.append(_SfcBlock(kind, tag.end, end, language))
            position = close.end() if close is not None else len(content)
        elif kind == "template" and template is None:
            depth = 1
            cursor = tag.end
            end = len(content)
            close_end = len(content)
            while cursor < len(content):
                child, cursor = _next_tag(content, cursor)
                if child is None:
                    break
                if child.name.lower() != "template":
                    continue
                if child.closing:
                    depth -= 1
                    if depth == 0:
                        end = child.start
                        close_end = child.end
                        break
                elif not child.self_closing:
                    depth += 1
            template = _SfcBlock("template", tag.end, end)
            position = close_end
    return scripts, template


def _mask_outside_scripts(content: str, scripts: list[_SfcBlock]) -> str:
    """将脚本外字符替换为空格但保留换行，维持原文件行号。"""
    masked = [char if char == "\n" else " " for char in content]
    for script in scripts:
        masked[script.start : script.end] = content[script.start : script.end]
    return "".join(masked)


def _is_sfc(target: str) -> bool:
    return ".vue::" in target


class VueSfcAnalyzer:
    """提取组件、Options API 成员、脚本节点及模板引用。"""

    def __init__(self, file_path: str, content: str, repo_path: str | None = None):
        self.file_path = Path(file_path)
        self.content = content
        self.repo_path = repo_path or ""
        self.nodes: list[Node] = []
        self.call_relationships: list[CallRelationship] = []
        self.seen_relationships: set[tuple[str, str]] = set()
        self.relative_path = Path(self._get_relative_path()).as_posix()
        self.component_name = vue_component_name(self.relative_path)
        self.component_id = f"{self.relative_path}::{self.component_name}"
        self.imports: dict[str, str] = {}
        self.import_lines: dict[str, int] = {}
        self.members: dict[str, str] = {}
        self.script_names: dict[str, str] = {}
        self._member_nodes: dict[str, Any] = {}
        self._analyze()

    def _get_relative_path(self) -> str:
        if self.repo_path:
            try:
                return os.path.relpath(str(self.file_path), self.repo_path)
            except ValueError:
                return str(self.file_path)
        return str(self.file_path)

    @staticmethod
    def _text(node) -> str:
        return node.text.decode("utf8", errors="replace") if node is not None else ""

    def _analyze(self) -> None:
        try:
            scripts, template = _scan_sfc(self.content)
            lines = self.content.splitlines()
            self._add_component_node(lines)
            if scripts:
                masked = _mask_outside_scripts(self.content, scripts)
                use_ts = any(script.language in {"ts", "tsx"} for script in scripts)
                language = "typescript" if use_ts else "javascript"
                # grammar 缺失必须显式失败，不能被本文件的容错捕获吞掉。
                script_root = get_parser(language).parse(masked.encode("utf8")).root_node
                self._run_script_analyzer(masked, use_ts)
                self._collect_imports(script_root)
                self._extract_options(script_root, lines)
                self._extract_member_calls()
                for local, target in self.imports.items():
                    self._add_relationship(
                        self.component_id,
                        target,
                        self.import_lines.get(local, 1),
                        _is_sfc(target),
                    )
            if template is not None:
                self._extract_template_edges(template)
        except GrammarUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — 坏文件不能中断整仓分析
            logger.error("解析 Vue 文件 %s 失败：%s", self.file_path, exc)

    def _run_script_analyzer(self, masked: str, use_ts: bool) -> None:
        if use_ts:
            from codewiki.src.be.dependency_analyzer.analyzers.typescript import (
                analyze_typescript_file_treesitter as analyze,
            )
        else:
            from codewiki.src.be.dependency_analyzer.analyzers.javascript import (
                analyze_javascript_file_treesitter as analyze,
            )

        nodes, relationships = analyze(str(self.file_path), masked, repo_path=self.repo_path)
        script_prefix = f"{self.relative_path}::script.{self.component_name}"

        def remap_id(node_id: str) -> str:
            if node_id == self.component_id:
                return script_prefix
            if node_id.startswith(self.component_id + "."):
                return script_prefix + node_id[len(self.component_id) :]
            return node_id

        for node in nodes:
            node.id = remap_id(node.id)
            if node.component_id:
                node.component_id = remap_id(node.component_id)
            self.nodes.append(node)
            self.script_names.setdefault(node.name.split(".")[-1], node.id)
        for rel in relationships:
            self.call_relationships.append(
                CallRelationship(
                    caller=remap_id(rel.caller),
                    callee=remap_id(rel.callee),
                    call_line=rel.call_line,
                    is_resolved=rel.is_resolved,
                )
            )

    def _collect_imports(self, root) -> None:
        for statement in root.children:
            if statement.type != "import_statement":
                continue
            source = statement.child_by_field_name("source")
            target_file = self._resolve_import_path(self._text(source).strip("\"'`"))
            if target_file is None:
                continue
            clause = next(
                (child for child in statement.children if child.type == "import_clause"),
                None,
            )
            if clause is None:
                continue
            for part in clause.children:
                if part.type == "identifier":
                    local = self._text(part)
                    target = (
                        f"{target_file}::{vue_component_name(target_file)}"
                        if target_file.endswith(".vue")
                        else local
                    )
                    self.imports[local] = target
                    self.import_lines[local] = statement.start_point[0] + 1
                elif part.type == "named_imports":
                    for specifier in part.children:
                        if specifier.type != "import_specifier":
                            continue
                        name = self._text(specifier.child_by_field_name("name"))
                        alias = specifier.child_by_field_name("alias")
                        local = self._text(alias) if alias is not None else name
                        self.imports[local] = f"{target_file}::{name}"
                        self.import_lines[local] = statement.start_point[0] + 1

    def _resolve_import_path(self, specifier: str) -> str | None:
        if specifier.startswith("@/"):
            base = posixpath.normpath(posixpath.join("src", specifier[2:]))
        elif specifier.startswith("."):
            here = posixpath.dirname(self.relative_path)
            base = posixpath.normpath(posixpath.join(here, specifier))
        else:
            return None
        if base == ".." or base.startswith("../"):
            return None

        candidates = [base] if base.endswith(_SCRIPT_EXTS) else []
        candidates.extend(base + extension for extension in _SCRIPT_EXTS)
        candidates.extend(posixpath.join(base, "index" + extension) for extension in _SCRIPT_EXTS)
        if not self.repo_path:
            return candidates[0]
        repo = Path(self.repo_path).resolve()
        for candidate in candidates:
            path = (repo / candidate).resolve()
            try:
                path.relative_to(repo)
            except ValueError:
                continue
            if path.is_file():
                return candidate
        return None

    @staticmethod
    def _component_object(root):
        """取出 ``export default {...}`` 或 ``defineComponent({...})`` 的对象。"""
        for statement in root.children:
            if statement.type != "export_statement":
                continue
            value = statement.child_by_field_name("value")
            if value is None:
                value = statement.child_by_field_name("declaration")
            if value is None:
                value = next(
                    (
                        child
                        for child in statement.named_children
                        if child.type in {"object", "call_expression"}
                    ),
                    None,
                )
            if value is not None and value.type == "call_expression":
                arguments = value.child_by_field_name("arguments")
                value = (
                    next(
                        (child for child in arguments.named_children if child.type == "object"),
                        None,
                    )
                    if arguments is not None
                    else None
                )
            if value is not None and value.type == "object":
                return value
        return None

    @staticmethod
    def _property(prop) -> tuple[str | None, Any | None]:
        if prop.type == "method_definition":
            return VueSfcAnalyzer._text(prop.child_by_field_name("name")), prop
        if prop.type == "pair":
            key = VueSfcAnalyzer._text(prop.child_by_field_name("key")).strip("\"'")
            value = prop.child_by_field_name("value")
            if value is not None and value.type in _FUNCTION_VALUES:
                return key, value
            return key, value if value is not None and value.type == "object" else None
        if prop.type == "shorthand_property_identifier":
            return VueSfcAnalyzer._text(prop), None
        return None, None

    def _extract_options(self, root, lines: list[str]) -> None:
        options = self._component_object(root)
        if options is None:
            return
        for prop in options.named_children:
            key, value = self._property(prop)
            if key in _MEMBER_GROUPS and value is not None and value.type == "object":
                for entry in value.named_children:
                    name, function = self._property(entry)
                    if not name or function is None:
                        continue
                    if key == "watch" and function.type == "object":
                        handler = next(
                            (
                                child
                                for child in function.named_children
                                if self._property(child)[0] == "handler"
                            ),
                            None,
                        )
                        function = self._property(handler)[1] if handler is not None else None
                    if function is not None and function.type in _FUNCTION_VALUES | {
                        "method_definition"
                    }:
                        self._add_member(name, function, lines)
            elif key == "components" and value is not None and value.type == "object":
                for entry in value.named_children:
                    name, _ = self._property(entry)
                    if name and name not in self.imports:
                        self.imports[name] = name
            elif (
                key in _LIFECYCLE_HOOKS
                and value is not None
                and value.type in _FUNCTION_VALUES | {"method_definition"}
            ):
                self._add_member(key, value, lines)

    def _add_member(self, name: str, node, lines: list[str]) -> None:
        if name in self.members:
            return
        logical_name = f"{self.component_name}.{name}"
        member_id = f"{self.relative_path}::{logical_name}"
        start = node.start_point[0]
        end = node.end_point[0] + 1
        parameters = node.child_by_field_name("parameters")
        parameter_names = (
            [self._text(child) for child in parameters.named_children]
            if parameters is not None
            else []
        )
        self.nodes.append(
            Node(
                id=member_id,
                name=logical_name,
                component_type="method",
                file_path=str(self.file_path),
                relative_path=self.relative_path,
                source_code="\n".join(lines[start:end]),
                start_line=start + 1,
                end_line=end,
                node_type="method",
                class_name=self.component_name,
                display_name=f"method {logical_name}",
                component_id=member_id,
                language="vue",
                parameters=parameter_names,
            )
        )
        self.members[name] = member_id
        self._member_nodes[member_id] = node
        self._add_relationship(self.component_id, member_id, start + 1, resolved=True)

    def _extract_member_calls(self) -> None:
        for member_id, node in self._member_nodes.items():
            for call in self._descendants(node, "call_expression"):
                function = call.child_by_field_name("function")
                line = call.start_point[0] + 1
                if function is None:
                    continue
                if function.type == "member_expression":
                    obj = function.child_by_field_name("object")
                    prop = self._text(function.child_by_field_name("property"))
                    if obj is not None and obj.type == "this" and prop in self.members:
                        self._add_relationship(member_id, self.members[prop], line, True)
                    elif obj is not None and obj.type == "identifier":
                        self._add_name_edge(member_id, self._text(obj), line)
                elif function.type == "identifier":
                    self._add_name_edge(member_id, self._text(function), line)

    def _add_name_edge(self, caller_id: str, name: str, line: int) -> None:
        if name in self.members:
            self._add_relationship(caller_id, self.members[name], line, True)
        elif name in self.script_names:
            self._add_relationship(caller_id, self.script_names[name], line, True)
        elif name in self.imports:
            target = self.imports[name]
            self._add_relationship(caller_id, target, line, _is_sfc(target))

    def _extract_template_edges(self, template: _SfcBlock) -> None:
        pascal_imports = {pascal_case(local): target for local, target in self.imports.items()}
        content = self.content
        line_starts = [0]
        line_starts.extend(match.end() for match in re.finditer("\n", content))
        position = template.start
        while position < template.end:
            tag, position = _next_tag(content, position)
            if tag is None or tag.start >= template.end:
                break
            if not tag.closing:
                line = bisect_right(line_starts, tag.start)
                if self._is_component_tag(tag.name):
                    name = pascal_case(tag.name)
                    target = pascal_imports.get(name, name)
                    self._add_relationship(self.component_id, target, line, _is_sfc(target))
                for attr_name, value in _attributes(tag.attributes).items():
                    if attr_name.startswith(("@", ":", "v-", "#")):
                        self._expression_edges(value, line)
            if position > template.end:
                break

        for match in _INTERPOLATION_RE.finditer(content, template.start, template.end):
            line = bisect_right(line_starts, match.start())
            self._expression_edges(match.group(1), line)

    @staticmethod
    def _is_component_tag(tag: str) -> bool:
        if not tag or tag.lower() in _BUILTIN_TAGS:
            return False
        return "-" in tag or tag[0].isupper()

    def _expression_edges(self, expression: str, line: int) -> None:
        for name in _IDENT_RE.findall(expression):
            if name not in _JS_KEYWORDS:
                self._add_name_edge(self.component_id, name, line)

    def _add_component_node(self, lines: list[str]) -> None:
        self.nodes.append(
            Node(
                id=self.component_id,
                name=self.component_name,
                component_type="class",
                file_path=str(self.file_path),
                relative_path=self.relative_path,
                source_code=self.content,
                start_line=1,
                end_line=max(len(lines), 1),
                node_type="component",
                display_name=f"Vue component {self.component_name}",
                component_id=self.component_id,
                language="vue",
            )
        )

    @staticmethod
    def _descendants(node, node_type: str):
        stack = list(node.children)
        while stack:
            current = stack.pop()
            if current.type == node_type:
                yield current
            stack.extend(current.children)

    def _add_relationship(self, caller: str, callee: str, line: int, resolved: bool) -> None:
        if not callee or caller == callee:
            return
        key = (caller, callee)
        if key in self.seen_relationships:
            return
        self.seen_relationships.add(key)
        self.call_relationships.append(
            CallRelationship(
                caller=caller,
                callee=callee,
                call_line=line,
                is_resolved=resolved,
            )
        )


def analyze_vue_file(
    file_path: str, content: str, repo_path: str | None = None
) -> tuple[list[Node], list[CallRelationship]]:
    """分析一个 Vue SFC，返回组件节点与调用/引用关系。"""
    analyzer = VueSfcAnalyzer(file_path, content, repo_path)
    return analyzer.nodes, analyzer.call_relationships
