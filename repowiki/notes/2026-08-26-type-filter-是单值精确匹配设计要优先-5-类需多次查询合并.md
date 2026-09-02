---
type: lesson
title: type_filter 是单值精确匹配，设计要「优先 5 类」需多次查询合并
tags:
- lesson
metadata:
  date: 2026-08-26
  related_modules:
  - wiki_search
  - review_changes
  source_ref: conversations/conv-@command-codewiki-变更评估与代码评审（修改后）.md
  consolidated_into:
  - wiki/scenarios/代码评审与分析工具方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:02:45+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:46Z'
author: wandering-bug
---

## 背景

设计文档 §4.3-C 要求 module_knowledge 轴优先返回 pitfall/lesson/architecture/decision/known_issue 五类历史踩坑笔记。但 type_filter 参数是单值精确匹配（page_type != type_filter 即跳过），bm25_search 与 _query_mode_* 均如此。

## 结论

1) 不传 type_filter 时模块知识轴 top-5 可能被高相关度的普通 docs 页面占满，挤掉真正该看的踩坑笔记——召回不够精准，但不导致评审结果错误（已有两层兜底：_note_metadata 回传 type、_rel_key 按 related_modules 交集排序）。
2) 补单个 type_filter 值只会丢更多类型，要按设计实现需按类型分多次查询再合并去重，查询次数翻 5 倍。
3) 因此单修 R-01 性价比低，必须与 R-05 并行化捆绑做。

## 根因

单值 filter 参数与「多类型优先」的设计需求不匹配，实现时未按多次查询+合并去重的思路设计。
