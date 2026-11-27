"""Deterministic facts for build, CI, container, manifest, schema and script files.

This is deliberately a fact layer, not a second dependency graph. Artifact IDs
live in their own namespace and never enter the source component store.
"""

from __future__ import annotations

import configparser
import errno
import fnmatch
import hashlib
import json
import os
import re
import shlex
import stat
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from codewiki.mcp.cache import analysis_meta_dir
from codewiki.src.be.dependency_analyzer.analysis.repo_analyzer import (
    GitIgnoreFilter,
    RepositoryBoundaryFilter,
)

ARTIFACT_FACTS_FILENAME = "artifact_facts.json"
ARTIFACT_SCHEMA_VERSION = 1

_KIND_PRIORITY = {
    "manifest": 0,
    "ci": 1,
    "container": 2,
    "build": 3,
    "schema": 4,
    "script": 5,
}
_DROP_SEGMENTS = {
    ".git",
    ".codewiki",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "fixtures",
    "node_modules",
    ".lake",
    "lake-packages",
    "repowiki",
    "snapshots",
    "testdata",
    "third_party",
    "vendor",
    "venv",
}
_LOCKFILES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "pipfile.lock",
    "uv.lock",
    "cargo.lock",
    "go.sum",
    "composer.lock",
    "gemfile.lock",
}
_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "build.sbt",
    "pubspec.yaml",
    "lakefile.toml",
    "lake-manifest.json",
    "lean-toolchain",
    "gemfile",
    "composer.json",
}
_BUILD_NAMES = {
    "makefile",
    "gnumakefile",
    "build",
    "workspace",
    "build.bazel",
    "build.zig",
    "lakefile.lean",
}
_SCHEMA_EXTS = {".proto", ".graphql", ".thrift"}
_SCRIPT_EXTS = {".sh", ".bash", ".zsh", ".fish", ".ps1"}
_SOURCE_EXTS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lean",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sc",
    ".dart",
    ".zig",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sh",
}
_PATH_REF_RE = re.compile(
    r"(?<![\w./-])(?:\./)?(?:[\w.-]+/)*[\w.-]+(?:"
    + "|".join(
        re.escape(ext) for ext in sorted(_SOURCE_EXTS - {".json", ".yaml", ".yml", ".toml", ".sh"})
    )
    + r")\b",
    re.IGNORECASE,
)
_PY_MODULE_RE = re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+-m\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
_MAKE_REF_RE = re.compile(r"\bmake\s+(?:-C\s+\S+\s+)?([A-Za-z_][\w.-]*)")
_NPM_REF_RE = re.compile(r"\bnpm\s+run\s+([\w:.-]+)")
_ARTIFACT_REF_RE = re.compile(
    r"(?<![\w./-])(Dockerfile(?:\.[\w-]+)?|Containerfile|Makefile|makefile|"
    r"package\.json|pyproject\.toml|compose(?:\.[\w-]+)?\.ya?ml)\b"
)
_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


@dataclass(frozen=True)
class ArtifactFactOptions:
    """Hard limits for one collection pass.

    ``max_files`` limits parsing, not discovery. Every discovered candidate is
    still fingerprinted so additions/deletions remain visible when a cap is hit.
    """

    max_files: int = 250
    max_file_bytes: int = 65_536
    max_units_per_file: int = 100
    max_facts: int = 2_000
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_files < 0 or self.max_units_per_file < 0 or self.max_facts < 1:
            raise ValueError("artifact limits must be non-negative and max_facts must be positive")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")


class ArtifactParseError(ValueError):
    def __init__(self, code: str, *, line: int | None = None, column: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.line = line
        self.column = column


def artifact_facts_path(repo_path: str | Path, output_dir: str | Path) -> Path:
    """Return the per-repo artifact fact path, including centralized layouts."""

    return analysis_meta_dir(Path(repo_path), Path(output_dir)) / ARTIFACT_FACTS_FILENAME


def unavailable_artifact_facts(error_type: str) -> dict[str, Any]:
    """Return the explicit fail-open shape used when collection cannot start."""

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": "unavailable",
        "summary": {
            "files_scanned": 0,
            "files_parsed": 0,
            "files_failed": 0,
            "files_truncated": 0,
            "facts": 0,
            "facts_omitted": 0,
            "by_kind": {},
        },
        "facts": [],
        "files": [],
        "omitted_files": [],
        "fingerprints": {},
        "changed_files": [],
        "warnings": [f"collection_failed:{error_type}"],
        "limits": {},
    }


