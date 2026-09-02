---
type: architecture
title: task_bindings 只与任务存在性挂钩，不校验活跃/完成状态
tags:
- architecture
metadata:
  date: 2026-08-15
  task_id: 产品维护
  related_modules:
  - task_manager
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-raw-conv-蒸馏的时候是如何判断某个对话时关联到哪个任.md
  consolidated_into:
  - wiki/scenarios/任务记忆系统设计方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:12:25+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:02Z'
reject_reason: consolidated into 任务记忆系统设计方法
author: mambo-wang
---

## 背景

任务会话绑定（`.meta/task_bindings/<session>.json`）的生命周期语义。

## 事实

`task_bindings` 只跟「任务是否存在」挂钩，**不跟 status 挂钩**：

- `set_session_task` 只调 `_find_by_id` 校验任务存在，不检查 `status == active`。
- `complete_task` 完全不碰绑定文件，任务完成后绑定原样残留。
- 只有 `delete_task` 才级联删除指向该任务的绑定文件（**唯一删除路径**）。

## 结论

绑定文件存的是「未被删除的任务」的绑定，而非「只存活跃任务」。这影响 capture 回退盖章语义：采用宽松语义（绑定在就盖章，不校验 `status`），任务完成与否交给 distill 阶段/人工评审把关，与 `query_wiki` 允许「幽灵 task_id」的语义对齐。
