"""Lean 4 Tree-sitter grammar 的离线加载器。

PyPI 目前没有独立的 ``tree-sitter-lean`` wheel，language-pack 的 Lean
parser 又会在首次使用时联网下载。这里固定携带 language-pack v1.14.3
release 中六平台的 Lean parser 二进制，只加载当前平台的一份，不访问网络。
"""

from __future__ import annotations

import ctypes
import platform
import sys
from pathlib import Path
from threading import Lock

from tree_sitter import Language

_LOCK = Lock()
_LIBRARY: ctypes.CDLL | None = None
_LANGUAGE: Language | None = None

_VENDOR_ROOT = Path(__file__).parent / "_vendor" / "lean"
_LIBRARY_NAMES = {
    "linux": "libtree_sitter_lean.so",
    "darwin": "libtree_sitter_lean.dylib",
    "win32": "tree_sitter_lean.dll",
}


def _platform_key() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        arch = "aarch64" if sys.platform.startswith("linux") else "arm64"
    elif machine in {"x86_64", "amd64"}:
        arch = "x86_64"
    else:
        arch = machine
    system = (
        "windows"
        if sys.platform == "win32"
        else "macos"
        if sys.platform == "darwin"
        else sys.platform
    )
    return f"{system}-{arch}"


def _library_path() -> Path:
    system = sys.platform
    if system.startswith("linux"):
        system = "linux"
    filename = _LIBRARY_NAMES.get(system)
    if filename is None:
        raise RuntimeError(f"Lean grammar 不支持平台 {sys.platform!r}")
    path = _VENDOR_ROOT / _platform_key() / filename
    if not path.is_file():
        raise RuntimeError(f"Lean grammar 缺少当前平台资产：{path}")
    return path


def _language_from_library(path: Path) -> Language:
    global _LIBRARY
    library = ctypes.CDLL(str(path))
    try:
        symbol = getattr(library, "tree_sitter_lean")
    except AttributeError as exc:
        raise RuntimeError(f"Lean grammar 缺少 tree_sitter_lean 导出符号：{path}") from exc
    symbol.restype = ctypes.c_void_p
    symbol.argtypes = []
    address = symbol()
    if not address:
        raise RuntimeError(f"Lean grammar 返回空语言指针：{path}")

    # py-tree-sitter 0.25+ 的 Language 只接受名为 tree_sitter.Language 的
    # PyCapsule；grammar 库由 _LIBRARY 持有，capsule 不负责释放该指针。
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    capsule_new.restype = ctypes.py_object
    capsule = capsule_new(ctypes.c_void_p(address), b"tree_sitter.Language", None)
    language = Language(capsule)
    if language.name != "lean":
        raise RuntimeError(f"Lean grammar 名称不匹配：{language.name!r}")
    _LIBRARY = library
    return language


def load_lean_language() -> Language:
    """加载并缓存当前平台的 Lean grammar，不触发任何下载。"""
    global _LANGUAGE
    if _LANGUAGE is not None:
        return _LANGUAGE
    with _LOCK:
        if _LANGUAGE is None:
            _LANGUAGE = _language_from_library(_library_path())
    return _LANGUAGE
