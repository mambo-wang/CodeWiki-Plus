---
type: pitfall
title: load_project_checklist 对 YAML 损坏静默回退 None 无日志，难排查
tags:
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - review_checklist
  source_ref: conversations/conv-@command-codewiki-变更评估与代码评审（修改后）.md
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:02:47+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:48Z'
author: wandering-bug
---

## 背景

review_checklist.py 的 load_project_checklist 对 YAML 缺失/解析失败/结构非法一律静默返回 None，损坏时无法定位原因。

## 正确做法

R-07 已修复：新增模块级 logger，PyYAML 不可用/YAML 解析失败/顶层非 mapping/段非 list/条目缺 id 时分别打 logger.warning（带文件路径与异常原因），保持容错不阻断评审。

## 根因

异常分支全部静默吞掉，未预留日志通道。
