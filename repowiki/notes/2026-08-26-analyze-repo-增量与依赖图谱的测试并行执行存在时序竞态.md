---
type: lesson
title: analyze_repo 增量与依赖图谱的测试并行执行存在时序竞态
tags:
- lesson
metadata:
  date: 2026-08-26
  related_modules:
  - change_analysis
  - review_changes
  source_ref: conversations/conv-@command-codewiki-变更评估与代码评审（修改后）.md
  consolidated_into:
  - wiki/scenarios/代码评审与分析工具方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:02:46+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:47Z'
author: wandering-bug
---

## 背景

执行变更评审时并行跑了 test_review_changes.py 与 analyze_repo 增量，测试 27/28 失败（changed_sources annotated 切片为空）。

## 正确做法

失败疑似因与 analyze_repo 并行——测试执行时图谱还是旧的。图谱更新后重跑即 28/28 全部通过。依赖图谱结果的测试/工具调用不应与图谱重建并行执行，应先完成 analyze_repo 再验证。

## 根因

analyze_repo 重建组件图谱是共享状态写操作，与依赖图谱快照的读操作并行产生时序竞态。
