"""Go analyzer package identity, repository imports and interface method sets."""

from __future__ import annotations

import os
import posixpath
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from codewiki.src.be.dependency_analyzer.models.core import CallRelationship, Node

_PACKAGE_REF_FILES = "*.go"
_MODULE_RE = re.compile(r"^\s*module\s+\"?([^\s\"]+)\"?", re.MULTILINE)
_REPLACE_RE = re.compile(r"^\s*(?:replace\s+)?\"?([^\s\"(]+)\"?(?:\s+\S+)?\s*=>\s*\"?([^\s\"]+)")
_PACKAGE_CLAUSE_RE = re.compile(r"^\s*package\s+([A-Za-z_]\w*)", re.MULTILINE)
_MAJOR_VERSION_RE = re.compile(r"^v\d+$")


def go_package_ref(package_dir: str, name: str) -> str:
    """Reference a declaration in a directory-scoped Go package."""
    prefix = f"{package_dir}/" if package_dir else ""
    return f"{prefix}{_PACKAGE_REF_FILES}::{name}"


def split_go_package_ref(callee: str) -> tuple[str, str] | None:
    head, separator, name = callee.partition("::")
    if not separator or not name:
        return None
    if head == _PACKAGE_REF_FILES:
        return "", name
    suffix = f"/{_PACKAGE_REF_FILES}"
    if head.endswith(suffix):
        return head[: -len(suffix)], name
    return None


def package_dir_of(relative_path: str) -> str:
    return posixpath.dirname(Path(relative_path).as_posix())


def package_name_of(relative_path: str) -> str:
    """Human-facing package identity without changing component IDs."""
    directory = package_dir_of(relative_path)
    filename = Path(relative_path).name
    return directory or filename.removesuffix(".go")


@lru_cache(maxsize=256)
def _parse_go_mod(path: str, mtime_ns: int) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    del mtime_ns  # The mtime is part of the cache key only.
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, ()
    module_match = _MODULE_RE.search(text)
    module = module_match.group(1) if module_match else None
    replaces: list[tuple[str, str]] = []
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line.startswith("replace") and line.rstrip().endswith("("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if not (in_block or line.startswith("replace")):
            continue
        match = _REPLACE_RE.match(line)
        if match and match.group(2).startswith(("./", "../")):
            replaces.append((match.group(1), match.group(2)))
    return module, tuple(replaces)


def _read_go_mod(path: str) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    try:
        mtime_ns = os.stat(path).st_mtime_ns
    except OSError:
        return None, ()
    return _parse_go_mod(path, mtime_ns)


def _normalize_dir(path: str) -> str | None:
    normalized = posixpath.normpath(path)
    if normalized == ".":
        return ""
    if normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


@lru_cache(maxsize=1024)
def _package_name_in_dir(abs_dir: str, signature: tuple[tuple[str, int], ...]) -> str | None:
    del signature  # File mtimes are part of the cache key only.
    try:
        names = sorted(os.listdir(abs_dir))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".go") or name.endswith("_test.go"):
            continue
        try:
            head = Path(abs_dir, name).read_text(encoding="utf-8", errors="replace")[:8192]
        except OSError:
            continue
        match = _PACKAGE_CLAUSE_RE.search(re.sub(r"//[^\n]*", "", head))
        if match:
            return match.group(1)
    return None


def _package_dir_signature(abs_dir: str) -> tuple[tuple[str, int], ...]:
    try:
        names = sorted(os.listdir(abs_dir))
    except OSError:
        return ()
    signature: list[tuple[str, int]] = []
    for name in names:
        if not name.endswith(".go") or name.endswith("_test.go"):
            continue
        try:
            signature.append((name, os.stat(os.path.join(abs_dir, name)).st_mtime_ns))
        except OSError:
            continue
    return tuple(signature)


def _default_import_names(import_path: str) -> set[str]:
    parts = [part for part in import_path.split("/") if part]
    if not parts:
        return set()
    last = parts[-1]
    if _MAJOR_VERSION_RE.match(last) and len(parts) > 1:
        last = parts[-2]
    last = re.sub(r"\.v\d+$", "", last)
    names = {last}
    for prefix in ("go-", "go."):
        if last.startswith(prefix):
            names.add(last[len(prefix) :])
    for suffix in ("-go", ".go"):
        if last.endswith(suffix):
            names.add(last[: -len(suffix)])
    names |= {name.replace("-", "") for name in names}
    names |= {name.replace("-", "_") for name in names}
    return {name for name in names if name.isidentifier()}


