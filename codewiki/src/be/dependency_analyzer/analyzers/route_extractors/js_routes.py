"""JavaScript / TypeScript route extractor — Express, NestJS, Koa, axios, fetch.

Uses regex-based heuristics on raw source text (the main analyzers
already use tree-sitter; route extraction is a lightweight post-pass).
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

# Express / Koa method names → HTTP methods
_EXPRESS_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "all", "use"}
_HTTP_METHODS_UPPER = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

# Client-side patterns
_CLIENT_PATTERNS = [
    # axios.get("/path"), axios.post("/path", data)
    re.compile(
        r'axios\s*\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*["\'`]([^"\'`]+)["\'`]',
        re.IGNORECASE,
    ),
    # fetch("/path"), fetch("/path", {method: "POST"})
    re.compile(
        r'fetch\s*\(\s*["\'`]([^"\'`]+)["\'`]',
        re.IGNORECASE,
    ),
    # got.get("/path"), ky.get("/path")
    re.compile(
        r'(?:got|ky|node-fetch)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*["\'`]([^"\'`]+)["\'`]',
        re.IGNORECASE,
    ),
]


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


class _JsRouteParser:
    def __init__(self, file_path: str, content: str, repo_name: str, language: str = "javascript"):
        self.file_path = file_path
        self.content = content
        self.lines = content.splitlines()
        self.repo_name = repo_name
        self.language = language
        self.routes: List[RouteNode] = []
        self._rel_path = _get_relative_path(file_path)

    def _make_component_id(self, func_name: str) -> str:
        return f"{self._rel_path}::{func_name}"

    def parse(self):
        self._extract_express_routes()
        self._extract_nestjs_routes()
        self._extract_client_calls()

    # ---- Express / Koa ----

    def _extract_express_routes(self):
        """Detect app.get("/path", handler), router.post("/path", handler), etc."""
        # Build exclusion set: known client libs + detected axios instances
        _excluded_names = {"axios", "got", "ky", "fetch", "window", "document"}

        # Detect axios instance variables: const X = axios.create(...), const X = axios,
        # import X from 'axios'
        for m in re.finditer(
            r'(?:const|let|var)\s+(\w+)\s*=\s*axios(?:\s*\.\s*create\s*\(|\s*[;,\n])',
            self.content,
        ):
            _excluded_names.add(m.group(1))
        for m in re.finditer(
            r'import\s+(\w+)\s+from\s+["\']axios["\']',
            self.content,
        ):
            _excluded_names.add(m.group(1))

        # Common HTTP client instance names that should not be treated as servers
        _excluded_names.update({"http", "api", "client", "request", "service", "instance"})

        # Pattern: (app|router|server|r|api).(get|post|put|delete|patch|use)("/path"
        pattern = re.compile(
            r'(\w+)\s*\.\s*(get|post|put|delete|patch|head|options|use)\s*\(\s*["\'`]([^"\'`]+)["\'`]',
            re.MULTILINE,
        )
        for m in pattern.finditer(self.content):
            obj_name = m.group(1)
            method_raw = m.group(2).lower()
            path = m.group(3)

            # Filter: only common router object names
            if obj_name in _excluded_names:
                continue

            if method_raw == "all":
                method = "GET"  # wildcard, treat as GET for matching
            elif method_raw == "use":
                # middleware, not a route
                continue
            elif method_raw in _HTTP_METHODS_LOWER:
                method = method_raw.upper()
            else:
                continue

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
                framework="express",
            ))

    # ---- NestJS ----

    def _extract_nestjs_routes(self):
        """Detect @Get("/path"), @Post("/path"), @Controller("/prefix") decorators."""
        # @Get("/path")  or  @Post()
        decorator_pattern = re.compile(
            r'@(Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*(?:["\'`]([^"\'`]*)["\'`])?\s*\)',
            re.MULTILINE,
        )
        for m in decorator_pattern.finditer(self.content):
            method = m.group(1).upper()
            path = m.group(2) or ""

            # Try to prepend @Controller prefix
            controller_prefix = self._find_controller_prefix(m.start())
            if controller_prefix:
                path = controller_prefix.rstrip("/") + "/" + path.lstrip("/")

            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_function(m.start())

            self.routes.append(RouteNode(
                route_key=make_route_key(method, path or "/"),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path or "/"),
                role=RouteRole.SERVER,
                component_id=self._make_component_id(func_name or path),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="nestjs",
            ))

    # ---- Client-side HTTP calls ----

    def _extract_client_calls(self):
        """Detect axios.get("/url"), fetch("/url"), etc."""

        # axios / got / ky patterns
        for pattern in _CLIENT_PATTERNS:
            for m in pattern.finditer(self.content):
                groups = m.groups()
                if len(groups) == 2:
                    # axios.method("url") or got.method("url")
                    method = groups[0].upper()
                    url = groups[1]
                elif len(groups) == 1:
                    # fetch("url")
                    url = groups[0]
                    method = "GET"  # default, might be overridden in options
                    # Check for method in nearby options object
                    context_end = min(len(self.content), m.end() + 200)
                    context = self.content[m.start():context_end]
                    method_match = re.search(
                        r'method\s*:\s*["\'`](\w+)["\'`]', context
                    )
                    if method_match:
                        method = method_match.group(1).upper()
                else:
                    continue

                path = _strip_url_to_path(url)
                if not path or len(path) < 2:
                    continue

                lineno = self.content[:m.start()].count("\n") + 1
                func_name = self._find_enclosing_function(m.start())

                framework = "axios"
                if "fetch" in m.group(0):
                    framework = "fetch"
                elif "got" in m.group(0) or "ky" in m.group(0):
                    framework = "got"

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
                    framework=framework,
                ))

    # ---- helpers ----

    def _find_enclosing_function(self, pos: int) -> Optional[str]:
        before = self.content[:pos]
        # JS/TS function patterns:
        #   group 1: function name(
        #   group 2: const/let/var name = <function> (arrow fn or function keyword)
        #   group 3: name(...) {  (method shorthand)
        #   group 4: async name(
        # Group 2 must NOT match plain variable assignments like `const res = await ...`;
        # only match when RHS is a function definition (has `=>` or `function` keyword).
        matches = list(re.finditer(
            r'(?:function\s+(\w+)'
            r'|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\b|(?:\([^)]*\)|\w+)\s*=>)'
            r'|(\w+)\s*\([^)]*\)\s*\{'
            r'|async\s+(\w+)\s*\()',
            before,
        ))
        if matches:
            last = matches[-1]
            return last.group(1) or last.group(2) or last.group(3) or last.group(4)
        return None

    def _find_controller_prefix(self, pos: int) -> str:
        """Find @Controller("/prefix") in the file."""
        m = re.search(r'@Controller\s*\(\s*["\'`]([^"\'`]*)["\'`]\s*\)', self.content[:pos])
        return m.group(1) if m else ""


_HTTP_METHODS_LOWER = {m.lower() for m in _HTTP_METHODS_UPPER}


def extract_js_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract HTTP route nodes from a JavaScript source file."""
    parser = _JsRouteParser(file_path, content, repo_name, "javascript")
    parser.parse()
    return parser.routes


def extract_ts_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract HTTP route nodes from a TypeScript source file."""
    parser = _JsRouteParser(file_path, content, repo_name, "typescript")
    parser.parse()
    return parser.routes
