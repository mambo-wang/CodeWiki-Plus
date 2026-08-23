---
type: pitfall
title: capture_conversation 的 task_id 需显式传入，绑定文件曾不被自动消费（已加回退修复）
tags:
- pitfall
metadata:
  date: 2026-08-15
  task_id: 产品维护
  related_modules:
  - capture_conversation
  - task_manager
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-raw-conv-蒸馏的时候是如何判断某个对话时关联到哪个任.md
  consolidated_into:
  - wiki/scenarios/任务记忆系统设计方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:12:24+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:11Z'
reject_reason: consolidated into 任务记忆系统设计方法
---

## 背景

用户发现 raw 文件 frontmatter 里没有 `task_id` 字段，但之前已通过 `set_session_task` 建立过会话绑定。

## 根因

`capture_conversation` 的 `task_id` 是从调用参数 `arguments.get("task_id")` 读的，代码全程没有「按 `source_session_id` 反查 `repowiki/.meta/task_bindings/` 绑定文件」的逻辑。而 `task_manager.py` docstring 和 `registry.py` 的 `set_session_task` 描述却写「绑定会被 capture_conversation 消费」——**文档与实现不一致**，导致 Agent 建了绑定但采集时没传 `task_id` 时，raw 丢失任务归属。

## 修复

新增 `_resolve_task_from_binding(output_dir, source_session_id)` helper，在 `_content_hash` 之前插入回退：未显式传 `task_id` 但传了 `source_session_id` 时，自动读绑定文件盖章。关键设计约束：

- 回退必须放在 `_content_hash` **之前**（`task_id` 参与去重指纹，放错位置会破坏去重/会话覆盖语义）。
- **不能 import `task_manager`**：它反向 import 了本模块的 `_resolve_output_dir`/`_slugify`（循环依赖），所以目录名 `output_dir/.meta/task_bindings/` 有意重复一份并加注释约束同步。
- 显式 `task_id` 永远优先（向后兼容）；envelope 场景（`source_session_id` 为空）不触发回退，自动安全。

## 教训

任何向 raw transcript 盖章/标注的路径，都要先确认该信息是否真的被下游消费，以及来源是否可观测（修复同时新增了 `task_source` 字段用于排查「task_id 从哪来」）。