def classify_artifact(rel_path: str, first_line: str | None = None) -> str | None:
    """Classify a repository-relative path without reading or executing it."""

    rel = rel_path.replace(os.sep, "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.startswith("../") or rel.startswith("/"):
        return None
    parts = rel.split("/")
    name = parts[-1]
    lower = name.lower()
    top = parts[0].lower() if len(parts) > 1 else ""
    if lower in _LOCKFILES or any(part.lower() in _DROP_SEGMENTS for part in parts[:-1]):
        return None
    if lower in {"codeowners", "funding.yml", ".env"} or lower.startswith(
        (".env.", "credentials.", "secrets.")
    ):
        return None
    if lower.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")):
        return None

    if (
        (rel.startswith(".github/workflows/") and lower.endswith((".yml", ".yaml")))
        or lower
        in {".gitlab-ci.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml", "jenkinsfile"}
        or (top in {".circleci", ".buildkite"} and lower.endswith((".yml", ".yaml")))
        or (rel.startswith(".github/actions/") and lower in {"action.yml", "action.yaml"})
    ):
        return "ci"
    if (
        lower == "containerfile"
        or lower.startswith("dockerfile")
        or lower.endswith(".dockerfile")
        or re.fullmatch(r"(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml", lower)
    ):
        return "container"
    if lower in _MANIFEST_NAMES or re.fullmatch(r"requirements-[\w.-]+\.txt", lower):
        return "manifest"
    if lower in _BUILD_NAMES or lower in {"build.xml", "build.gn"}:
        return "build"
    if (
        Path(lower).suffix in _SCHEMA_EXTS
        or lower.startswith(("openapi.", "swagger."))
        or lower.endswith((".schema.json", ".schema.yml", ".schema.yaml"))
        or (top in {"schema", "schemas", "api"} and lower.endswith((".json", ".yml", ".yaml")))
    ):
        return "schema"
    if Path(lower).suffix in _SCRIPT_EXTS:
        return "script"
    if not Path(lower).suffix and top in {"bin", "scripts"} and (first_line or "").startswith("#!"):
        return "script"
    return None


def _matches_patterns(rel_path: str, patterns: Iterable[str]) -> bool:
    name = Path(rel_path).name
    parts = rel_path.split("/")
    for raw in patterns:
        pattern = raw.strip().replace("\\", "/")
        if not pattern:
            continue
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.endswith("/") and rel_path.startswith(pattern.rstrip("/")):
            return True
        if rel_path.startswith(pattern.rstrip("/") + "/") or rel_path == pattern:
            return True
        if pattern.rstrip("/") in parts[:-1]:
            return True
    return False


@contextmanager
def _open_regular_file(path: Path) -> Iterator[Any]:
    """Open only regular files, without blocking on FIFOs or device nodes."""

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(errno.EINVAL, "artifact is not a regular file", str(path))
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            yield handle
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _discover_candidates(repo_path: Path, options: ArtifactFactOptions) -> list[tuple[str, str]]:
    boundaries = RepositoryBoundaryFilter(repo_path)
    gitignore = GitIgnoreFilter(repo_path, boundaries)
    candidates: list[tuple[str, str]] = []

    def raise_walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, files in os.walk(repo_path, followlinks=False, onerror=raise_walk_error):
        base = Path(directory)
        kept_dirs: list[str] = []
        for name in sorted(dirs):
            child = base / name
            rel = child.relative_to(repo_path).as_posix()
            if (
                name.lower() in _DROP_SEGMENTS
                or child.is_symlink()
                or boundaries.should_skip(child)
                or gitignore.is_ignored(rel, is_dir=True)
                or _matches_patterns(rel, options.exclude_patterns)
            ):
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            path = base / name
            rel = path.relative_to(repo_path).as_posix()
            if path.is_symlink() or gitignore.is_ignored(rel, is_dir=False):
                continue
            if options.include_patterns and not _matches_patterns(rel, options.include_patterns):
                continue
            if _matches_patterns(rel, options.exclude_patterns):
                continue
            first_line = None
            if not path.suffix and Path(rel).parts[0] in {"bin", "scripts"}:
                try:
                    with _open_regular_file(path) as handle:
                        first_line = (
                            handle.read(256).decode("utf-8", errors="replace").split("\n", 1)[0]
                        )
                except OSError:
                    # Keep the path visible; the collection pass records the
                    # unreadable/non-regular failure instead of silently dropping it.
                    first_line = None
            kind = classify_artifact(rel, first_line)
            if kind or (
                not path.suffix and Path(rel).parts[0] in {"bin", "scripts"} and first_line is None
            ):
                candidates.append((rel, kind or "script"))
    return sorted(candidates, key=lambda item: (_KIND_PRIORITY[item[1]], item[0]))


def _read_head(path: Path, max_bytes: int) -> tuple[bytes, int, bool, str]:
    # Parse only a bounded prefix, but fingerprint the whole file so same-size
    # edits beyond the parse cap still trigger an incremental re-analysis.
    with _open_regular_file(path) as handle:
        data = handle.read(max_bytes + 1)
        digest = hashlib.sha256(data)
        total = len(data)
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
            total += len(chunk)
    truncated = total > max_bytes
    return data[:max_bytes], total, truncated, f"{total}:{digest.hexdigest()}"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _references(values: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    unique = {(str(item.get("kind", "")), str(item.get("value", ""))) for item in values}
    return [{"kind": kind, "value": value} for kind, value in sorted(unique) if kind and value]


def _extract_references(text: str) -> list[dict[str, str]]:
    normalized = text.replace("\\", "/")
    refs: list[Mapping[str, str]] = []
    refs.extend(
        {"kind": "path", "value": match.group(0).removeprefix("./")}
        for match in _PATH_REF_RE.finditer(normalized)
    )
    refs.extend(
        {"kind": "artifact", "value": match.group(0)} for match in _ARTIFACT_REF_RE.finditer(text)
    )
    refs.extend(
        {"kind": "module", "value": match.group(1)} for match in _PY_MODULE_RE.finditer(text)
    )
    refs.extend(
        {"kind": "make_target", "value": match.group(1)} for match in _MAKE_REF_RE.finditer(text)
    )
    refs.extend(
        {"kind": "npm_script", "value": match.group(1)} for match in _NPM_REF_RE.finditer(text)
    )
    return _references(refs)


def _fact(
    kind: str,
    path: str,
    name: str,
    line: int,
    *,
    attributes: Mapping[str, Any] | None = None,
    references: Iterable[Mapping[str, str]] = (),
) -> dict[str, Any]:
    return {
        "id": f"artifact:{kind}:{path}:{max(1, line)}:{name}",
        "kind": kind,
        "name": str(name),
        "path": path,
        "line": max(1, line),
        "attributes": _json_value(dict(attributes or {})),
        "references": _references(references),
    }


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _json_key_line(text: str, key: str, start: int = 0) -> int:
    match = re.search(rf'"{re.escape(key)}"\s*:', text[start:])
    return _line_of(text, start + match.start()) if match else 1


def _section_key_line(text: str, section: str, key: str) -> int:
    lines = text.splitlines()
    in_section = False
    section_line = 1
    key_pattern = re.compile(
        rf"^\s*(?:\"{re.escape(key)}\"|'{re.escape(key)}'|{re.escape(key)})\s*="
    )
    for number, line in enumerate(lines, start=1):
        header = re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
        if header:
            if in_section:
                break
            in_section = header.group(1).strip() == section
            if in_section:
                section_line = number
            continue
        if in_section and key_pattern.match(line):
            return number
    return section_line


def _load_yaml(text: str) -> tuple[Any, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - dependency is part of the project contract
        raise ArtifactParseError("yaml_unavailable") from exc
    try:
        data = yaml.safe_load(text)
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise ArtifactParseError(
            "invalid_yaml",
            line=(mark.line + 1 if mark is not None else None),
            column=(mark.column + 1 if mark is not None else None),
        ) from exc
    if not isinstance(data, dict) or node is None:
        raise ArtifactParseError("invalid_yaml_shape")
    return data, node


def _yaml_child(node: Any, key: str) -> tuple[Any, Any, int] | None:
    if not isinstance(getattr(node, "value", None), list):
        return None
    for key_node, value_node in node.value:
        if getattr(key_node, "value", None) == key:
            return value_node.value, value_node, key_node.start_mark.line + 1
    return None


def _ci_references(node: Any) -> list[dict[str, str]]:
    """Extract only bounded references from CI command fields, never their bodies."""

    actions: list[str] = []
    commands: list[str] = []

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key))
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str):
            if key == "uses":
                actions.append(item)
            elif key in {"run", "script", "command"}:
                commands.append(item)

    visit(node)
    refs: list[Mapping[str, str]] = []
    refs.extend({"kind": "action", "value": value} for value in actions)
    refs.extend(_extract_references("\n".join(commands)))
    return _references(refs)


