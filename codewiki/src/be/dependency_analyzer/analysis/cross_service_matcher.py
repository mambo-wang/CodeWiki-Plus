"""Cross-service matcher — four-phase Route matching engine.

Borrowed from CBM's ``pass_cross_repo.c`` four-phase matching strategy:
  Phase 1: HTTP route matching (exact + fuzzy template fallback)
  Phase 2: MQ producer/consumer matching (Kafka / RabbitMQ / RocketMQ)
  Phase 3: Channel EMITS/LISTENS_ON matching
  Phase 4: gRPC / GraphQL / tRPC matching
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    CrossServiceLink,
    RouteNode,
    RouteProtocol,
    RouteRole,
    WorkspaceTopology,
)

logger = logging.getLogger(__name__)


def path_matches_template(concrete: str, template: str) -> bool:
    """Segment-by-segment comparison: ``{}`` segments match any non-empty segment.

    Borrowed from CBM ``cr_path_matches_template()``.

    Examples::

        /users/123      matches  /users/{}    → True
        /users/123/posts matches  /users/{}    → False (different length)
        /api/orders/42  matches  /api/orders/{} → True
    """
    c_segs = [s for s in concrete.split("/") if s]
    t_segs = [s for s in template.split("/") if s]
    if len(c_segs) != len(t_segs):
        return False
    for c, t in zip(c_segs, t_segs):
        if t == "{}":
            if not c:
                return False
        elif c != t:
            return False
    return True


class CrossServiceMatcher:
    """Aggregate routes from multiple repositories and find cross-service links."""

    def __init__(self):
        # repo_name → list[RouteNode]
        self._repo_routes: Dict[str, List[RouteNode]] = {}

    def add_repo_routes(self, repo_name: str, routes: List[RouteNode]):
        """Register one repository's routes for matching."""
        self._repo_routes[repo_name] = routes

    def match(self) -> WorkspaceTopology:
        """Run all matching phases and return the workspace topology."""
        all_routes: List[RouteNode] = []
        for routes in self._repo_routes.values():
            all_routes.extend(routes)

        links: List[CrossServiceLink] = []

        # Route keys that participated in any match (client and server side).
        # Fuzzy matches store the *server* template key on the link, so the
        # client's concrete route_key must be tracked separately here —
        # otherwise matched client routes would show up as unmatched.
        matched_keys: Set[str] = set()

        # Phase 1: HTTP routes
        links.extend(self._match_http_routes(matched_keys))

        # Phase 2: MQ (populated when mq_patterns are used)
        links.extend(self._match_mq_routes(matched_keys))

        # Phase 3-4: placeholders for future expansion
        # links.extend(self._match_channels())
        # links.extend(self._match_typed_routes())

        # Compute unmatched routes
        for link in links:
            matched_keys.add(link.route_key)

        unmatched = [
            r for r in all_routes
            if r.route_key not in matched_keys
        ]

        return WorkspaceTopology(
            repos=sorted(self._repo_routes.keys()),
            routes=all_routes,
            links=links,
            unmatched_routes=unmatched,
        )

    # ---- Phase 1: HTTP ----

    def _match_http_routes(self, matched_keys: Set[str]) -> List[CrossServiceLink]:
        """Match HTTP client routes to server routes across repositories."""
        links: List[CrossServiceLink] = []

        # Build server index: route_key → list[(repo_name, RouteNode)]
        server_index: Dict[str, List[Tuple[str, RouteNode]]] = defaultdict(list)
        for repo_name, routes in self._repo_routes.items():
            for route in routes:
                if route.protocol == RouteProtocol.HTTP and route.role == RouteRole.SERVER:
                    server_index[route.route_key].append((repo_name, route))

        # Bucket server templates by path segment count so fuzzy matching
        # only compares candidates of the same length (avoids O(clients×servers)).
        fuzzy_index: Dict[int, List[Tuple[str, str, RouteNode]]] = defaultdict(list)
        for srv_key, srv_entries in server_index.items():
            for srv_repo, srv_route in srv_entries:
                seg_count = len([s for s in srv_route.path.split("/") if s])
                fuzzy_index[seg_count].append((srv_key, srv_repo, srv_route))

        # Iterate client routes and look up servers
        for repo_name, routes in self._repo_routes.items():
            for route in routes:
                if route.protocol != RouteProtocol.HTTP or route.role != RouteRole.CLIENT:
                    continue

                # Exact match
                servers = server_index.get(route.route_key)
                if servers:
                    for srv_repo, srv_route in servers:
                        if srv_repo == repo_name:
                            continue  # skip intra-repo
                        links.append(CrossServiceLink(
                            route_key=route.route_key,
                            protocol=RouteProtocol.HTTP,
                            method=route.method,
                            path=route.path,
                            client_repo=repo_name,
                            client_component_id=route.component_id,
                            client_function=route.component_id.split("::")[-1] if "::" in route.component_id else "",
                            server_repo=srv_repo,
                            server_component_id=srv_route.component_id,
                            server_function=srv_route.component_id.split("::")[-1] if "::" in srv_route.component_id else "",
                            confidence=1.0,
                        ))
                    continue

                # Fuzzy template match: try matching concrete path against server templates
                fuzzy = self._fuzzy_match(route, fuzzy_index)
                if fuzzy:
                    links.extend(fuzzy)
                    # Record the client's own concrete route_key as matched
                    matched_keys.add(route.route_key)

        # Deduplicate
        seen: Set[str] = set()
        deduped: List[CrossServiceLink] = []
        for link in links:
            key = f"{link.client_repo}:{link.client_component_id}→{link.server_repo}:{link.server_component_id}:{link.route_key}"
            if key not in seen:
                seen.add(key)
                deduped.append(link)

        return deduped

    def _fuzzy_match(
        self,
        client_route: RouteNode,
        fuzzy_index: Dict[int, List[Tuple[str, str, RouteNode]]],
    ) -> List[CrossServiceLink]:
        """Try matching a client's concrete path against server template paths.

        Example: client path ``/users/42`` matches server template ``/users/{}``.
        """
        links: List[CrossServiceLink] = []
        client_repo = client_route.repo_name
        method = client_route.method or "GET"

        seg_count = len([s for s in client_route.path.split("/") if s])
        for srv_key, srv_repo, srv_route in fuzzy_index.get(seg_count, []):
            if srv_repo == client_repo:
                continue
            if srv_route.method and srv_route.method != method:
                continue
            # Try matching client path (concrete) against server path (template)
            if path_matches_template(client_route.path, srv_route.path):
                links.append(CrossServiceLink(
                    route_key=srv_key,
                    protocol=RouteProtocol.HTTP,
                    method=method,
                    path=srv_route.path,
                    client_repo=client_repo,
                    client_component_id=client_route.component_id,
                    client_function=client_route.component_id.split("::")[-1] if "::" in client_route.component_id else "",
                    server_repo=srv_repo,
                    server_component_id=srv_route.component_id,
                    server_function=srv_route.component_id.split("::")[-1] if "::" in srv_route.component_id else "",
                    confidence=0.8,
                ))
        return links

    # ---- Phase 2: MQ ----

    def _match_mq_routes(self, matched_keys: Set[str]) -> List[CrossServiceLink]:
        """Match MQ producer routes to consumer routes across repositories."""
        links: List[CrossServiceLink] = []

        # Build consumer index: route_key → list[(repo_name, RouteNode)]
        consumer_index: Dict[str, List[Tuple[str, RouteNode]]] = defaultdict(list)
        for repo_name, routes in self._repo_routes.items():
            for route in routes:
                if route.protocol == RouteProtocol.MQ and route.role == RouteRole.SERVER:
                    consumer_index[route.route_key].append((repo_name, route))

        # Iterate producer routes
        for repo_name, routes in self._repo_routes.items():
            for route in routes:
                if route.protocol != RouteProtocol.MQ or route.role != RouteRole.CLIENT:
                    continue
                consumers = consumer_index.get(route.route_key)
                if not consumers:
                    continue
                for cons_repo, cons_route in consumers:
                    if cons_repo == repo_name:
                        continue
                    links.append(CrossServiceLink(
                        route_key=route.route_key,
                        protocol=RouteProtocol.MQ,
                        method=None,
                        path=route.path,
                        client_repo=repo_name,
                        client_component_id=route.component_id,
                        client_function=route.component_id.split("::")[-1] if "::" in route.component_id else "",
                        server_repo=cons_repo,
                        server_component_id=cons_route.component_id,
                        server_function=cons_route.component_id.split("::")[-1] if "::" in cons_route.component_id else "",
                        confidence=1.0,
                    ))

        return links
