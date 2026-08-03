---
title: "空间Rbac"
type: Concept
description: "WeKnora 多空间权限控制：四级角色矩阵 + 资源归属 + 空间审计日志"
generated: { by: codewiki/5.2.0, at: 2026-08-03T04:55:42Z }
stale_after: 2026-11-01
aliases: [空间 RBAC, RBAC, 多空间权限]
source_refs: ["README_CN"]
chunk_refs: ["README_CN:71", "README_CN:159", "README_CN:159", "README_CN:159", "README_CN:159", "README_CN:150", "README_CN:67"]
sources:
  - id: README_CN
    resource: raw/sources/README_CN.md
    title: "WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程"
    last_modified: 2026-08-03
---
# 空间RBAC

空间 RBAC 是 [WeKnora](../entities/WeKnora.md) 的企业级多空间权限控制能力，于 v0.6.0 引入 [^src:README_CN:71]。

## 权限模型

- 四级角色矩阵：Owner / Admin / Contributor / Viewer [^src:README_CN:159]
- 按知识库的资源归属 [^src:README_CN:159]
- 每空间审计日志 [^src:README_CN:159]
- invite-only 准入；无租户预置与受控自助创建工作区；管理员密码重置（会话吊销）；跨空间超级管理员 [^src:README_CN:159]
- 权限范围 API Key：能力级授权 + 按 KB 限制 + 节流的 last_used 追踪，配套 API 集成调试台 [^src:README_CN:150] [^src:README_CN:67]

## 相关页面

[WeKnora](../entities/WeKnora.md)