def _ci_command_counts(node: Any) -> tuple[int, int]:
    steps = actions = 0

    def visit(item: Any, key: str | None = None) -> None:
        nonlocal steps, actions
        if isinstance(item, dict):
            for child_key, child in item.items():
                name = str(child_key)
                if name == "steps" and isinstance(child, list):
                    steps += len(child)
                if name == "uses" and isinstance(child, str):
                    actions += 1
                visit(child, name)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)

    visit(node)
    return steps, actions


def _parse_ci_provider(
    path: str, text: str, data: Mapping[str, Any], root: Any
) -> tuple[dict, list[dict]]:
    lower = path.lower()
    if lower.startswith(".github/actions/"):
        ci_type = "github_action"
        known = {"name", "description", "inputs", "outputs", "runs", "branding"}
        jobs: Mapping[str, Any] = {}
    elif lower.startswith(".circleci/"):
        ci_type = "circleci"
        known = {"version", "jobs", "executors", "commands", "orbs", "parameters"}
        jobs = dict(data["jobs"]) if isinstance(data.get("jobs"), dict) else {}
    elif lower.startswith(".buildkite/"):
        ci_type = "buildkite"
        known = {"steps", "agents", "env", "pipelines", "notify"}
        jobs = {}
    elif lower == ".gitlab-ci.yml":
        ci_type = "gitlab"
        known = {
            "stages",
            "workflow",
            "include",
            "default",
            "variables",
            "image",
            "services",
            "before_script",
            "after_script",
            "cache",
            "pages",
        }
        jobs = {
            key: value
            for key, value in data.items()
            if key not in known and isinstance(value, dict)
        }
    elif lower == "azure-pipelines.yml":
        ci_type = "azure"
        known = {"trigger", "pr", "stages", "jobs", "steps", "pool", "variables", "parameters"}
        jobs = dict(data["jobs"]) if isinstance(data.get("jobs"), dict) else {}
    elif lower == "bitbucket-pipelines.yml":
        ci_type = "bitbucket"
        known = {"definitions", "pipelines", "options", "image"}
        jobs = {}
    else:
        ci_type = "unknown"
        known = {"jobs", "steps", "stages", "pipelines", "definitions"}
        jobs = dict(data["jobs"]) if isinstance(data.get("jobs"), dict) else {}

    recognized = bool(set(data) & known or jobs)
    if not recognized:
        raise ArtifactParseError("unsupported_ci_structure")
    units: list[dict] = []
    jobs_node = _yaml_child(root, "jobs")
    for name in sorted(jobs, key=str):
        config = jobs[name]
        if not isinstance(config, dict):
            continue
        child = _yaml_child(jobs_node[1], str(name)) if jobs_node else _yaml_child(root, str(name))
        script_count = sum(
            len(value) if isinstance(value, list) else 1
            for key, value in config.items()
            if key in {"script", "before_script", "after_script"}
        )
        dependencies: list[Any] = (
            list(config["needs"]) if isinstance(config.get("needs"), list) else []
        )
        units.append(
            _fact(
                "ci",
                path,
                str(name),
                child[2] if child else 1,
                attributes={
                    "ci_type": ci_type,
                    "stage": config.get("stage"),
                    "script_count": script_count,
                    "needs": sorted(str(item) for item in dependencies),
                },
                references=_ci_references(config),
            )
        )
    step_count, action_count = _ci_command_counts(data)
    file_fact = _fact(
        "ci",
        path,
        Path(path).name,
        1,
        attributes={
            "ci_type": ci_type,
            "structure_recognized": recognized,
            "job_count": len(jobs),
            "step_count": step_count,
            "action_count": action_count,
        },
        references=_ci_references(data),
    )
    return file_fact, units


