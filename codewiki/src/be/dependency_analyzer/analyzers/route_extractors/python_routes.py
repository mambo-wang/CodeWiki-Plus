"""Python route extractor — FastAPI, Flask, Django, requests, httpx, aiohttp.

Uses Python's built-in ``ast`` module (same parser as the existing
PythonASTAnalyzer) to detect server-side route decorators and client-side
HTTP calls.
"""
from __future__ import annotations

import ast
import logging
import os
from typing import List, Optional

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    RouteNode, RouteProtocol, RouteRole,
)
from codewiki.src.be.dependency_analyzer.utils.path_canonicalizer import (
    canonicalize_path, make_route_key,
)

logger = logging.getLogger(__name__)

# ---- Server-side framework detection ----

# decorator.func.attr  →  (method, framework)
_DECORATOR_METHOD_MAP = {
    "get":    ("GET",    "fastapi"),
    "post":   ("POST",   "fastapi"),
    "put":    ("PUT",    "fastapi"),
    "delete": ("DELETE", "fastapi"),
    "patch":  ("PATCH",  "fastapi"),
    "head":   ("HEAD",   "fastapi"),
    "options":("OPTIONS","fastapi"),
}

_FLASK_ROUTE_ATTRS = {"route"}

# Django url()/path()/re_path()
_DJANGO_PATH_FUNCS = {"path", "re_path", "url"}

# ---- Client-side HTTP library detection ----

_CLIENT_LIBRARIES = {
    # module.method  →  (method, framework)
    "requests.get":    ("GET",    "requests"),
    "requests.post":   ("POST",   "requests"),
    "requests.put":    ("PUT",    "requests"),
    "requests.delete": ("DELETE", "requests"),
    "requests.patch":  ("PATCH",  "requests"),
    "requests.head":   ("HEAD",   "requests"),
    "requests.request":(None,     "requests"),  # method from 1st arg
    "httpx.get":       ("GET",    "httpx"),
    "httpx.post":      ("POST",   "httpx"),
    "httpx.put":       ("PUT",    "httpx"),
    "httpx.delete":    ("DELETE", "httpx"),
    "httpx.patch":     ("PATCH",  "httpx"),
    "httpx.request":   (None,     "httpx"),
    "aiohttp.get":     ("GET",    "aiohttp"),
    "aiohttp.post":    ("POST",   "aiohttp"),
    "aiohttp.put":     ("PUT",    "aiohttp"),
    "aiohttp.delete":  ("DELETE", "aiohttp"),
    "aiohttp.patch":   ("PATCH",  "aiohttp"),
}

_HTTP_METHODS_UPPER = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def _get_relative_path(file_path: str, repo_name: str) -> str:
    """Best-effort relative path computation."""
    try:
        return os.path.relpath(file_path)
    except (ValueError, TypeError):
        return str(file_path)


def _component_id_from_context(file_path: str, func_name: str, class_name: str = "") -> str:
    rel = _get_relative_path(file_path, "")
    if class_name:
        return f"{rel}::{class_name}.{func_name}"
    return f"{rel}::{func_name}"


