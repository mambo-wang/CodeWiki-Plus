---
type: pitfall
title: raw 索引 .index.json 的 task_id 带字面引号导致按任务过滤漏检
tags:
- pitfall
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - capture_conversation
  - distill_conversation
  severity: medium
  source_ref: conversations/conv-@command-codewiki-增量更新-Wiki.md
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:14:19+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:07Z'
reject_reason: 聚合进场景：对话蒸馏管线与raw暂存区
author: mambo-wang
---

## 背景

distill_conversation(mode=prepare, task_id=...) 返回 noop，但 .index.json 中明明有绑定记录。排查发现历史重建索引时写入的 task_id 带字面引号（"产品维护" 存成了 "\"产品维护\""）。

## 正确做法

将 _unq 提升为模块级函数，_rebuild_index 提取 frontmatter 值统一 _unq，pending_raws_by_task 的 index 分支复用 _unq（frontmatter fallback 分支早已去引号）。修复后用新逻辑重建 .index.json 清零脏数据。

## 根因

_rebuild_index 用 _peek_frontmatter 未去 YAML 引号，而读取端部分分支去引号、部分不去，两端行为不一致导致按 task_id 过滤漏检。
