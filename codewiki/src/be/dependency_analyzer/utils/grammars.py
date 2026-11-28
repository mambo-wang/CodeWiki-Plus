"""语言 grammar 的一次性预检与 parser 构造。

独立 grammar wheel 不包含运行时下载，但依赖缺失、二进制不兼容或 ABI
变化仍会让 parser 初始化失败。必须在逐文件分析前显式失败，避免被语言
分析器内部的 ``except Exception`` 吞成“这个文件没有组件”。
"""

from functools import lru_cache
from importlib import import_module
from typing import Iterable

from tree_sitter import Language, Parser

_GRAMMAR_MODULES = {
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "rust": "tree_sitter_rust",
    "ruby": "tree_sitter_ruby",
    "go": "tree_sitter_go",
    "scala": "tree_sitter_scala",
    "dart": "tree_sitter_dart",
    "zig": "tree_sitter_zig",
    "lean": "tree_sitter_lean",
}


class GrammarUnavailableError(RuntimeError):
    """请求语言的 grammar 无法加载。"""

    def __init__(self, language: str, cause: Exception):
        module = _GRAMMAR_MODULES.get(language, f"tree-sitter-{language}")
        package = module.replace("_", "-")
        if language == "lean":
            message = (
                f"无法加载 {language!r} 的 tree-sitter grammar（{cause}）。"
                "Lean 使用随包分发的离线 native 资产；请确认当前平台资产完整且与"
                " tree-sitter ABI 兼容，不要静默跳过该语言。"
            )
        else:
            message = (
                f"无法加载 {language!r} 的 tree-sitter grammar（{cause}）。"
                f"请确认依赖 {package!r} 已安装且与当前 tree-sitter ABI 兼容；"
                "离线环境应在构建或安装阶段准备好对应 wheel，不要静默跳过该语言。"
            )
        super().__init__(message)
        self.language = language


def _load_language(language: str) -> Language:
    if language == "lean":
        from codewiki.src.be.dependency_analyzer.analyzers.lean_grammar import (
            load_lean_language,
        )

        return load_lean_language()
    module_name = _GRAMMAR_MODULES[language]
    module = import_module(module_name)
    if language == "typescript":
        return Language(module.language_typescript())
    return Language(module.language())


@lru_cache(maxsize=None)
def get_language(language: str) -> Language:
    """加载并缓存不可变的 grammar Language 对象。"""
    try:
        return _load_language(language)
    except Exception as exc:
        raise GrammarUnavailableError(language, exc) from exc


def get_parser(language: str):
    """为单次文件分析创建独立 parser，避免跨线程共享可变解析器。"""
    try:
        return Parser(get_language(language))
    except GrammarUnavailableError:
        raise
    except Exception as exc:
        raise GrammarUnavailableError(language, exc) from exc


def ensure_grammars(languages: Iterable[str]) -> None:
    """在解析任何文件前加载所需 grammar；未知语言保持原有分派行为。"""
    for language in sorted(set(languages)):
        required = {"javascript", "typescript"} if language == "vue" else {language}
        for target in sorted(required):
            if target in _GRAMMAR_MODULES:
                get_parser(target)