def resolve_repository_import(import_path: str, package_dir: str, repo_path: str) -> str | None:
    """Map an import to a repository directory via go.mod/local replace.

    Without go.mod, a GOPATH-style suffix is accepted only when it names an
    existing repository directory. Standard-library imports never qualify.
    """
    if not repo_path:
        return None
    directory = package_dir
    while True:
        go_mod = posixpath.join(repo_path.replace(os.sep, "/"), directory, "go.mod")
        if os.path.isfile(go_mod):
            module, replaces = _read_go_mod(go_mod)
            targets = ([(module, "")] if module else []) + list(replaces)
            for prefix, local in targets:
                if import_path == prefix or import_path.startswith(prefix + "/"):
                    rest = import_path[len(prefix) :].lstrip("/")
                    return _normalize_dir(posixpath.join(directory, local, rest))
            return None
        if not directory:
            break
        directory = posixpath.dirname(directory)

    parts = import_path.split("/")
    if len(parts) < 2 or "." not in parts[0]:
        return None
    for start in range(1, len(parts)):
        candidate = "/".join(parts[start:])
        if os.path.isdir(os.path.join(repo_path, candidate)):
            return candidate
    return None


def default_import_names(import_path: str) -> set[str]:
    return _default_import_names(import_path)


def package_name_in_dir(abs_dir: str) -> str | None:
    return _package_name_in_dir(abs_dir, _package_dir_signature(abs_dir))


def is_skipped_go_file(relative_path: str) -> bool:
    """Generated tests and vendored dependencies are not project components."""
    posix = Path(relative_path).as_posix()
    return posix.endswith("_test.go") or "vendor" in posix.split("/")[:-1]


class GoPackageIndex:
    """Repository-wide Go declarations grouped by directory-scoped package."""

    def __init__(self, functions: dict[str, Node]):
        self.functions = functions
        self.by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.methods: dict[tuple[str, str], list[str]] = defaultdict(list)
        for func_id, node in functions.items():
            if node.language != "go":
                continue
            directory = package_dir_of(node.relative_path)
            if node.component_type == "method" and node.class_name:
                self.methods[(directory, node.name.rsplit(".", 1)[-1])].append(func_id)
            else:
                self.by_name[(directory, node.name)].append(func_id)
        for ids in (*self.by_name.values(), *self.methods.values()):
            ids.sort()

    def lookup(self, directory: str, name: str, depth: int = 0) -> str | None:
        if "." not in name:
            ids = self.by_name.get((directory, name))
            return ids[0] if ids and len(ids) == 1 else None
        if depth >= 3:
            return None
        owner, method = name.split(".", 1)
        owned = [
            func_id
            for func_id in self.methods.get((directory, method), [])
            if self.functions[func_id].class_name == owner
        ]
        if len(owned) == 1:
            return owned[0]
        for owner_id in self.by_name.get((directory, owner), []):
            for base in self.functions[owner_id].base_classes or []:
                if "." in base:
                    continue
                found = self.lookup(directory, f"{base}.{method}", depth + 1)
                if found:
                    return found
        return None


def resolve_go_callee(
    callee: str,
    caller: Node,
    index: GoPackageIndex,
    visible_dirs: set[str] | None,
) -> str | None:
    reference = split_go_package_ref(callee)
    if reference is not None:
        return index.lookup(*reference)
    if "::" in callee or "." in callee:
        return None
    directories = visible_dirs or {package_dir_of(caller.relative_path)}
    candidates = sorted(
        {
            func_id
            for directory in directories
            for func_id in index.methods.get((directory, callee), [])
        }
    )
    return candidates[0] if len(candidates) == 1 else None


def link_go_interfaces(functions: dict[str, Node]) -> list[CallRelationship]:
    """Link concrete package types to interfaces they implement implicitly."""
    types: dict[str, dict[str, Node]] = defaultdict(dict)
    method_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for node in functions.values():
        if node.language != "go":
            continue
        directory = package_dir_of(node.relative_path)
        if node.component_type == "method" and node.class_name:
            method_sets[(directory, node.class_name)].add(node.name.rsplit(".", 1)[-1])
        elif node.node_type in ("struct", "interface", "type"):
            types[directory][node.name] = node

    relationships: list[CallRelationship] = []
    for directory, by_name in types.items():
        interfaces = [
            (interface, methods)
            for interface in by_name.values()
            if interface.node_type == "interface"
            if (methods := method_sets.get((directory, interface.name)))
        ]
        if not interfaces:
            continue
        for type_node in by_name.values():
            if type_node.node_type == "interface":
                continue
            own_methods = method_sets.get((directory, type_node.name))
            if not own_methods:
                continue
            for interface, required_methods in interfaces:
                if required_methods <= own_methods:
                    bases = type_node.base_classes or []
                    if interface.name not in bases:
                        type_node.base_classes = [*bases, interface.name]
                    relationships.append(
                        CallRelationship(
                            caller=type_node.id,
                            callee=interface.id,
                            call_line=type_node.start_line,
                            is_resolved=True,
                        )
                    )
    return relationships
