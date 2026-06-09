"""External API symbols that should not count as unresolved project edges."""

from __future__ import annotations

from pathlib import Path


C_EXTERNAL_SYMBOLS = {
    "abort",
    "atexit",
    "calloc",
    "exit",
    "fclose",
    "fopen",
    "fprintf",
    "ftruncate",
    "fread",
    "free",
    "fwrite",
    "getline",
    "ioctl",
    "isatty",
    "isdigit",
    "isprint",
    "isspace",
    "malloc",
    "memcmp",
    "memcpy",
    "memmove",
    "memset",
    "open",
    "perror",
    "printf",
    "read",
    "realloc",
    "scanf",
    "snprintf",
    "sscanf",
    "strcat",
    "strchr",
    "strerror",
    "strcmp",
    "strcpy",
    "strlen",
    "strstr",
    "tcgetattr",
    "tcsetattr",
    "time",
    "close",
    "signal",
    "va_end",
    "va_start",
    "vsnprintf",
    "write",
}


# C++ standard-library symbols: STL container member functions and core std::
# types. These are language-level knowledge (true for any C++ project), not
# specific to any one repository. Library-specific names are intentionally
# excluded — those are filtered per-repo via include-derived externals so we
# never suppress a project's own types by accident.
CPP_EXTERNAL_SYMBOLS = C_EXTERNAL_SYMBOLS | {
    "basic_string",
    "begin",
    "cin",
    "cout",
    "c_str",
    "data",
    "delete",
    "endl",
    "empty",
    "end",
    "exception",
    "forward",
    "function",
    "initializer_list",
    "make_shared",
    "make_unique",
    "move",
    "new",
    "optional",
    "pair",
    "push_back",
    "shared_ptr",
    "size",
    "static_assert",
    "std",
    "string",
    "string_view",
    "tuple",
    "unique_ptr",
    "vector",
}


# Core JDK types from java.lang (auto-imported, so they appear unqualified with
# no import statement to derive them from) plus the most common java.util
# collection interfaces. Types reached through an explicit import (e.g.
# javax.tools.JavaFileObject) are NOT listed here — they are filtered per-repo
# via the import map, which keeps this list free of project-specific entries.
JAVA_EXTERNAL_SYMBOLS = {
    "Appendable",
    "AssertionError",
    "Cloneable",
    "Comparable",
    "Exception",
    "IllegalArgumentException",
    "IllegalStateException",
    "Iterable",
    "Iterator",
    "NullPointerException",
    "Object",
    "RuntimeException",
    "String",
    "StringBuilder",
    "UnsupportedOperationException",
}


CPP_STANDARD_HEADERS = {
    "algorithm",
    "array",
    "chrono",
    "cmath",
    "cstdint",
    "cstdio",
    "cstdlib",
    "cstring",
    "exception",
    "functional",
    "initializer_list",
    "iostream",
    "limits",
    "map",
    "memory",
    "optional",
    "ostream",
    "sstream",
    "stdexcept",
    "string",
    "string_view",
    "tuple",
    "type_traits",
    "utility",
    "vector",
}


def normalize_symbol(symbol: str) -> str:
    """Return a comparable symbol name from an ID, qualified name, or call target."""
    if not symbol:
        return ""
    normalized = symbol.strip()
    if "::" in normalized and not normalized.startswith("std::"):
        normalized = normalized.split("::")[-1]
    normalized = normalized.split("(")[0]
    normalized = normalized.strip("&*[] ")
    if "." in normalized:
        normalized = normalized.split(".")[-1]
    if "::" in normalized:
        normalized = normalized.split("::")[-1]
    return normalized


def is_external_symbol(
    language: str | None,
    symbol: str,
    derived_externals: "set[str] | None" = None,
) -> bool:
    """Check whether a callee is a known external/runtime symbol.

    Classification is layered, from most general to most specific:
      1. Namespace prefix rules (``java.``/``javax.``/``std::``/...), which hold
         for any project regardless of which third-party libraries it uses.
      2. ``derived_externals`` — names the caller resolved to an external origin
         for *this* repository (e.g. types reached through a non-project import,
         or symbols from a system ``#include``). This is how library-specific
         externals are filtered without hardcoding them here.
      3. The curated language standard-library sets, which encode only true
         language-level knowledge (libc, STL members, core JDK types).
    """
    if not symbol:
        return False

    normalized = normalize_symbol(symbol)
    if symbol.startswith(("java.", "javax.", "jdk.", "sun.")):
        return True
    if symbol.startswith("std::"):
        return True
    if Path(symbol).suffix:
        normalized = normalize_symbol(Path(symbol).stem)

    if derived_externals and (symbol in derived_externals or normalized in derived_externals):
        return True

    if language == "java":
        return normalized in JAVA_EXTERNAL_SYMBOLS
    if language == "cpp":
        return normalized in CPP_EXTERNAL_SYMBOLS
    if language == "c":
        return normalized in C_EXTERNAL_SYMBOLS
    return False
