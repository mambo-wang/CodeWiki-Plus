---
title: 空间Rbac
type: Concept
description: WeKnora 多空间权限控制：四级角色矩阵 + 资源归属 + 空间审计日志
generated:
  by: codewiki/5.2.0
  at: 2026-08-03 04:55:42+00:00
stale_after: '2027-02-22'
aliases:
- 空间 RBAC
- RBAC
- 多空间权限
metadata:
  source_refs:
  - README_CN
  chunk_refs:
  - README_CN:71
  - README_CN:159
  - README_CN:159
  - README_CN:159
  - README_CN:159
  - README_CN:150
  - README_CN:67
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:14Z'
---
# 空间RBAC

空间 RBAC 是 [WeKnora](../entities/WeKnora.md) 的企业级多空间权限控制能力，于 v0.6.0 引入 。

## 权限模型

- 四级角色矩阵：Owner / Admin / Contributor / Viewer 
- 按知识库的资源归属 
- 每空间审计日志 
- invite-only 准入；无租户预置与受控自助创建工作区；管理员密码重置（会话吊销）；跨空间超级管理员 
- 权限范围 API Key：能力级授权 + 按 KB 限制 + 节流的 last_used 追踪，配套 API 集成调试台  

## 相关页面

[WeKnora](../entities/WeKnora.md)
