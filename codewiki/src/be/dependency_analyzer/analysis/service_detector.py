"""Service boundary detector for monorepo sub-service discovery.

Detects sub-services within a single git repository using multiple
heuristic signals: docker-compose definitions, Dockerfiles, build
manifests (go.mod / pom.xml / package.json / pyproject.toml), and
convention directories (services/ / apps/).

Used by ``analyze_repo`` to partition routes by sub-service so that
``CrossServiceMatcher`` can find intra-repo cross-service calls.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Directories that should never be treated as services
_EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".next",
    ".nuxt",
    "vendor",
    "test",
    "tests",
    "testing",
    "e2e",
    "docs",
    "doc",
    "scripts",
    "migrations",
    "fixtures",
    "mocks",
    "__mocks__",
    ".codewiki",
    "repowiki",
    "workspace-wiki",
}

# Convention directories whose children are likely services
_CONVENTION_DIRS = {"services", "apps", "microservices", "modules", "packages"}

# Maximum directory depth for service detection (relative to repo root)
_MAX_DEPTH = 3


class ServiceInfo:
    """A detected sub-service within a monorepo."""

    def __init__(self, name: str, relative_path: str, source: str):
        self.name = name
        self.relative_path = relative_path  # POSIX-style relative to repo root
        self.source = source  # detection signal: "docker-compose", "dockerfile", etc.

    def __repr__(self) -> str:
        return (
            f"ServiceInfo(name={self.name!r}, path={self.relative_path!r}, source={self.source!r})"
        )


def detect_services(repo_path: Path) -> Dict[str, ServiceInfo]:
    """Detect sub-services within a monorepo.

    Returns a dict mapping service name → ServiceInfo.  An empty dict
    (or a single entry) means no meaningful sub-service boundaries were
    found and cross-service analysis should be skipped.
    """
    repo_path = repo_path.resolve()
    services: Dict[str, ServiceInfo] = {}

    # Phase 1: docker-compose.yml (highest confidence)
    _detect_from_compose(repo_path, services)

    # Phase 2: Multiple Dockerfiles
    _detect_from_dockerfiles(repo_path, services)

    # Phase 3: Build manifests (go.mod, pom.xml, package.json, pyproject.toml)
    _detect_from_build_manifests(repo_path, services)

    # Phase 4: Convention directories (services/, apps/)
    _detect_from_convention_dirs(repo_path, services)

    # Phase 5: Spring Boot application.yml / application.properties
    _detect_from_spring_config(repo_path, services)

    # Filter: remove services that are sub-paths of other detected services
    services = _remove_nested_services(services)

    if services:
        logger.info(
            "Detected %d sub-services in %s: %s",
            len(services),
            repo_path.name,
            ", ".join(f"{s.name} ({s.source})" for s in services.values()),
        )

    return services


def assign_service_label(
    file_path: str,
    services: Dict[str, ServiceInfo],
    repo_path: str = "",
    fallback: str = "_root",
) -> str:
    """Given a file path, return the best-matching service name using
    longest-prefix matching on the path relative to ``repo_path``.

    Returns ``fallback`` if the file does not fall under any detected
    service directory.
    """
    # Normalise to forward slashes
    fp = file_path.replace("\\", "/")

    # Compute path relative to repo root for accurate prefix matching
    if repo_path:
        rp = repo_path.replace("\\", "/")
        if not rp.endswith("/"):
            rp += "/"
        if fp.startswith(rp):
            fp = fp[len(rp) :]

    best_name = fallback
    best_len = 0
    for name, info in services.items():
        prefix = info.relative_path
        if not prefix:
            continue
        # Ensure prefix ends with "/" for clean boundary matching
        if not prefix.endswith("/"):
            prefix += "/"
        if fp.startswith(prefix):
            if len(prefix) > best_len:
                best_len = len(prefix)
                best_name = name
    return best_name


# ---------------------------------------------------------------------------
# Pruned directory walker (avoids descending into excluded dirs)
# ---------------------------------------------------------------------------


def _walk_pruned(
    root: Path,
    max_depth: int = _MAX_DEPTH,
) -> Iterator[Tuple[Path, List[str], List[str]]]:
    """os.walk with in-place pruning of excluded directories.

    Yields ``(dir_path, dir_names, file_names)`` like ``os.walk``, but
    never descends into ``_EXCLUDE_DIRS`` or hidden directories, and
    stops at ``max_depth`` levels below ``root``.
    """
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        # Compute depth relative to root
        rel = os.path.relpath(dirpath, root_str)
        if rel == ".":
            depth = 0
        else:
            depth = len(rel.replace("\\", "/").split("/"))

        # Prune excluded dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]

        # Stop descending beyond max_depth
        if depth >= max_depth:
            dirnames.clear()

        yield Path(dirpath), dirnames, filenames


def _find_files(root: Path, name: str, max_depth: int = _MAX_DEPTH) -> List[Path]:
    """Find files matching ``name`` under ``root`` with pruned walking."""
    results = []
    for dirpath, _, filenames in _walk_pruned(root, max_depth):
        if name in filenames:
            results.append(dirpath / name)
    return results


def _find_files_glob(root: Path, pattern: str, max_depth: int = _MAX_DEPTH) -> List[Path]:
    """Find files matching a glob pattern (e.g. 'Dockerfile.*') with pruned walking."""
    import fnmatch

    results = []
    for dirpath, _, filenames in _walk_pruned(root, max_depth):
        for fn in filenames:
            if fnmatch.fnmatch(fn, pattern):
                results.append(dirpath / fn)
    return results


# ---------------------------------------------------------------------------
# Service registration (handles name collisions)
# ---------------------------------------------------------------------------


def _register_service(
    services: Dict[str, ServiceInfo],
    name: str,
    relative_path: str,
    source: str,
):
    """Register a service, qualifying the name on collision.

    If ``name`` is already taken by a different path, use the full
    relative path as the name to avoid silent drops.
    """
    if name not in services:
        services[name] = ServiceInfo(name=name, relative_path=relative_path, source=source)
    elif services[name].relative_path != relative_path:
        # Collision: qualify with parent directory
        qualified = relative_path.replace("/", "-").replace("\\", "-")
        if qualified not in services:
            services[qualified] = ServiceInfo(
                name=qualified,
                relative_path=relative_path,
                source=source,
            )


# ---------------------------------------------------------------------------
# Phase 1: docker-compose
# ---------------------------------------------------------------------------


def _detect_from_compose(repo_path: Path, services: Dict[str, ServiceInfo]):
    """Parse docker-compose files for service definitions with build contexts."""
    for pattern in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        for f in _find_files(repo_path, pattern):
            _parse_compose_for_services(f, repo_path, services)


def _parse_compose_for_services(
    compose_file: Path,
    repo_path: Path,
    services: Dict[str, ServiceInfo],
):
    try:
        import yaml

        data = yaml.safe_load(compose_file.read_text(encoding="utf-8", errors="replace"))
    except ImportError:
        logger.debug("PyYAML not available, skipping compose parsing")
        return
    except Exception as e:
        logger.warning("Failed to parse %s: %s", compose_file, e)
        return

    if not isinstance(data, dict):
        return
    svc_defs = data.get("services", {})
    if not isinstance(svc_defs, dict):
        return

    compose_dir = compose_file.parent

    for svc_name, svc_config in svc_defs.items():
        if not isinstance(svc_config, dict):
            continue

        # Determine the service's source directory
        build = svc_config.get("build", {})
        if isinstance(build, str):
            context_dir = build
        elif isinstance(build, dict):
            context_dir = build.get("context", ".")
        else:
            context_dir = None

        # Skip image-only services (redis, postgres, etc.) — no code to analyze
        if context_dir is None:
            continue

        abs_dir = (compose_dir / context_dir).resolve()

        try:
            rel = abs_dir.relative_to(repo_path).as_posix()
        except ValueError:
            continue

        if rel == ".":
            # Service builds from repo root — not a useful partition
            continue

        if _is_excluded_rel(rel):
            continue

        _register_service(services, svc_name, rel, "docker-compose")


# ---------------------------------------------------------------------------
# Phase 2: Dockerfiles
# ---------------------------------------------------------------------------


def _detect_from_dockerfiles(repo_path: Path, services: Dict[str, ServiceInfo]):
    """Detect services from Dockerfiles in distinct sub-directories."""
    dockerfiles: List[Path] = []
    for name in ("Dockerfile", "dockerfile"):
        dockerfiles.extend(_find_files(repo_path, name))
    # Also match Dockerfile.* variants (e.g. Dockerfile.backend)
    dockerfiles.extend(_find_files_glob(repo_path, "Dockerfile.*"))

    for df in dockerfiles:
        svc_dir = df.parent
        try:
            rel = svc_dir.relative_to(repo_path).as_posix()
        except ValueError:
            continue
        if rel == ".":
            continue
        if _is_excluded_rel(rel):
            continue
        if _depth(rel) > _MAX_DEPTH:
            continue

        svc_name = _service_name_from_path(rel)
        if svc_name:
            _register_service(services, svc_name, rel, "dockerfile")


# ---------------------------------------------------------------------------
# Phase 3: Build manifests
# ---------------------------------------------------------------------------

_BUILD_MANIFESTS = {
    "go.mod": "go",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "package.json": "node",
    "pyproject.toml": "python",
    "setup.py": "python",
    "Cargo.toml": "rust",
}


def _detect_from_build_manifests(repo_path: Path, services: Dict[str, ServiceInfo]):
    """Detect services from build manifests in sub-directories."""
    # Collect all manifest locations first, then decide if there are multiples
    manifest_locations: Dict[str, List[Path]] = {}
    for manifest_name in _BUILD_MANIFESTS:
        locations = []
        for f in _find_files(repo_path, manifest_name):
            try:
                rel = f.parent.relative_to(repo_path).as_posix()
            except ValueError:
                continue
            if rel == ".":
                continue
            if _is_excluded_rel(rel):
                continue
            if _depth(rel) > _MAX_DEPTH:
                continue
            locations.append(f)
        if locations:
            manifest_locations[manifest_name] = locations

    # Only treat as multi-service if there are ≥2 manifests of the same type
    # OR manifests of different types in different directories
    all_dirs: Set[str] = set()
    for manifest_name, locations in manifest_locations.items():
        if len(locations) < 2 and len(manifest_locations) == 1:
            # Single manifest of a single type — likely not a monorepo
            continue
        for f in locations:
            try:
                rel = f.parent.relative_to(repo_path).as_posix()
            except ValueError:
                continue

            # For package.json, verify it has a start/main script (skip pure libs)
            if manifest_name == "package.json":
                if not _package_json_is_service(f):
                    continue

            svc_name = _service_name_from_path(rel)
            if svc_name and rel not in all_dirs:
                all_dirs.add(rel)
                _register_service(
                    services,
                    svc_name,
                    rel,
                    f"build-manifest:{_BUILD_MANIFESTS[manifest_name]}",
                )


def _package_json_is_service(pkg_path: Path) -> bool:
    """Check if a package.json looks like a runnable service (has start/main)."""
    try:
        import json

        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    scripts = data.get("scripts", {})
    if isinstance(scripts, dict) and ("start" in scripts or "serve" in scripts or "dev" in scripts):
        return True
    if data.get("main"):
        return True
    return False


# ---------------------------------------------------------------------------
# Phase 4: Convention directories
# ---------------------------------------------------------------------------


def _detect_from_convention_dirs(repo_path: Path, services: Dict[str, ServiceInfo]):
    """Detect services under convention directories like services/, apps/."""
    for conv_name in _CONVENTION_DIRS:
        conv_dir = repo_path / conv_name
        if not conv_dir.is_dir():
            continue
        for child in sorted(conv_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in _EXCLUDE_DIRS:
                continue
            try:
                rel = child.relative_to(repo_path).as_posix()
            except ValueError:
                continue

            # Must contain at least one source file to be a real service
            if not _has_source_files(child):
                continue

            _register_service(services, child.name, rel, f"convention:{conv_name}")


def _has_source_files(directory: Path, max_files: int = 200) -> bool:
    """Quick check: does this directory contain source code files?

    Uses os.walk with pruning for better coverage than rglob with a
    small limit.
    """
    source_exts = {
        ".py",
        ".java",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".kt",
        ".kts",
        ".cs",
        ".php",
        ".rb",
        ".c",
        ".cpp",
    }
    count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(str(directory)):
            # Prune excluded dirs
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix.lower() in source_exts:
                    return True
                count += 1
                if count > max_files:
                    return False
    except PermissionError:
        pass
    return False


# ---------------------------------------------------------------------------
# Phase 5: Spring Boot application.yml / application.properties
# ---------------------------------------------------------------------------


def _detect_from_spring_config(repo_path: Path, services: Dict[str, ServiceInfo]):
    """Detect Spring Boot services via spring.application.name."""
    # YAML configs
    for pattern in ("application.yml", "application.yaml"):
        for f in _find_files(repo_path, pattern):
            name = _extract_spring_app_name_yml(f)
            if name:
                _register_spring_service(f, name, repo_path, services)

    # Properties configs
    for f in _find_files(repo_path, "application.properties"):
        name = _extract_spring_app_name_properties(f)
        if name:
            _register_spring_service(f, name, repo_path, services)


def _register_spring_service(
    config_file: Path,
    name: str,
    repo_path: Path,
    services: Dict[str, ServiceInfo],
):
    """Register a Spring Boot service after finding its app name."""
    try:
        svc_dir = _find_service_root(config_file.parent, repo_path)
        rel = svc_dir.relative_to(repo_path).as_posix()
    except ValueError:
        return
    if rel == "." or _is_excluded_rel(rel):
        return
    _register_service(services, name, rel, "spring-boot")


def _extract_spring_app_name_yml(yml_path: Path) -> Optional[str]:
    """Extract spring.application.name from a YAML file."""
    try:
        import yaml

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    spring = data.get("spring", {})
    if isinstance(spring, dict):
        app = spring.get("application", {})
        if isinstance(app, dict):
            name = app.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _extract_spring_app_name_properties(prop_path: Path) -> Optional[str]:
    """Extract spring.application.name from a .properties file."""
    try:
        content = prop_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(
        r"^spring\.application\.name\s*=\s*(.+?)$",
        content,
        re.MULTILINE,
    )
    if m:
        name = m.group(1).strip()
        if name:
            return name
    return None


def _find_service_root(start: Path, repo_root: Path) -> Path:
    """Walk up from start to find the nearest directory with a build manifest."""
    markers = {
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "go.mod",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "Cargo.toml",
    }
    current = start
    while current != repo_root and current != current.parent:
        if any((current / m).exists() for m in markers):
            return current
        current = current.parent
    return start


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_excluded_rel(rel_path: str) -> bool:
    """Check if a relative path contains excluded directory segments."""
    parts = rel_path.replace("\\", "/").split("/")
    return any(p in _EXCLUDE_DIRS or p.startswith(".") for p in parts)


def _depth(rel_path: str) -> int:
    """Count directory depth of a relative path."""
    return len([p for p in rel_path.replace("\\", "/").split("/") if p])


def _service_name_from_path(rel_path: str) -> Optional[str]:
    """Derive a service name from a relative directory path.

    ``backend/order-service`` → ``order-service``
    ``services/auth`` → ``auth``
    ``apps/web`` → ``web``
    """
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    if not parts:
        return None
    # Use the last path segment as the service name
    return parts[-1]


def _remove_nested_services(services: Dict[str, ServiceInfo]) -> Dict[str, ServiceInfo]:
    """Remove services whose path is a sub-directory of another service.

    If both ``backend`` and ``backend/api`` are detected, keep only
    ``backend`` (the broader boundary).
    """
    if len(services) <= 1:
        return services

    # Sort by path length (shortest first)
    sorted_svcs = sorted(services.values(), key=lambda s: len(s.relative_path))
    kept: Dict[str, ServiceInfo] = {}
    kept_paths: List[str] = []

    for svc in sorted_svcs:
        prefix = svc.relative_path
        if not prefix.endswith("/"):
            prefix += "/"
        # Check if this service is nested under an already-kept service
        is_nested = any(
            prefix.startswith(kp if kp.endswith("/") else kp + "/") for kp in kept_paths
        )
        if not is_nested:
            kept[svc.name] = svc
            kept_paths.append(svc.relative_path)

    return kept
