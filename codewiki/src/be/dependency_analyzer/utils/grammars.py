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
    "rust": "tree_sitter_rust",
    "ruby": "tree_sitter_ruby",
}


class GrammarUnavailableError(RuntimeError):
    """请求语言的 grammar 无法加载。"""

    def __init__(self, language: str, cause: Exception):
        module = _GRAMMAR_MODULES.get(language, f"tree-sitter-{language}")
        package = module.replace("_", "-")
        super().__init__(
            f"无法加载 {language!r} 的 tree-sitter grammar（{cause}）。"
            f"请确认依赖 {package!r} 已安装且与当前 tree-sitter ABI 兼容；"
            "离线环境应在构建或安装阶段准备好对应 wheel，不要静默跳过该语言。"
        )
        self.language = language


def _load_language(language: str) -> Language:
    module_name = _GRAMMAR_MODULES[language]
    module = import_module(module_name)
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
        if language in _GRAMMAR_MODULES:
            get_parser(language)
