---
type: pitfall
title: get_prompt 工具参数是 prompt_type 而非 name
tags:
- pitfall
metadata:
  date: 2026-08-15
  related_modules:
  - prompts
  - registry
  source_ref: raw\conv-user_command-commands-codewiki-增量更新-Wiki-请增量更新代码仓库的-Wiki-文档。.md
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:14:29+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:13Z'
reject_reason: consolidated into MCP-Server薄壳架构与参数约定
author: mambo-wang
---

## 背景

调用 `get_prompt` 时用 `name` 参数报错 `Input validation error: 'prompt_type' is a required property`。

## 正确做法

`get_prompt` 接收 `prompt_type` 参数（值形如 `distill-conversations`、`team-memory-hook`），不是 `name`。此坑在多次会话中重复踩到，调用前先读工具描述确认参数名。
