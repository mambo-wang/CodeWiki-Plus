"""Go route extractor — Gin, Chi, Echo, net/http, httpx.

Uses regex-based heuristics on raw source text.
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    RouteNode, RouteProtocol, RouteRole,
)
from codewiki.src.be.dependency_analyzer.utils.path_canonicalizer import (
    canonicalize_path, make_route_key,
)

logger = logging.getLogger(__name__)

# Gin: r.GET("/path", handler), group.POST("/path", handler)
_GIN_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "ANY"}

# Chi / Echo / mux patterns
_ROUTER_METHODS_PATTERN = re.compile(
    r'(\w+)\s*\.\s*(Get|Post|Put|Delete|Patch|Head|Options|HandleFunc|Handle)\s*\(\s*"([^"]+)"',
    re.MULTILINE,
)

# net/http client: http.Get("url"), http.Post("url", ...)
_HTTP_CLIENT_PATTERN = re.compile(
    r'http\s*\.\s*(Get|Post|PostForm|Do|Head)\s*\(\s*"([^"]+)"',
    re.MULTILINE,
)

# net/http.NewRequest: http.NewRequest("GET", "url", ...)
_NEW_REQUEST_PATTERN = re.compile(
    r'http\s*\.\s*NewRequest\s*\(\s*"(\w+)"\s*,\s*"([^"]+)"',
    re.MULTILINE,
)

# net/http server: http.HandleFunc("/path", handler)
_HTTP_SERVER_PATTERN = re.compile(
    r'http\s*\.\s*(?:HandleFunc|Handle)\s*\(\s*"([^"]+)"',
    re.MULTILINE,
)


def _get_relative_path(file_path: str) -> str:
    try:
        return os.path.relpath(file_path)
    except (ValueError, TypeError):
        return str(file_path)


def _strip_url_to_path(url: str) -> str:
    if url.startswith("/"):
        return url
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            rest = url[len(scheme):]
            slash = rest.find("/")
            return rest[slash:] if slash != -1 else "/"
    return "/" + url if not url.startswith("/") else url


class _GoRouteParser:
    def __init__(self, file_path: str, content: str, repo_name: str):
        self.file_path = file_path
        self.content = content
        self.repo_name = repo_name
        self.routes: List[RouteNode] = []
        self._rel_path = _get_relative_path(file_path)

    def _make_component_id(self, func_name: str) -> str:
        return f"{self._rel_path}::{func_name}"

    def parse(self):
        self._extract_gin_routes()
        self._extract_mux_routes()
        self._extract_http_server_routes()
        self._extract_client_calls()

    # ---- Gin ----

    def _extract_gin_routes(self):
        """Detect r.GET("/path", handler), group.POST("/path", handler)."""
        for method in _GIN_METHODS:
            pattern = re.compile(
                rf'(\w+)\s*\.\s*{method}\s*\(\s*"([^"]+)"',
                re.MULTILINE,
            )
            for m in pattern.finditer(self.content):
                path = m.group(2)
                lineno = self.content[:m.start()].count("\n") + 1
                func_name = self._find_enclosing_function(m.start())

                http_method = method if method != "ANY" else "GET"
                self.routes.append(RouteNode(
                    route_key=make_route_key(http_method, path),
                    protocol=RouteProtocol.HTTP,
                    method=http_method,
                    path=canonicalize_path(path),
                    role=RouteRole.SERVER,
                    component_id=self._make_component_id(func_name or path),
                    repo_name=self.repo_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    framework="gin",
                ))

    # ---- Chi / Echo / mux ----

    def _extract_mux_routes(self):
        for m in _ROUTER_METHODS_PATTERN.finditer(self.content):
            obj_name = m.group(1)
            method_raw = m.group(2)
            path = m.group(3)

            # Skip if it looks like a client call
            if obj_name in {"http", "client", "httpClient"}:
                continue

            if method_raw in ("HandleFunc", "Handle"):
                method = "GET"  # default for generic handler
            else:
                method = method_raw.upper()

            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_function(m.start())

            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.SERVER,
                component_id=self._make_component_id(func_name or path),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="mux",
            ))

    # ---- net/http server ----

    def _extract_http_server_routes(self):
        for m in _HTTP_SERVER_PATTERN.finditer(self.content):
            path = m.group(1)
            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_function(m.start())
            self.routes.append(RouteNode(
                route_key=make_route_key("GET", path),
                protocol=RouteProtocol.HTTP,
                method="GET",
                path=canonicalize_path(path),
                role=RouteRole.SERVER,
                component_id=self._make_component_id(func_name or path),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="net/http",
            ))

    # ---- Client-side HTTP calls ----

    def _extract_client_calls(self):
        # http.Get("url"), http.Post("url", ...)
        for m in _HTTP_CLIENT_PATTERN.finditer(self.content):
            go_method = m.group(1)
            url = m.group(2)
            path = _strip_url_to_path(url)

            method_map = {"Get": "GET", "Post": "POST", "PostForm": "POST",
                         "Head": "HEAD", "Do": "GET"}
            method = method_map.get(go_method, "GET")

            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_function(m.start())

            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.CLIENT,
                component_id=self._make_component_id(func_name or "unknown"),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="net/http",
            ))

        # http.NewRequest("METHOD", "url", ...)
        for m in _NEW_REQUEST_PATTERN.finditer(self.content):
            method = m.group(1).upper()
            url = m.group(2)
            path = _strip_url_to_path(url)

            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_function(m.start())

            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.CLIENT,
                component_id=self._make_component_id(func_name or "unknown"),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="net/http",
            ))

    # ---- helpers ----

    def _find_enclosing_function(self, pos: int) -> Optional[str]:
        before = self.content[:pos]
        matches = list(re.finditer(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', before))
        return matches[-1].group(1) if matches else None


def extract_go_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract HTTP route nodes from a Go source file."""
    parser = _GoRouteParser(file_path, content, repo_name)
    parser.parse()
    return parser.routes
