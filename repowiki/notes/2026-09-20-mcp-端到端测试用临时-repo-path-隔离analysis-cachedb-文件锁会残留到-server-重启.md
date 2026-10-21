---
type: procedure
title: MCP 端到端测试用临时 repo_path 隔离，analysis_cache.db 文件锁会残留到 server 重启
tags:
- codewiki
- procedure
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 他山之石
  source_session: 8963b3e1a98b4608a6ab4e05850d2702
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-c29f4b.md
  scene: MCP 端到端测试
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 11:37:39+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:00:03Z'
---

## 背景

对 CodeWiki MCP 工具（ingest_note、lint_wiki 等）做端到端验证时，直接用真实仓库的 `repo_path` 会把测试笔记写进真实 `repowiki/`，污染知识库并触发 auto_push 推送。

## 正确做法

1. 用临时目录做 repo_path（如 `D:\repos\CodeWiki-Plus\.scratch\mcp-test`），工具会在其下自建 `repowiki/` 结构，测试笔记、lint 检查全部隔离在该目录内。
2. 测试完成后清理临时目录。

## 坑：analysis_cache.db 文件锁残留

MCP server 进程会持有临时目录下 `.codewiki/analysis_cache.db` 的文件锁，测试结束时 `Remove-Item -Recurse -Force` 删不掉该缓存文件（notes 等其余文件可删）。不影响测试结论；残留缓存等 MCP server 重启后即可删除，不必强求当场清干净。

## Rationale

这是 ADR-0013 落地后实际跑通的 MCP 层验证方法（stable 无 reason 拒绝、reason/evidence 落章、threshold_drift 检查注册），隔离模式与文件锁行为都是非显而易见的实操细节，下次做 MCP 端到端测试可直接复用。

## 适用范围

任何需要真调 codewiki MCP 工具验证行为的场景（单测覆盖不到 dispatch/schema 校验层时）。