def _parse_ci(path: str, text: str) -> tuple[dict, list[dict]]:
    data, root = _load_yaml(text)
    if not path.startswith(".github/workflows/"):
        return _parse_ci_provider(path, text, data, root)
    jobs = data.get("jobs")
    job_node = _yaml_child(root, "jobs")
    units: list[dict] = []
    if isinstance(jobs, dict) and job_node:
        for name in sorted(jobs, key=str):
            config = jobs[name]
            if not isinstance(config, dict):
                continue
            child = _yaml_child(job_node[1], str(name))
            line = child[2] if child else 1
            steps: list[Any] = (
                list(config["steps"]) if isinstance(config.get("steps"), list) else []
            )
            actions: list[str] = []
            run_texts: list[str] = []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if isinstance(step.get("uses"), str):
                    actions.append(step["uses"])
                if isinstance(step.get("run"), str):
                    run_texts.append(step["run"])
            runner = config.get("runs-on")
            units.append(
                _fact(
                    "ci",
                    path,
                    str(name),
                    line,
                    attributes={
                        "runner": runner,
                        "step_count": len(steps),
                        "action_count": len(actions),
                        "run_count": len(run_texts),
                    },
                    references=[{"kind": "action", "value": value} for value in actions]
                    + _extract_references("\n".join(run_texts)),
                )
            )
    file_fact = _fact(
        "ci",
        path,
        Path(path).name,
        1,
        attributes={
            "workflow_name": data.get("name"),
            "job_count": len(jobs) if isinstance(jobs, dict) else 0,
        },
    )
    return file_fact, units


def _parse_compose(path: str, text: str) -> tuple[dict, list[dict]]:
    data, root = _load_yaml(text)
    services = data.get("services")
    services_node = _yaml_child(root, "services")
    units: list[dict] = []
    if isinstance(services, dict) and services_node:
        for name in sorted(services, key=str):
            config = services[name]
            if not isinstance(config, dict):
                continue
            child = _yaml_child(services_node[1], str(name))
            line = child[2] if child else 1
            build = config.get("build")
            context = (
                build
                if isinstance(build, str)
                else build.get("context")
                if isinstance(build, dict)
                else None
            )
            dockerfile = build.get("dockerfile") if isinstance(build, dict) else None
            ports: list[Any] = (
                list(config["ports"]) if isinstance(config.get("ports"), list) else []
            )
            raw_dependencies = config.get("depends_on")
            dependencies: list[Any]
            if isinstance(raw_dependencies, dict):
                dependencies = list(raw_dependencies)
            elif isinstance(raw_dependencies, list):
                dependencies = list(raw_dependencies)
            else:
                dependencies = []
            refs: list[Mapping[str, str]] = []
            if isinstance(context, str):
                refs.append({"kind": "path", "value": context})
            if isinstance(dockerfile, str):
                refs.append({"kind": "artifact", "value": dockerfile})
            units.append(
                _fact(
                    "container",
                    path,
                    str(name),
                    line,
                    attributes={
                        "image": config.get("image"),
                        "build_context": context,
                        "dockerfile": dockerfile,
                        "ports": [str(port) for port in ports],
                        "depends_on": sorted(str(item) for item in dependencies),
                        "environment_omitted": "environment" in config,
                        "command_omitted": any(key in config for key in ("command", "entrypoint")),
                    },
                    references=refs,
                )
            )
    file_fact = _fact(
        "container",
        path,
        Path(path).name,
        1,
        attributes={"service_count": len(services) if isinstance(services, dict) else 0},
    )
    return file_fact, units


def _docker_instructions(text: str) -> list[tuple[str, str, int]]:
    instructions: list[tuple[str, str, int]] = []
    pending = ""
    start_line = 1
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            start_line = number
        continuation = stripped.endswith("\\")
        pending += stripped[:-1] + " " if continuation else stripped
        if continuation:
            continue
        match = re.match(r"([A-Za-z]+)\s+(.*)$", pending)
        if match:
            instructions.append((match.group(1).upper(), match.group(2).strip(), start_line))
        pending = ""
    if pending:
        match = re.match(r"([A-Za-z]+)\s+(.*)$", pending)
        if match:
            instructions.append((match.group(1).upper(), match.group(2).strip(), start_line))
    return instructions


