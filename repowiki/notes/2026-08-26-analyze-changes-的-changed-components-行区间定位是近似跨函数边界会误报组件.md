---
type: pitfall
title: analyze_changes 的 changed_components 行区间定位是近似，跨函数边界会误报组件
tags:
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - change_analysis
  source_ref: conversations/conv-user_command-commands-codewiki-变更评估与代码评审（修改后）-请对最近代码变更做影响范围评-2.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:03:02+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:48Z'
---

## 背景

评审变更时 analyze_changes 将 get_checklist 标为变更组件，但实际 diff 未触及该函数——行区间定位跨函数边界产生近似误报。

## 正确做法

changed_components 的变更行命中（行级 diff 定位）是近似而非精确：diff 解析器按行区间归属函数，hint 字符串常量→变量的替换可能被识别为「删除」（deleted_unlocated）。评审时对变更组件需逐一核对实际 diff，不可盲信行区间归属。

## 根因

行级 diff 按行号区间映射到函数/类，函数边界处的行（常量、装饰器附近）容易被归属到相邻函数。
