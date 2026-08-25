---
type: pitfall
title: untracked 新文件不在分析图谱内，review_changes changed_sources 切片为空
tags:
- pitfall
aliases:
- review_changes untracked
- changed_sources 为空
- 新文件不在分析图谱
metadata:
  date: 2026-08-25
  related_modules:
  - mcp
  related_components:
  - codewiki/mcp/tools/review_changes.py
  - codewiki/mcp/tools/analysis.py
  severity: medium
  root_cause: 新文件未纳入分析图谱（analyze_repo 增量），prepare 无法对其做变更函数切片
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 15:55:10+00:00
stale_after: '2027-02-21'
verified:
- by: human:mambo-wang
  at: '2026-08-25T15:55:20Z'
---

## 背景

用 review_changes 评审包含新增文件（untracked）的变更时，上下文包的 file_level_changes 将新文件标注为 "untracked file not in analysis graph"，对应 changed_sources annotated 为空，评审目标缺失。

## 现象

- 新增 review_changes.py / review_checklist.py / 测试文件时，prepare 产出的 changed_components 只有已跟踪组件，核心新文件不在评审目标内。
- 曾导致测试失败（changed_sources annotated 为空），analyze_repo 增量更新图谱后恢复。

## 根因

新文件在 analyze_repo 之前未纳入分析图谱，prepare 无法对新文件做变更函数切片。

## 正确做法

1. 对 untracked 新文件，先运行 analyze_repo（incremental）把文件纳入图谱，再执行 review_changes prepare。
2. 工具侧改进方向：prepare 对 untracked 新文件提示先增量分析，或将 untracked 文件全文纳入 changed_sources 而非仅行切片。