def _parse_dockerfile(path: str, text: str) -> tuple[dict, list[dict]]:
    instructions = _docker_instructions(text)
    stages = [(args, line) for instruction, args, line in instructions if instruction == "FROM"]
    units: list[dict] = []
    for index, (args, line) in enumerate(stages):
        try:
            tokens = shlex.split(args)
        except ValueError as exc:
            raise ArtifactParseError("invalid_dockerfile", line=line) from exc
        positional = [token for token in tokens if not token.startswith("--")]
        if not positional:
            continue
        alias = None
        for token_index, token in enumerate(tokens[:-1]):
            if token.upper() == "AS":
                alias = tokens[token_index + 1]
                break
        name = alias or f"stage_{index}"
        refs: list[Mapping[str, str]] = []
        for instruction, instruction_args, instruction_line in instructions:
            if instruction_line < line or (
                index + 1 < len(stages) and instruction_line >= stages[index + 1][1]
            ):
                continue
            if instruction == "COPY":
                try:
                    copy_tokens = [
                        token
                        for token in shlex.split(instruction_args)
                        if not token.startswith("--")
                    ]
                except ValueError:
                    continue
                for source in copy_tokens[:-1]:
                    if not source.startswith(("http://", "https://", "/")):
                        refs.append({"kind": "path", "value": source})
            elif instruction in {"RUN", "ADD"}:
                refs.extend(_extract_references(instruction_args))
        units.append(
            _fact(
                "container",
                path,
                name,
                line,
                attributes={"base_image": positional[0], "stage_index": index},
                references=refs,
            )
        )
    exposed = sorted(
        {
            args.split()[0]
            for instruction, args, _ in instructions
            if instruction == "EXPOSE" and args
        }
    )
    file_fact = _fact(
        "container",
        path,
        Path(path).name,
        1,
        attributes={
            "instruction_count": len(instructions),
            "stage_count": len(stages),
            "exposed_ports": exposed,
            "has_entrypoint": any(
                instruction == "ENTRYPOINT" for instruction, _, _ in instructions
            ),
            "has_cmd": any(instruction == "CMD" for instruction, _, _ in instructions),
        },
    )
    return file_fact, units


def _parse_makefile(path: str, text: str) -> tuple[dict, list[dict]]:
    lines = text.splitlines()
    units: list[dict] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^([A-Za-z0-9][\w./-]*)\s*:(?![:=])(.*)$", lines[index])
        if (
            not match
            or "%" in match.group(1)
            or "$" in match.group(1)
            or match.group(1).startswith(".")
            or re.match(r"\s*[?+!]?=", match.group(2))
        ):
            index += 1
            continue
        name = match.group(1)
        prerequisite_text = match.group(2).split("#", 1)[0]
        inline_recipe = ";" in prerequisite_text
        raw_prerequisites = prerequisite_text.split(";", 1)[0].split()
        if re.search(r"\$\(shell\b|`", prerequisite_text, re.IGNORECASE):
            prerequisites: list[str] = []
        else:
            prerequisites = [
                token
                for token in raw_prerequisites
                if token != "|" and re.fullmatch(r"[A-Za-z0-9_./@%+-]+", token)
            ]
        end = index + 1
        while end < len(lines) and (lines[end].startswith("\t") or not lines[end].strip()):
            end += 1
        recipe = [line[1:] for line in lines[index + 1 : end] if line.startswith("\t")]
        units.append(
            _fact(
                "build",
                path,
                name,
                index + 1,
                attributes={
                    "prerequisites": prerequisites,
                    "prerequisites_omitted": len(raw_prerequisites) - len(prerequisites),
                    "command_count": len(recipe) + int(inline_recipe),
                    "inline_recipe": inline_recipe,
                },
                references=_extract_references("\n".join(recipe)),
            )
        )
        index = end
    file_fact = _fact("build", path, Path(path).name, 1, attributes={"target_count": len(units)})
    return file_fact, units


