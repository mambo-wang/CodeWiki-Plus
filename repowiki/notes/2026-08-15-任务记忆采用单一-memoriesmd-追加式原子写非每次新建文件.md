---
type: architecture
title: 任务记忆采用单一 memories.md 追加式原子写，非每次新建文件
tags:
- architecture
metadata:
  date: 2026-08-15
  related_modules:
  - task_manager
  - distill_conversation
  source_ref: raw\conv-新建session的时候，选择完创建任务后，能不能再弹个框输入任务名称-@d-repos-CodeWiki-CN-.co.md
  consolidated_into:
  - wiki/scenarios/任务记忆系统设计方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:11:39+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:01Z'
reject_reason: consolidated into 任务记忆系统设计方法
author: mambo-wang
---

## 背景

任务记忆（task memories）如何落盘存储。

## 存储布局

一个任务对应**一个** `repowiki/tasks/<task_id>/memories.md`，所有记忆追加式写入同一文件，不是每次蒸馏新建文件。目录结构：`.index.json`（任务索引）+ `<task_id>/task.md`（描述）+ `<task_id>/memories.md`（累积记忆）。

## 追加机制

`handle_add_task_memory` 每次：读旧内容 → `rstrip("\n")` + 拼 `\n\n` → 写临时文件 `.tmp` → `os.replace` 原子替换（`task_manager.py:187-197`）。条与条之间空行分隔，读者永远看不到写了一半的文件。

## 配套

`get_task_context` 聚合 `task.md + memories.md + task_id 关联笔记` 供下一会话恢复上下文。
