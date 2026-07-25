"""Route extractors registry — language-specific HTTP route detection.

Each extractor is a callable ``(file_path, content, repo_name) -> List[RouteNode]``.
Register extractors in the ``EXTRACTORS`` dict keyed by file extension.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from codewiki.src.be.dependency_analyzer.models.cross_service import RouteNode

# Type alias for an extractor function
RouteExtractor = Callable[[str, str, str], List[RouteNode]]

EXTRACTORS: Dict[str, RouteExtractor] = {}


def _lazy_register():
    """Register all built-in extractors (lazy imports to avoid circular deps)."""
    if EXTRACTORS:
        return

    from codewiki.src.be.dependency_analyzer.analyzers.route_extractors.python_routes import (
        extract_python_routes,
    )
    from codewiki.src.be.dependency_analyzer.analyzers.route_extractors.java_routes import (
        extract_java_routes,
    )
    from codewiki.src.be.dependency_analyzer.analyzers.route_extractors.js_routes import (
        extract_js_routes,
        extract_ts_routes,
    )
    from codewiki.src.be.dependency_analyzer.analyzers.route_extractors.go_routes import (
        extract_go_routes,
    )

    EXTRACTORS[".py"] = extract_python_routes
    EXTRACTORS[".java"] = extract_java_routes
    EXTRACTORS[".js"] = extract_js_routes
    EXTRACTORS[".jsx"] = extract_js_routes
    EXTRACTORS[".mjs"] = extract_js_routes
    EXTRACTORS[".ts"] = extract_ts_routes
    EXTRACTORS[".tsx"] = extract_ts_routes
    EXTRACTORS[".go"] = extract_go_routes


def get_extractor(ext: str) -> Optional[RouteExtractor]:
    """Return the route extractor for *ext*, or ``None`` if unsupported."""
    _lazy_register()
    return EXTRACTORS.get(ext)
