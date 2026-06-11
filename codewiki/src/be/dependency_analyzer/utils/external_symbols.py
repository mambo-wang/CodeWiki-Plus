"""External API symbols that should not count as unresolved project edges."""

from __future__ import annotations

import re


C_EXTERNAL_SYMBOLS = {
    "abort",
    "abs",
    "asctime",
    "assert",
    "atof",
    "atoi",
    "atol",
    "bsearch",
    "clock",
    "ctime",
    "difftime",
    "fabs",
    "feof",
    "ferror",
    "fflush",
    "fgetc",
    "fgets",
    "fputc",
    "fputs",
    "fseek",
    "ftell",
    "getc",
    "getchar",
    "getenv",
    "gmtime",
    "isalnum",
    "isalpha",
    "iscntrl",
    "islower",
    "ispunct",
    "isupper",
    "isxdigit",
    "localtime",
    "longjmp",
    "memchr",
    "mktime",
    "putc",
    "putchar",
    "puts",
    "qsort",
    "rand",
    "remove",
    "rename",
    "rewind",
    "setjmp",
    "sprintf",
    "srand",
    "strdup",
    "strftime",
    "strncat",
    "strncmp",
    "strncpy",
    "strrchr",
    "strtod",
    "strtol",
    "strtoul",
    "system",
    "tolower",
    "toupper",
    "ungetc",
    "va_arg",
    "va_copy",
    "vfprintf",
    "vprintf",
    "vsprintf",
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
    "at",
    "append",
    "back",
    "basic_string",
    "begin",
    "capacity",
    "cbegin",
    "cend",
    "cin",
    "clear",
    "contains",
    "count",
    "cout",
    "c_str",
    "data",
    "delete",
    "find",
    "emplace",
    "emplace_back",
    "endl",
    "empty",
    "end",
    "erase",
    "exception",
    "forward",
    "front",
    "function",
    "initializer_list",
    "insert",
    "length",
    "lower_bound",
    "make_pair",
    "make_shared",
    "make_tuple",
    "make_unique",
    "move",
    "new",
    "optional",
    "pair",
    "pop_back",
    "pop_front",
    "push_back",
    "push_front",
    "rbegin",
    "rend",
    "reserve",
    "resize",
    "shared_ptr",
    "shrink_to_fit",
    "size",
    "static_assert",
    "std",
    "string",
    "string_view",
    "substr",
    "swap",
    "tuple",
    "unique_ptr",
    "upper_bound",
    "vector",
    "what",
}


# Types from java.lang, which are auto-imported and therefore appear
# unqualified with no import statement to derive them from. This is a closed,
# language-level set (no java.util/javax types here — those require an import
# and are filtered per-repo through the import map and wildcard imports).
JAVA_EXTERNAL_SYMBOLS = {
    # Core classes and interfaces
    "Appendable",
    "AutoCloseable",
    "Boolean",
    "Byte",
    "Character",
    "CharSequence",
    "Class",
    "ClassLoader",
    "Cloneable",
    "Comparable",
    "Double",
    "Enum",
    "Float",
    "Integer",
    "Iterable",
    "Long",
    "Math",
    "Module",
    "Number",
    "Object",
    "Package",
    "Process",
    "ProcessBuilder",
    "Readable",
    "Record",
    "Runnable",
    "Runtime",
    "Short",
    "StackTraceElement",
    "StrictMath",
    "String",
    "StringBuffer",
    "StringBuilder",
    "System",
    "Thread",
    "ThreadGroup",
    "ThreadLocal",
    "Void",
    # Throwables
    "ArithmeticException",
    "ArrayIndexOutOfBoundsException",
    "ArrayStoreException",
    "AssertionError",
    "ClassCastException",
    "ClassNotFoundException",
    "CloneNotSupportedException",
    "Error",
    "Exception",
    "IllegalAccessException",
    "IllegalArgumentException",
    "IllegalStateException",
    "IndexOutOfBoundsException",
    "InstantiationException",
    "InterruptedException",
    "LinkageError",
    "NegativeArraySizeException",
    "NoClassDefFoundError",
    "NoSuchFieldException",
    "NoSuchMethodException",
    "NullPointerException",
    "NumberFormatException",
    "OutOfMemoryError",
    "ReflectiveOperationException",
    "RuntimeException",
    "SecurityException",
    "StackOverflowError",
    "StringIndexOutOfBoundsException",
    "Throwable",
    "UnsupportedOperationException",
    "VirtualMachineError",
    # Annotations
    "Deprecated",
    "FunctionalInterface",
    "Override",
    "SafeVarargs",
    "SuppressWarnings",
}


# Methods every Java object inherits from java.lang.Object. A call to one of
# these on a project type that does not override it locally can never resolve
# to a project component, so analyzers skip emitting it as a project edge.
JAVA_OBJECT_METHODS = {
    "clone",
    "equals",
    "finalize",
    "getClass",
    "hashCode",
    "notify",
    "notifyAll",
    "toString",
    "wait",
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


# ALL_CAPS tokens that are common standard constants/keywords, not macros.
NON_MACRO_UPPER = {
    "FALSE",
    "TRUE",
    "NULL",
    "EOF",
    "EXIT_SUCCESS",
    "EXIT_FAILURE",
}

_ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def is_macro_name(token: str) -> bool:
    """Heuristic: an ALL_CAPS identifier (with an underscore or 4+ chars) reads
    as a macro by C/C++ naming convention, not a function or type. Macros are
    never extracted as components, so a call to one can never resolve to a
    project function. This is consulted only after project resolution has had
    its chance, so a genuine ALL_CAPS project component still matches first."""
    if not token or not _ALL_CAPS_RE.match(token):
        return False
    return (len(token) >= 4 or "_" in token) and token not in NON_MACRO_UPPER


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


def is_external_symbol(language: str | None, symbol: str) -> bool:
    """Check whether a callee is a known external/runtime symbol.

    Classification is layered, from most general to most specific:
      1. Namespace prefix rules (``java.``/``javax.``/``std::``/...), which hold
         for any project regardless of which third-party libraries it uses.
      2. The curated language standard-library sets, which encode only true
         language-level knowledge (libc, STL members, java.lang types).

    A dotted Java name that survives the prefix rules is qualified to some
    non-JDK package; whether that package belongs to the project is decided by
    the resolver's project-package check, not by simple-name matching here.
    """
    if not symbol:
        return False

    if symbol.startswith(("java.", "javax.", "jdk.", "sun.")):
        return True
    if symbol.startswith("std::"):
        return True

    if language == "java":
        if "." in symbol:
            return False
        return symbol in JAVA_EXTERNAL_SYMBOLS

    normalized = normalize_symbol(symbol)
    if language == "cpp":
        return normalized in CPP_EXTERNAL_SYMBOLS
    if language == "c":
        return normalized in C_EXTERNAL_SYMBOLS
    return False
