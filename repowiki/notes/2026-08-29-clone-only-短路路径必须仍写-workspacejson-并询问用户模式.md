---
type: pitfall
title: clone-only 短路路径必须仍写 workspace.json 并询问用户模式
tags:
- pitfall
metadata:
  date: 2026-08-29
  task_id: 多仓工作区
  related_modules:
  - workspace_bootstrap
  - init_workspace
  severity: medium
  source_ref: conversations/conv-工作区已有部分初始化痕迹（bootstrap.ps1-登记了业务仓、.gitignore-已排除等）时，init_wor.md
  scene: 多仓工作区初始化缺陷修复
  consolidated_into:
  - wiki/scenarios/多仓工作区初始化与增量分析.md
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:03:54+00:00
stale_after: '2027-02-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-29T15:14:32Z'
---

## Background

实现「痕迹齐备时 clone-only 短路」后，发现初始化时没有问用户模式，也没有生成 repowiki/.meta/workspace.json。

## Pitfall

clone-only 短路路径跳过了完整 init_workspace 流程，但也跳过了写 workspace.json 和询问用户模式这两个必要步骤。任何对 init 流程的短路优化都必须确保关键产物（workspace.json、模式选择）不被遗漏。

## Recovery

排查 clone-only 路径的实际状态，补回缺失的 workspace.json 写入和用户模式询问逻辑。后续对 init 流程做任何优化时，应列出所有必要产物作为 checklist。