def _parse_package_json(path: str, text: str) -> tuple[dict, list[dict]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactParseError("invalid_json", line=exc.lineno, column=exc.colno) from exc
    if not isinstance(data, dict):
        raise ArtifactParseError("invalid_json_shape")
    scripts: Mapping[str, Any] = (
        dict(data["scripts"]) if isinstance(data.get("scripts"), dict) else {}
    )
    scripts_offset = text.find('"scripts"')
    units: list[dict] = []
    for name in sorted(scripts, key=str):
        command = scripts[name]
        if not isinstance(command, str):
            continue
        units.append(
            _fact(
                "manifest",
                path,
                str(name),
                _json_key_line(text, str(name), max(0, scripts_offset)),
                attributes={"script_type": "command"},
                references=_extract_references(command),
            )
        )
    dependency_count = 0
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        value = data.get(key)
        if isinstance(value, dict):
            dependency_count += len(value)
    file_fact = _fact(
        "manifest",
        path,
        Path(path).name,
        1,
        attributes={
            "ecosystem": "node",
            "name": data.get("name"),
            "version": data.get("version"),
            "main": data.get("main"),
            "script_count": len(scripts),
            "dependency_count": dependency_count,
        },
    )
    return file_fact, units


def _parse_pyproject(path: str, text: str) -> tuple[dict, list[dict]]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ArtifactParseError("invalid_toml", line=getattr(exc, "lineno", None)) from exc
    project: Mapping[str, Any] = (
        dict(data["project"]) if isinstance(data.get("project"), dict) else {}
    )
    tool: Mapping[str, Any] = dict(data["tool"]) if isinstance(data.get("tool"), dict) else {}
    poetry: Mapping[str, Any] = dict(tool["poetry"]) if isinstance(tool.get("poetry"), dict) else {}
    tables: list[tuple[str, Mapping[str, Any]]] = []
    for section, key in (("project.scripts", "scripts"), ("project.gui-scripts", "gui-scripts")):
        value = project.get(key)
        if isinstance(value, dict):
            tables.append((section, value))
    if isinstance(poetry, dict) and isinstance(poetry.get("scripts"), dict):
        tables.append(("tool.poetry.scripts", poetry["scripts"]))
    units: list[dict] = []
    for section, entries in tables:
        for name in sorted(entries, key=str):
            target = entries[name]
            if not isinstance(target, str):
                continue
            module, separator, function = target.partition(":")
            units.append(
                _fact(
                    "manifest",
                    path,
                    str(name),
                    _section_key_line(text, section, str(name)),
                    attributes={
                        "target": target,
                        "module": module,
                        "function": function if separator else None,
                    },
                    references=[{"kind": "module", "value": module}],
                )
            )
    dependencies = project.get("dependencies")
    file_fact = _fact(
        "manifest",
        path,
        Path(path).name,
        1,
        attributes={
            "ecosystem": "python",
            "name": project.get("name"),
            "requires_python": project.get("requires-python"),
            "dependency_count": len(dependencies) if isinstance(dependencies, (dict, list)) else 0,
        },
    )
    return file_fact, units


def _parse_setup_cfg(path: str, text: str) -> tuple[dict, list[dict]]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ArtifactParseError("invalid_ini", line=getattr(exc, "lineno", None)) from exc
    units: list[dict] = []
    if parser.has_section("options.entry_points"):
        for line_number, line in enumerate(
            parser.get("options.entry_points", "console_scripts", fallback="").splitlines(), start=1
        ):
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, target = (part.strip() for part in line.split("=", 1))
            module, separator, function = target.partition(":")
            offset = text.find(line)
            units.append(
                _fact(
                    "manifest",
                    path,
                    name,
                    _line_of(text, offset) if offset >= 0 else line_number,
                    attributes={
                        "target": target,
                        "module": module,
                        "function": function if separator else None,
                    },
                    references=[{"kind": "module", "value": module}],
                )
            )
    metadata_name = parser.get("metadata", "name", fallback=None)
    file_fact = _fact(
        "manifest",
        path,
        Path(path).name,
        1,
        attributes={"ecosystem": "python", "name": metadata_name},
    )
    return file_fact, units


def _parse_requirements(path: str, text: str) -> tuple[dict, list[dict]]:
    dependencies = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]
    return _fact(
        "manifest",
        path,
        Path(path).name,
        1,
        attributes={"ecosystem": "python", "dependency_count": len(dependencies)},
    ), []


def _parse_generic_manifest(path: str, text: str) -> tuple[dict, list[dict]]:
    ecosystems = {
        "cargo.toml": "rust",
        "go.mod": "go",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "build.sbt": "sbt",
        "pubspec.yaml": "dart",
        "build.zig": "zig",
        "lakefile.toml": "lean",
        "lake-manifest.json": "lean",
        "lean-toolchain": "lean",
        "gemfile": "ruby",
        "composer.json": "php",
        "setup.py": "python",
    }
    return _fact(
        "manifest",
        path,
        Path(path).name,
        1,
        attributes={
            "ecosystem": ecosystems.get(Path(path).name.lower(), "unknown"),
            "line_count": len(text.splitlines()),
        },
        # SBT 常以 file("src/main/scala/...") 显式列出源码；只提取字面路径，
        # 不执行 build.sbt，也不把普通 Scala 文件升格为 artifact。
        references=_extract_references(text)
        if Path(path).name.lower() in {"build.sbt", "build.zig", "lakefile.toml"}
        else (),
    ), []


def _parse_openapi(path: str, text: str) -> tuple[dict, list[dict]]:
    if path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArtifactParseError("invalid_json", line=exc.lineno, column=exc.colno) from exc
        root = None
        if not isinstance(data, dict):
            raise ArtifactParseError("invalid_json_shape")
    else:
        data, root = _load_yaml(text)
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    paths_node = _yaml_child(root, "paths") if root is not None else None
    units: list[dict] = []
    for route in sorted(paths, key=str):
        operations = paths[route]
        if not isinstance(operations, dict):
            continue
        route_node = _yaml_child(paths_node[1], str(route)) if paths_node else None
        for method in sorted(operations, key=str):
            if method.lower() not in _HTTP_METHODS:
                continue
            operation = operations[method]
            if not isinstance(operation, dict):
                continue
            method_node = _yaml_child(route_node[1], str(method)) if route_node else None
            line = (
                method_node[2]
                if method_node
                else (
                    _json_key_line(text, str(method), text.find(f'"{route}"'))
                    if root is None
                    else 1
                )
            )
            units.append(
                _fact(
                    "schema",
                    path,
                    f"{method.upper()} {route}",
                    line,
                    attributes={
                        "method": method.upper(),
                        "path": str(route),
                        "operation_id": operation.get("operationId"),
                    },
                )
            )
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    return _fact(
        "schema",
        path,
        Path(path).name,
        1,
        attributes={
            "schema_type": "openapi",
            "version": data.get("openapi") or data.get("swagger"),
            "title": info.get("title"),
            "path_count": len(paths),
        },
    ), units


