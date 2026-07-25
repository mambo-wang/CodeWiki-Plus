"""Cross-service analysis data models.

Route nodes, cross-service links, and workspace topology for
inter-repository API call detection and matching.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RouteProtocol(str, Enum):
    HTTP = "http"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    MQ = "mq"


class RouteRole(str, Enum):
    SERVER = "server"   # 服务端路由处理器
    CLIENT = "client"   # 客户端 HTTP / MQ 调用


class RouteNode(BaseModel):
    """A protocol-agnostic rendezvous point (borrowed from CBM)."""

    route_key: str                         # "__route__POST__/api/orders/{}"
    protocol: RouteProtocol = RouteProtocol.HTTP
    method: Optional[str] = None           # GET, POST, PUT, DELETE, PATCH …
    path: str = ""                         # 规范化后的路径
    role: RouteRole = RouteRole.SERVER
    component_id: str = ""                 # 关联的 Node ID
    repo_name: str = ""
    file_path: str = ""
    line_number: int = 0
    framework: Optional[str] = None        # fastapi, spring, express …
    extra: Dict = Field(default_factory=dict)  # 协议专属扩展字段


class CrossServiceLink(BaseModel):
    """A matched cross-service call between two repositories."""

    route_key: str
    protocol: RouteProtocol = RouteProtocol.HTTP
    method: Optional[str] = None
    path: str = ""
    client_repo: str = ""
    client_component_id: str = ""
    client_function: str = ""
    server_repo: str = ""
    server_component_id: str = ""
    server_function: str = ""
    confidence: float = 1.0                # 1.0 = 精确匹配, <1 = 模糊匹配


class WorkspaceTopology(BaseModel):
    """Aggregated cross-service topology for a workspace."""

    repos: List[str] = Field(default_factory=list)
    routes: List[RouteNode] = Field(default_factory=list)
    links: List[CrossServiceLink] = Field(default_factory=list)
    unmatched_routes: List[RouteNode] = Field(default_factory=list)
