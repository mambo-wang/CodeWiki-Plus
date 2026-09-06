---
type: architecture
title: lint_wiki 支持 fix=true 自愈过期索引
tags:
- architecture
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - wiki_lint
  severity: high
  source_ref: conversations/conv-@command-codewiki-增量更新-Wiki.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:14:12+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:05Z'
reject_reason: 聚合进场景：Wiki页面生成约定与数据结构
author: mambo-wang
---

## 背景

lint 清理时 stale_refs 49 条 error 全部指向 index.md 中引用的失效文件（模块已删但索引未更新）。手工重建可清零但会复发。

## 决策

handle_lint_wiki 新增 fix=true 参数：stale_refs 存在且全部来自 index.md 时自动 rebuild_index 后重跑 stale_refs。注意 Windows 路径分隔符（wiki\\index.md），比较时用 Path().as_posix()。

## 根因

索引只写不清：删除/拒绝笔记的路径没有触发 rebuild_index 的钩子。fix 自愈把检测+修复闭环在工具内，无需用户手工重建。