def _parse_proto(path: str, text: str) -> tuple[dict, list[dict]]:
    units: list[dict] = []
    for match in re.finditer(r"^\s*(service|message)\s+([A-Za-z_]\w*)\s*\{", text, re.MULTILINE):
        unit_type, name = match.groups()
        units.append(
            _fact(
                "schema",
                path,
                name,
                _line_of(text, match.start()),
                attributes={"unit_type": unit_type},
            )
        )
    return _fact(
        "schema",
        path,
        Path(path).name,
        1,
        attributes={
            "schema_type": "protobuf",
            "service_count": sum(
                1 for unit in units if unit["attributes"]["unit_type"] == "service"
            ),
            "message_count": sum(
                1 for unit in units if unit["attributes"]["unit_type"] == "message"
            ),
        },
    ), units


def _parse_json_schema(path: str, text: str) -> tuple[dict, list[dict]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactParseError("invalid_json", line=exc.lineno, column=exc.colno) from exc
    if not isinstance(data, dict):
        raise ArtifactParseError("invalid_json_shape")
    properties: Mapping[str, Any] = (
        dict(data["properties"]) if isinstance(data.get("properties"), dict) else {}
    )
    required: list[Any] = list(data["required"]) if isinstance(data.get("required"), list) else []
    return _fact(
        "schema",
        path,
        Path(path).name,
        1,
        attributes={
            "schema_type": "json_schema",
            "title": data.get("title"),
            "property_count": len(properties),
            "required_count": len(required),
        },
    ), []


def _parse_script(path: str, text: str) -> tuple[dict, list[dict]]:
    lines = text.splitlines()
    first_line = lines[0] if lines else ""
    interpreter = None
    if first_line.startswith("#!"):
        try:
            tokens = shlex.split(first_line[2:].strip())
        except ValueError:
            tokens = first_line[2:].strip().split()
        # A shebang may contain arbitrary arguments; export only its executable.
        interpreter = tokens[0] if tokens else None
    return _fact(
        "script",
        path,
        Path(path).name,
        1,
        attributes={"interpreter": interpreter, "line_count": len(lines)},
        references=_extract_references(text),
    ), []


def _parse_artifact(kind: str, path: str, text: str) -> tuple[dict, list[dict]]:
    name = Path(path).name.lower()
    if kind == "ci":
        if name == "jenkinsfile":
            return _fact("ci", path, Path(path).name, 1, attributes={"ci_type": "jenkins"}), []
        return _parse_ci(path, text)
    if kind == "container":
        if re.fullmatch(r"(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml", name):
            return _parse_compose(path, text)
        return _parse_dockerfile(path, text)
    if kind == "manifest":
        if name == "package.json":
            return _parse_package_json(path, text)
        if name == "pyproject.toml":
            return _parse_pyproject(path, text)
        if name == "setup.cfg":
            return _parse_setup_cfg(path, text)
        if name.startswith("requirements") and name.endswith(".txt"):
            return _parse_requirements(path, text)
        return _parse_generic_manifest(path, text)
    if kind == "build":
        if name in {"build.zig", "lakefile.lean"}:
            return _fact(
                "build",
                path,
                Path(path).name,
                1,
                attributes={"line_count": len(text.splitlines())},
                references=_extract_references(text),
            ), []
        if name in {"makefile", "gnumakefile"}:
            return _parse_makefile(path, text)
        return _fact(
            "build", path, Path(path).name, 1, attributes={"line_count": len(text.splitlines())}
        ), []
    if kind == "schema":
        if name.startswith(("openapi.", "swagger.")):
            return _parse_openapi(path, text)
        if name.endswith(".proto"):
            return _parse_proto(path, text)
        if name.endswith(".json"):
            return _parse_json_schema(path, text)
        return _fact(
            "schema",
            path,
            Path(path).name,
            1,
            attributes={"schema_type": "unknown", "line_count": len(text.splitlines())},
        ), []
    if kind == "script":
        return _parse_script(path, text)
    return _fact(kind, path, Path(path).name, 1), []


def _previous_fingerprints(previous: Mapping[str, Any] | None) -> tuple[dict[str, str], list[str]]:
    if previous is None:
        return {}, []
    if not isinstance(previous, Mapping):
        return {}, ["invalid_previous_index"]
    raw = previous.get("fingerprints")
    if not isinstance(raw, Mapping):
        return {}, ["invalid_previous_index"]
    fingerprints = {str(path): str(value) for path, value in raw.items() if isinstance(value, str)}
    if len(fingerprints) != len(raw):
        return fingerprints, ["invalid_previous_index"]
    return fingerprints, []


def analyze_artifact_facts(
    repo_path: str | Path,
    *,
    previous: Mapping[str, Any] | None = None,
    options: ArtifactFactOptions | None = None,
) -> dict[str, Any]:
    """Collect a deterministic, capped fact snapshot without executing files."""

    root = Path(repo_path).expanduser().resolve()
    opts = options or ArtifactFactOptions()
    previous_fingerprints, warnings = _previous_fingerprints(previous)
    result: dict[str, Any] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": "ok",
        "summary": {},
        "facts": [],
        "files": [],
        "omitted_files": [],
        "fingerprints": {},
        "changed_files": [],
        "warnings": warnings,
        "limits": {
            "max_files": opts.max_files,
            "max_file_bytes": opts.max_file_bytes,
            "max_units_per_file": opts.max_units_per_file,
            "max_facts": opts.max_facts,
        },
    }
    try:
        candidates = _discover_candidates(root, opts)
    except (OSError, ValueError) as exc:
        result["status"] = "unavailable"
        result["warnings"].append(f"discovery_failed:{type(exc).__name__}")
        result["summary"] = {
            "files_scanned": 0,
            "files_parsed": 0,
            "files_failed": 0,
            "files_truncated": 0,
            "facts": 0,
            "facts_omitted": 0,
            "by_kind": {},
        }
        return result

    parsed_candidates = candidates[: opts.max_files]
    omitted_candidates = candidates[opts.max_files :]
    parsed_set = set(parsed_candidates)
    omitted_set = set(omitted_candidates)
    facts: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    omitted_files: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    failed = 0
    truncated = 0
    facts_omitted = 0
    by_kind: dict[str, dict[str, int]] = {}

    if omitted_candidates:
        warnings.append(f"file_cap:{len(omitted_candidates)}")

    for rel_path, kind in candidates:
        path = root / rel_path
        counts = by_kind.setdefault(kind, {"files": 0, "facts": 0, "failed": 0, "omitted": 0})
        try:
            raw, size, was_truncated, fingerprint = _read_head(path, opts.max_file_bytes)
        except OSError as exc:
            if (rel_path, kind) in parsed_set:
                failed += 1
                counts["files"] += 1
                counts["failed"] += 1
                files.append(
                    {
                        "path": rel_path,
                        "kind": kind,
                        "status": "failed",
                        "facts": 0,
                        "error": {"code": "unreadable", "error_type": type(exc).__name__},
                    }
                )
                warnings.append(f"unreadable:{rel_path}")
            else:
                counts["omitted"] += 1
                omitted_files.append(
                    {
                        "path": rel_path,
                        "kind": kind,
                        "reason": "file_cap",
                        "read_error": type(exc).__name__,
                    }
                )
            continue

        fingerprints[rel_path] = fingerprint
        if (rel_path, kind) in omitted_set:
            counts["omitted"] += 1
            omitted_files.append({"path": rel_path, "kind": kind, "reason": "file_cap"})
            continue

        counts["files"] += 1
        file_entry: dict[str, Any] = {
            "path": rel_path,
            "kind": kind,
            "status": "truncated" if was_truncated else "ok",
            "truncated": was_truncated,
            "size_bytes": size,
            "fingerprint": fingerprint,
            "facts": 0,
        }
        if was_truncated:
            truncated += 1
            warnings.append(f"truncated:{rel_path}")
        if b"\x00" in raw:
            failed += 1
            counts["failed"] += 1
            file_entry["status"] = "failed"
            file_entry["error"] = {"code": "binary_content"}
            files.append(file_entry)
            warnings.append(f"binary_content:{rel_path}")
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
            file_fact, units = _parse_artifact(kind, rel_path, text)
        except ArtifactParseError as exc:
            failed += 1
            counts["failed"] += 1
            file_entry["status"] = "failed"
            file_entry["error"] = {"code": exc.code}
            if exc.line is not None:
                file_entry["error"]["line"] = exc.line
            if exc.column is not None:
                file_entry["error"]["column"] = exc.column
            files.append(file_entry)
            warnings.append(f"{exc.code}:{rel_path}")
            continue
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            failed += 1
            counts["failed"] += 1
            file_entry["status"] = "failed"
            file_entry["error"] = {"code": "parse_failed", "error_type": type(exc).__name__}
            files.append(file_entry)
            warnings.append(f"parse_failed:{rel_path}")
            continue

        selected_units = units[: opts.max_units_per_file]
        if len(units) > opts.max_units_per_file:
            facts_omitted += len(units) - opts.max_units_per_file
            warnings.append(f"unit_cap:{rel_path}:{len(units) - opts.max_units_per_file}")
        for fact in [file_fact, *selected_units]:
            if len(facts) >= opts.max_facts:
                facts_omitted += 1
                continue
            facts.append(fact)
            file_entry["facts"] += 1
            counts["facts"] += 1
        files.append(file_entry)

    if facts_omitted:
        warnings.append(f"fact_cap:{facts_omitted}")
    facts.sort(
        key=lambda item: (item["path"], item["line"], item["kind"], item["name"], item["id"])
    )
    files.sort(key=lambda item: item["path"])
    omitted_files.sort(key=lambda item: item["path"])
    for kind in by_kind:
        by_kind[kind]["facts"] = sum(1 for fact in facts if fact["kind"] == kind)
    current_fingerprints = fingerprints
    changed = (
        sorted(
            path
            for path in set(previous_fingerprints) | set(current_fingerprints)
            if previous_fingerprints.get(path) != current_fingerprints.get(path)
        )
        if previous is not None
        else []
    )
    has_degradation = bool(
        failed
        or truncated
        or omitted_candidates
        or facts_omitted
        or any("invalid_previous_index" in warning for warning in warnings)
    )
    result.update(
        {
            "status": "partial" if has_degradation else "ok",
            "summary": {
                "files_scanned": len(candidates),
                "files_parsed": len(parsed_candidates),
                "files_failed": failed,
                "files_truncated": truncated,
                "facts": len(facts),
                "facts_omitted": facts_omitted,
                "by_kind": {kind: by_kind[kind] for kind in sorted(by_kind)},
            },
            "facts": facts,
            "files": files,
            "omitted_files": omitted_files,
            "fingerprints": dict(sorted(current_fingerprints.items())),
            "changed_files": changed,
            "warnings": sorted(set(warnings)),
        }
    )
    return result
