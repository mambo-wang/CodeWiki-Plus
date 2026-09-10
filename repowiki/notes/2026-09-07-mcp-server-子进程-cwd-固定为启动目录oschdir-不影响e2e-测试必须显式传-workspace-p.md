---
type: pitfall
title: MCP server 子进程 cwd 固定为启动目录，os.chdir 不影响：E2E 测试必须显式传 workspace_path/repo_path
tags:
- pitfall
metadata:
  date: 2026-09-07
  related_modules:
  - mcp
  - tests
  severity: medium
  source_ref: conversations/conv-本周改动有点大，请把CODEWIKI-MCP整体测试一遍，重点测试最近一周的改动.md
  scene: MCP 协议层 E2E 测试
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:04:00+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:14Z'
reject_reason: consolidated into MCP-Server薄壳架构与参数约定
---

## 背景

2026-09-02 写协议层 E2E 测试脚本（真实 MCP stdio client 起 server 子进程）时，脚本里 `os.chdir(ws)` 后调 `init_workspace`，结果生成物（bootstrap.sh/ps1、workspace.json、repo-map.md、改 AGENTS.md）全部写到仓库根而非测试工作区，污染了工作区。

## 根因

MCP server 是独立子进程，其 cwd 固定为**脚本启动时**的目录；测试进程内的 `os.chdir` 对子进程无效。

## 正确做法

测试 MCP server 时一律**显式传 `workspace_path` / `repo_path` 参数**，不依赖 cwd；测试后核对生成物落点。污染发生后按生成物清单逐一清理并 `git status` 复核。
