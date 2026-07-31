"""Java route extractor — Spring MVC, JAX-RS, Feign, RestTemplate, WebClient.

Uses Tree-sitter Java AST (same parser as the existing Java analyzer)
to detect server-side annotations and client-side HTTP calls.
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional, Tuple

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    RouteNode, RouteProtocol, RouteRole,
)
from codewiki.src.be.dependency_analyzer.utils.path_canonicalizer import (
    canonicalize_path, make_route_key,
)

logger = logging.getLogger(__name__)

# Spring MVC annotations
_SPRING_MAPPING_ANNOTATIONS = {
    "GetMapping":    "GET",
    "PostMapping":   "POST",
    "PutMapping":    "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping":  "PATCH",
}

_JAXRS_METHOD_ANNOTATIONS = {
    "GET":    "GET",
    "POST":   "POST",
    "PUT":    "PUT",
    "DELETE": "DELETE",
    "PATCH":  "PATCH",
    "HEAD":   "HEAD",
    "OPTIONS":"OPTIONS",
}

# Client-side method patterns
_REST_TEMPLATE_METHODS = {
    "getForObject":      "GET",
    "getForEntity":      "GET",
    "postForObject":     "POST",
    "postForEntity":     "POST",
    "put":               "PUT",
    "delete":            "DELETE",
    "exchange":          None,  # method from HttpMethod arg
}

_WEBCLIENT_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _get_relative_path(file_path: str) -> str:
    try:
        return os.path.relpath(file_path)
    except (ValueError, TypeError):
        return str(file_path)


def _extract_string_literal(text: str) -> Optional[str]:
    """Extract string content from a quoted Java string literal."""
    text = text.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return text[1:-1]
    return None


def _strip_url_to_path(url: str) -> str:
    if url.startswith("/"):
        return url
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            rest = url[len(scheme):]
            slash = rest.find("/")
            return rest[slash:] if slash != -1 else "/"
    return "/" + url if not url.startswith("/") else url


class _JavaRouteParser:
    """Parse Java source text using regex heuristics (no tree-sitter dependency).

    Falls back to regex pattern matching on the raw source text. This avoids
    importing tree-sitter at the route extractor level (the main analyzer
    already uses it).
    """

    def __init__(self, file_path: str, content: str, repo_name: str):
        self.file_path = file_path
        self.content = content
        self.lines = content.splitlines()
        self.repo_name = repo_name
        self.routes: List[RouteNode] = []
        self._rel_path = _get_relative_path(file_path)

    def _make_component_id(self, func_name: str, class_name: str = "") -> str:
        if class_name:
            return f"{self._rel_path}::{class_name}.{func_name}"
        return f"{self._rel_path}::{func_name}"

    def parse(self):
        self._extract_spring_annotations()
        self._extract_jaxrs_annotations()
        self._extract_feign_clients()
        self._extract_client_calls()

    # ---- Spring MVC ----

    def _extract_spring_annotations(self):
        """Detect @GetMapping, @PostMapping, etc. and @RequestMapping."""
        import re

        # Find class-level @RequestMapping prefix to prepend to method routes
        class_prefix = self._find_class_request_mapping()

        for ann_name, method in _SPRING_MAPPING_ANNOTATIONS.items():
            # @GetMapping("/path")  or  @GetMapping(value = "/path")
            pattern = re.compile(
                rf'@{ann_name}\s*\(\s*(?:value\s*=\s*)?"([^"]+)"',
                re.MULTILINE,
            )
            for m in pattern.finditer(self.content):
                path = m.group(1)
                # Prepend class-level @RequestMapping prefix
                if class_prefix:
                    path = class_prefix.rstrip("/") + "/" + path.lstrip("/")
                lineno = self.content[:m.start()].count("\n") + 1
                func_name = self._find_next_method_name(m.end())
                class_name = self._find_enclosing_class(m.start())
                self.routes.append(RouteNode(
                    route_key=make_route_key(method, path),
                    protocol=RouteProtocol.HTTP,
                    method=method,
                    path=canonicalize_path(path),
                    role=RouteRole.SERVER,
                    component_id=self._make_component_id(func_name, class_name),
                    repo_name=self.repo_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    framework="spring",
                ))

        # @RequestMapping(value="/path", method=RequestMethod.GET)
        # Only emit method-level @RequestMapping as routes; skip class-level ones
        # (class-level is used as prefix above).
        rm_pattern = re.compile(
            r'@RequestMapping\s*\(([^)]+)\)',
            re.MULTILINE,
        )
        for m in rm_pattern.finditer(self.content):
            # Skip class-level @RequestMapping (appears right before class declaration)
            if self._is_class_level_annotation(m.start()):
                continue

            params = m.group(1)
            path = self._extract_param_value(params, "value") or self._extract_param_value(params, "path")
            if not path:
                # Try positional: @RequestMapping("/path")
                path = _extract_string_literal(params.strip())
            if not path:
                continue

            # Prepend class-level prefix for method-level @RequestMapping too
            if class_prefix:
                path = class_prefix.rstrip("/") + "/" + path.lstrip("/")

            method = "GET"  # default
            method_val = self._extract_param_value(params, "method")
            if method_val:
                # RequestMethod.GET → GET,  GET → GET
                for m_upper in _HTTP_METHODS:
                    if m_upper in method_val.upper():
                        method = m_upper
                        break

            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_next_method_name(m.end())
            class_name = self._find_enclosing_class(m.start())
            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.SERVER,
                component_id=self._make_component_id(func_name, class_name),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="spring",
            ))

    # ---- JAX-RS ----

    def _extract_jaxrs_annotations(self):
        import re
        # @Path("/base") on class, @GET/@POST on method
        # Find methods with both @Path and a method annotation
        for ann_name, method in _JAXRS_METHOD_ANNOTATIONS.items():
            pattern = re.compile(rf'@{ann_name}\b', re.MULTILINE)
            for m in pattern.finditer(self.content):
                # Look for @Path near this annotation
                context_start = max(0, m.start() - 200)
                context_end = min(len(self.content), m.end() + 200)
                context = self.content[context_start:context_end]

                path_match = re.search(r'@Path\s*\(\s*"([^"]+)"', context)
                if not path_match:
                    continue
                path = path_match.group(1)
                lineno = self.content[:m.start()].count("\n") + 1
                func_name = self._find_next_method_name(m.end())
                class_name = self._find_enclosing_class(m.start())

                # Prepend class-level @Path if present
                class_path = self._find_class_path(m.start())
                if class_path:
                    path = class_path.rstrip("/") + "/" + path.lstrip("/")

                self.routes.append(RouteNode(
                    route_key=make_route_key(method, path),
                    protocol=RouteProtocol.HTTP,
                    method=method,
                    path=canonicalize_path(path),
                    role=RouteRole.SERVER,
                    component_id=self._make_component_id(func_name, class_name),
                    repo_name=self.repo_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    framework="jaxrs",
                ))

    # ---- Feign clients ----

    def _extract_feign_clients(self):
        import re
        # @FeignClient(name = "service-name") on interface
        # Then @GetMapping/@PostMapping on methods
        if "@FeignClient" not in self.content:
            return
        # Already handled by _extract_spring_annotations since Feign uses same annotations

    # ---- Client-side HTTP calls ----

    # Variable name patterns that indicate Map/collection receivers (not HTTP clients)
    _MAP_RECEIVER_PATTERN = re.compile(
        r'(?:map|Map|hashMap|HashMap|concurrentMap|ConcurrentHashMap|linkedHashMap|'
        r'LinkedHashMap|hashtable|Hashtable|properties|Properties|headers|headersMap|'
        r'config|params|attributes|attrs|cache|registry|store|map\w*|\w+Map)\s*$',
    )

    # Variable name patterns that indicate a RestTemplate / HTTP client receiver
    _HTTP_CLIENT_RECEIVER_PATTERN = re.compile(
        r'(?:restTemplate|RestTemplate|template|httpClient|HttpClient|client|'
        r'restClient|RestClient|http|webClient|WebClient)\s*$',
        re.IGNORECASE,
    )

    def _extract_client_calls(self):
        import re
        # RestTemplate: restTemplate.getForObject("/path", ...)
        for method_name, http_method in _REST_TEMPLATE_METHODS.items():
            pattern = re.compile(
                rf'(\w+)\s*\.\s*{method_name}\s*\(\s*"([^"]+)"',
                re.MULTILINE,
            )
            for m in pattern.finditer(self.content):
                receiver = m.group(1)
                url = m.group(2)

                # For ambiguous methods (put/delete), verify receiver is an HTTP
                # client and not a Map/collection variable.
                if method_name in ("put", "delete"):
                    if self._MAP_RECEIVER_PATTERN.search(receiver):
                        continue
                    if not self._HTTP_CLIENT_RECEIVER_PATTERN.search(receiver):
                        continue

                path = _strip_url_to_path(url)
                lineno = self.content[:m.start()].count("\n") + 1
                func_name = self._find_enclosing_method(m.start())
                class_name = self._find_enclosing_class(m.start())
                method = http_method or "GET"
                self.routes.append(RouteNode(
                    route_key=make_route_key(method, path),
                    protocol=RouteProtocol.HTTP,
                    method=method,
                    path=canonicalize_path(path),
                    role=RouteRole.CLIENT,
                    component_id=self._make_component_id(
                        func_name or "unknown", class_name or ""
                    ),
                    repo_name=self.repo_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    framework="resttemplate",
                ))

        # WebClient: webClient.get().uri("/path")
        wc_pattern = re.compile(
            r'\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*\)\s*\.\s*uri\s*\(\s*"([^"]+)"',
            re.MULTILINE | re.IGNORECASE,
        )
        for m in wc_pattern.finditer(self.content):
            method = m.group(1).upper()
            url = m.group(2)
            path = _strip_url_to_path(url)
            lineno = self.content[:m.start()].count("\n") + 1
            func_name = self._find_enclosing_method(m.start())
            class_name = self._find_enclosing_class(m.start())
            self.routes.append(RouteNode(
                route_key=make_route_key(method, path),
                protocol=RouteProtocol.HTTP,
                method=method,
                path=canonicalize_path(path),
                role=RouteRole.CLIENT,
                component_id=self._make_component_id(
                    func_name or "unknown", class_name or ""
                ),
                repo_name=self.repo_name,
                file_path=self.file_path,
                line_number=lineno,
                framework="webclient",
            ))

    # ---- helpers ----

    def _extract_param_value(self, params: str, key: str) -> Optional[str]:
        import re
        m = re.search(rf'{key}\s*=\s*"([^"]*)"', params)
        return m.group(1) if m else None

    def _find_next_method_name(self, pos: int) -> str:
        """Find the next Java method declaration after *pos*."""
        rest = self.content[pos:pos + 1000]
        m = re.search(
            r'(?:public|private|protected|static|final|abstract|synchronized|\s)+\s+'
            r'[\w<>\[\],\s]+\s+(\w+)\s*\(',
            rest,
        )
        return m.group(1) if m else "unknown"

    def _find_enclosing_class(self, pos: int) -> str:
        import re
        before = self.content[:pos]
        matches = list(re.finditer(r'(?:class|interface)\s+(\w+)', before))
        return matches[-1].group(1) if matches else ""

    def _find_enclosing_method(self, pos: int) -> Optional[str]:
        before = self.content[:pos]
        matches = list(re.finditer(
            r'(?:public|private|protected|static|final|abstract|synchronized|\s)+\s+'
            r'[\w<>\[\],\s]+\s+(\w+)\s*\(',
            before,
        ))
        return matches[-1].group(1) if matches else None

    def _find_class_path(self, pos: int) -> str:
        """Find the @Path annotation on the enclosing class."""
        import re
        before = self.content[:pos]
        # Find last class declaration
        class_matches = list(re.finditer(r'class\s+\w+', before))
        if not class_matches:
            return ""
        class_pos = class_matches[-1].start()
        # Look for @Path before the class
        pre_class = before[max(0, class_pos - 300):class_pos]
        path_match = re.search(r'@Path\s*\(\s*"([^"]+)"', pre_class)
        return path_match.group(1) if path_match else ""

    def _find_class_request_mapping(self) -> str:
        """Find the class-level @RequestMapping value (Spring MVC prefix)."""
        import re
        # Find the first class/interface declaration
        class_match = re.search(r'(?:class|interface)\s+\w+', self.content)
        if not class_match:
            return ""
        class_pos = class_match.start()
        # Look for @RequestMapping in the 500 chars before the class declaration
        pre_class = self.content[max(0, class_pos - 500):class_pos]
        rm_match = re.search(r'@RequestMapping\s*\(([^)]+)\)', pre_class)
        if not rm_match:
            # Also try simple form: @RequestMapping("/path")
            rm_simple = re.search(r'@RequestMapping\s*\(\s*"([^"]+)"', pre_class)
            return rm_simple.group(1) if rm_simple else ""
        params = rm_match.group(1)
        # Try value = "..." or path = "..."
        val_match = re.search(r'(?:value|path)\s*=\s*"([^"]*)"', params)
        if val_match:
            return val_match.group(1)
        # Try positional string literal
        simple = _extract_string_literal(params.strip())
        return simple or ""

    def _is_class_level_annotation(self, pos: int) -> bool:
        """Check if the annotation at *pos* is class-level (before a class/interface decl)."""
        import re
        # Look at the text between this annotation and the next declaration
        after = self.content[pos:pos + 500]
        # If the next significant declaration after the annotation is a class/interface,
        # then this is a class-level annotation
        next_decl = re.search(
            r'(?:public|private|protected|static|final|abstract|\s)*\s*(class|interface)\s+\w+',
            after,
        )
        next_method = re.search(
            r'(?:public|private|protected|static|final|abstract|synchronized|\s)+\s*[\w<>\[\],\s]+\s+\w+\s*\(',
            after,
        )
        if next_decl and (not next_method or next_decl.start() <= next_method.start()):
            return True
        return False


_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def extract_java_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract HTTP route nodes from a Java source file."""
    parser = _JavaRouteParser(file_path, content, repo_name)
    parser.parse()
    return parser.routes
