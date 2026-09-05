---
title: "WeKnora MCP Server"
type: Entity
description: "WeKnora 配套 MCP 服务器：官方 PyPI 包 tencent-weknora-mcp，29 个工具，stdio/SSE/HTTP 三种传输"
generated: { by: codewiki/5.6.0, at: 2026-09-05T12:00:39Z }
stale_after: 2026-12-04
aliases: [tencent-weknora-mcp, WeKnora MCP 服务器, WeKnora MCP Server]
status: stable
metadata:
  category: "集成"
  source_refs: ["README_CN_2.0"]
  source_refs: ["README_CN_2.0"]
  chunk_refs: ["README_CN_2.0:162", "README_CN_2.0:267-269", "README_CN_2.0:162", "README_CN_2.0:162", "README_CN_2.0:63", "README_CN_2.0:162", "README_CN_2.0:68", "README_CN_2.0:127"]
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
sources:
  - id: README_CN_2.0
    resource: raw/sources/README_CN_2.0.md
    title: "WeKnora (维娜拉) 项目 README 中文版 v0.8.0：企业级 LLM 知识管理框架介绍"
    last_modified: 2026-09-05
---
# WeKnora MCP Server

## 概述

WeKnora MCP Server 是 WeKnora 的配套 MCP 服务器，提供官方 PyPI 包 `tencent-weknora-mcp`，共 29 个工具，支持 stdio / SSE / HTTP 三种传输 [^src:README_CN_2.0:162]。配置说明见 mcp-server/MCP_CONFIG.md [^src:README_CN_2.0:267-269]。

## 公开 API / 工具

- 官方 PyPI 包：`tencent-weknora-mcp` [^src:README_CN_2.0:162]
- 共 29 个工具 [^src:README_CN_2.0:162]
- v0.7.2 迁移到 mcp 2.x 高级 API（MCP Server 1.1.x），新增 `create_knowledge_from_text` 与 `list_shared_knowledge_bases` [^src:README_CN_2.0:63]

## 传输方式

支持 stdio / SSE / HTTP 三种传输 [^src:README_CN_2.0:162]（v0.6.1 起支持 MCP Server 多传输 stdio / SSE / HTTP [^src:README_CN_2.0:68]）。

## 与其他实体的关系

属于 [WeKnora](WeKnora.md) 配套生态；支持 MCP OAuth2 远程服务与会话内 OAuth 授权（工具调用） [^src:README_CN_2.0:127]。注意：本页描述 WeKnora 的 MCP Server，与 CodeWiki 自身的 MCP_Server 模块无关。

## 相关页面

[WeKnora](WeKnora.md) · [README_CN_2.0](../sources/README_CN_2.0.md)