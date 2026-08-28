---
type: architecture
title: OKF §7 actor 约定是 codewiki/<version>，旧格式 agent:codewiki/ 已废弃
tags:
- architecture
metadata:
  date: 2026-08-15
  related_modules:
  - config
  - doc_writer
  - knowledge_loop
  source_ref: raw\conv-使用codewiki-mcp扫描生成的代码wiki为什么status是draft.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:16:11+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:06Z'
reject_reason: consolidated into Wiki页面生成约定与数据结构
---

## 背景

修复 `tests/okf_regression_test.py` 的 3 个基线失败时发现：测试断言期望 `agent:codewiki/`，但实现输出 `codewiki/5.2.2`。

## 事实

OKF §7 actor 约定为 `<producer>/<version>`，`actor_id()` 返回 `codewiki/5.2.2`（无 `agent:` 前缀）。旧格式 `agent:codewiki/` 已废弃。

## 教训

测试断言（或 Agent 生成的前端）若仍写 `agent:codewiki/` 即为过时；排查 actor 相关失败时先看 `codewiki/src/config.py` 的 `actor_id()` 实际返回值，不要按旧文档/旧断言臆断。