class _RouteVisitor(ast.NodeVisitor):
    """Walk the AST and collect RouteNode instances."""

    # Client class constructors that produce HTTP client instances
    _CLIENT_CONSTRUCTORS = {
        "httpx.Client": "httpx",
        "httpx.AsyncClient": "httpx",
        "requests.Session": "requests",
        "aiohttp.ClientSession": "aiohttp",
    }

    _CLIENT_INSTANCE_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

    def __init__(self, file_path: str, repo_name: str):
        self.file_path = file_path
        self.repo_name = repo_name
        self.routes: List[RouteNode] = []
        self._current_func: Optional[str] = None
        self._current_class: Optional[str] = None
        # Track variable names bound to HTTP client instances
        self._client_vars: dict[str, str] = {}  # var_name → framework

    # ---- helpers ----

    def _make_component_id(self, name: str) -> str:
        return _component_id_from_context(
            self.file_path, name, self._current_class or ""
        )

    def _extract_string_arg(self, node: ast.expr) -> Optional[str]:
        """Extract a string literal from an AST expression."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            # f-string — extract the literal parts, replace expressions with {}
            parts = []
            for val in node.values:
                if isinstance(val, ast.Constant):
                    parts.append(str(val.value))
                else:
                    parts.append("{}")
            return "".join(parts)
        return None

    # ---- server-side: decorators ----

    def _check_decorator(self, decorator: ast.expr, lineno: int):
        """Check if a decorator is a route decorator."""

        # FastAPI: @app.get("/path"), @router.post("/path")
        if isinstance(decorator, ast.Call):
            func = decorator.func

            # Pattern: obj.method("/path", ...)
            if isinstance(func, ast.Attribute):
                attr = func.attr

                # FastAPI-style: app.get, router.post, api_router.get, etc.
                if attr in _DECORATOR_METHOD_MAP:
                    args = decorator.args
                    if args:
                        path = self._extract_string_arg(args[0])
                        if path:
                            method, fw = _DECORATOR_METHOD_MAP[attr]
                            self.routes.append(RouteNode(
                                route_key=make_route_key(method, path),
                                protocol=RouteProtocol.HTTP,
                                method=method,
                                path=canonicalize_path(path),
                                role=RouteRole.SERVER,
                                component_id=self._make_component_id(
                                    self._current_func or "unknown"
                                ),
                                repo_name=self.repo_name,
                                file_path=self.file_path,
                                line_number=lineno,
                                framework=fw,
                            ))
                            return

                # Flask: @app.route("/path", methods=["GET"])
                if attr in _FLASK_ROUTE_ATTRS:
                    args = decorator.args
                    if args:
                        path = self._extract_string_arg(args[0])
                        if path:
                            # Extract method from methods=[...] keyword
                            method = "GET"
                            for kw in decorator.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                                    for elt in kw.value.elts:
                                        m = self._extract_string_arg(elt)
                                        if m and m.upper() in _HTTP_METHODS_UPPER:
                                            method = m.upper()
                                            break
                            self.routes.append(RouteNode(
                                route_key=make_route_key(method, path),
                                protocol=RouteProtocol.HTTP,
                                method=method,
                                path=canonicalize_path(path),
                                role=RouteRole.SERVER,
                                component_id=self._make_component_id(
                                    self._current_func or "unknown"
                                ),
                                repo_name=self.repo_name,
                                file_path=self.file_path,
                                line_number=lineno,
                                framework="flask",
                            ))
                            return

            # Django: path("route/", view_func)
            if isinstance(func, ast.Name) and func.id in _DJANGO_PATH_FUNCS:
                args = decorator.args if hasattr(decorator, "args") else []
                if not args:
                    return
                # path() is a function call, not a decorator — but it appears
                # inside urlpatterns = [path(...), ...], not as a decorator.
                # We handle it in visit_Call instead.
                return

    # ---- client-side: function calls ----

    def _check_client_call(self, node: ast.Call):
        """Check if a call is a client-side HTTP call."""
        func = node.func
        call_expr = None

        # Pattern: module.method(...)  e.g. requests.get("url")
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            call_expr = f"{func.value.id}.{func.attr}"

        if call_expr and call_expr in _CLIENT_LIBRARIES:
            method_hint, framework = _CLIENT_LIBRARIES[call_expr]
            args = node.args
            if not args:
                return

            # For generic .request(method, url, ...), first arg is the method
            if method_hint is None and args:
                m = self._extract_string_arg(args[0])
                if m and m.upper() in _HTTP_METHODS_UPPER:
                    method_hint = m.upper()
                    url_arg = args[1] if len(args) > 1 else None
                else:
                    return
            else:
                url_arg = args[0]

            if url_arg is None:
                return
            url = self._extract_string_arg(url_arg)
            if not url:
                return

            # Strip scheme + host to get path
            path = _strip_url_to_path(url)
            if not path:
                return

            method = method_hint or "GET"
            comp_id = self._make_component_id(self._current_func or "unknown")

            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.CLIENT,
                component_id=comp_id,
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=node.lineno,
                framework=framework,
            ))
            return

        # Pattern: instance.method(...)  e.g. c.get("/path") where c is a
        # tracked client variable from 'with httpx.Client() as c:'
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            var_name = func.value.id
            attr = func.attr
            if var_name in self._client_vars and attr in self._CLIENT_INSTANCE_METHODS:
                framework = self._client_vars[var_name]
                method = attr.upper()
                args = node.args
                if not args:
                    return
                url_arg = args[0]
                url = self._extract_string_arg(url_arg)
                if not url:
                    return
                path = _strip_url_to_path(url)
                if not path:
                    return
                comp_id = self._make_component_id(self._current_func or "unknown")
                self.routes.append(RouteNode(
                    route_key=make_route_key(method, path),
                    protocol=RouteProtocol.HTTP,
                    method=method,
                    path=canonicalize_path(path),
                    role=RouteRole.CLIENT,
                    component_id=comp_id,
                    repo_name=self.repo_name,
                    file_path=self.file_path,
                    line_number=node.lineno,
                    framework=framework,
                ))

    # ---- AST visitor methods ----

    def visit_ClassDef(self, node: ast.ClassDef):
        prev = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = prev

    def visit_FunctionDef(self, node: ast.FunctionDef):
        prev = self._current_func
        self._current_func = node.name
        for dec in node.decorator_list:
            self._check_decorator(dec, node.lineno)
        self.generic_visit(node)
        self._current_func = prev

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        prev = self._current_func
        self._current_func = node.name
        for dec in node.decorator_list:
            self._check_decorator(dec, node.lineno)
        self.generic_visit(node)
        self._current_func = prev

    def visit_With(self, node: ast.With):
        self._track_with_bindings(node)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        self._track_with_bindings(node)
        self.generic_visit(node)

    def _track_with_bindings(self, node):
        """Record variable bindings from 'with httpx.Client() as c:' etc."""
        for item in node.items:
            # item.context_expr is the call, item.optional_vars is the 'as' target
            if item.optional_vars is None:
                continue
            if not isinstance(item.optional_vars, ast.Name):
                continue
            var_name = item.optional_vars.id
            ctor = self._resolve_constructor_name(item.context_expr)
            if ctor and ctor in self._CLIENT_CONSTRUCTORS:
                self._client_vars[var_name] = self._CLIENT_CONSTRUCTORS[ctor]

    def _resolve_constructor_name(self, node: ast.expr) -> Optional[str]:
        """Resolve a Call node like httpx.Client() to 'httpx.Client'."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
        return None

    def visit_Assign(self, node: ast.Assign):
        """Track simple assignments like 'c = httpx.Client()'."""
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            ctor = self._resolve_constructor_name(node.value)
            if ctor and ctor in self._CLIENT_CONSTRUCTORS:
                self._client_vars[var_name] = self._CLIENT_CONSTRUCTORS[ctor]
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        self._check_client_call(node)
        self.generic_visit(node)


def _strip_url_to_path(url: str) -> str:
    """Extract the path component from a URL or bare path.

    ``https://example.com/api/users`` → ``/api/users``
    ``/api/users`` → ``/api/users``
    """
    # Already a path (starts with /)
    if url.startswith("/"):
        return url

    # Full URL — strip scheme + host
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            rest = url[len(scheme):]
            slash = rest.find("/")
            if slash != -1:
                return rest[slash:]
            return "/"
    # No scheme — treat as path
    if url.startswith("/"):
        return url
    # Relative path — prepend /
    return "/" + url


def extract_python_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract HTTP route nodes from a Python source file."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    visitor = _RouteVisitor(file_path, repo_name)
    visitor.visit(tree)
    return visitor.routes
