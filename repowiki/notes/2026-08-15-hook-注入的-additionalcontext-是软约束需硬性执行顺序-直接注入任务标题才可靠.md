---
type: lesson
title: hook 注入的 additionalContext 是软约束，需硬性执行顺序 + 直接注入任务标题才可靠
tags:
- lesson
metadata:
  date: 2026-08-15
  task_id: 产品维护
  related_modules:
  - task-memory
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-.meta-task_bindings-这里文件的作用是什么.md
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 15:07:53+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T15:08:30Z'
reject_reason: consolidated into IDE-Hook采集链路方法
---

## 背景

hook 已注入「请立即弹框关联任务」，但 agent 仍先探索代码、回答完问题才补弹框，顺序颠倒。

## 正确做法

`additionalContext` 本质是「给 agent 看的建议」，要让 agent 可靠遵守，需两处加固：

1. **硬性执行顺序**：明确「第一个动作必须是弹框，严禁先探索代码或直接回答」，而非软性的「请立即」。
2. **直接注入任务标题**：把 active 任务标题 + `task_id` 直接打印进 additionalContext，而不是只写「列出任务标题」却不列——否则 agent 还得自己再调 `list_tasks` 多走一步。

## 根因

1. 措辞是软约束，没有明确禁止「先回答」，也没有强制顺序。
2. `_load_active_tasks()` 已读出 active 任务，但 message 里未把标题内联进去，造成信息断层。
