---
type: decision
title: 工作区痕迹齐备时跳过 init_workspace，直接跑 bootstrap 脚本补 clone
tags:
- codewiki
- decision
metadata:
  date: 2026-08-29
  task_id: 多仓工作区
  related_modules:
  - workspace_bootstrap
  - init_workspace
  severity: high
  source_ref: conversations/conv-工作区已有部分初始化痕迹（bootstrap.ps1-登记了业务仓、.gitignore-已排除等）时，init_wor.md
  scene: 多仓工作区初始化流程优化
  consolidated_into:
  - wiki/scenarios/多仓工作区初始化与增量分析.md
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:03:49+00:00
stale_after: '2027-08-29'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-29T15:14:32Z'
---

## Background

当工作区已有部分初始化痕迹（bootstrap.ps1/.sh 已登记业务仓、.gitignore 已排除 /codewiki-plus/、repowiki/ 骨架存在），但 .meta/workspace.json 不存在时，handle_init_workspace 每次调用都跑全流程（重新生成 wiki tree、强制更新 AGENTS.md 约定块、重写 CodeWiki 块），而对痕迹齐备的工作区真正有用的只有 clone 业务仓。

## Decision

prompt 改为「痕迹齐备时直接跑 bootstrap 脚本补 clone，不调 init_workspace」。工具侧 clone-only 路径保留作误调兜底。同步更新 registry 描述与文档，prompt 渲染测试断言旧文案（auto-clone）也同步更新。

## Rationale

bootstrap 脚本本身读同一张登记表、也能补 clone，不必走 MCP 往返。initialize_wiki_tree 基本幂等（只补缺），但 write_workspace_conventions 是强制覆盖，重复执行有副作用。

## 验证

ruff 过、受影响 98 个测试过，全量确认基线。
