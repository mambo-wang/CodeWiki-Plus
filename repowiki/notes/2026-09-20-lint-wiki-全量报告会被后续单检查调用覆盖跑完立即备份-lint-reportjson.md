---
type: pitfall
title: lint_wiki 全量报告会被后续单检查调用覆盖，跑完立即备份 lint_report.json
tags:
- pitfall
metadata:
  date: 2026-09-20
  confidence_level: weak
  source_session: f880020901b44931982aa724834955df
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-文档质量审计-请对-Wiki-文档执行全面质量审计。按以下-3ed82e.md
  scene: Wiki 文档质量审计
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 11:39:23+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:00:00Z'
---

## 背景

执行 `codewiki/文档质量审计` 命令时，`lint_wiki(checks=["all"])` 的完整报告写入 `.codewiki/workspace/lint_report.json`。审计过程中若再次调用 `lint_wiki`（哪怕只跑单个检查，如 `threshold_drift`），后台进程会用新报告**覆盖**该文件——实测全量报告被一次单检查的空报告覆盖，导致后续分析丢失数据。

## 正确做法

1. 跑完全量 `lint_wiki` 后**立即**把 `lint_report.json` 备份到别处（如 `.scratch/lint-report-backup.json`），再基于备份做分析。
2. 需要验证修复效果时重跑 lint，同样先备份再读。

## Rationale

这是审计实操中真实踩到的坑：报告文件是共享单文件、每次调用都覆写，且覆写可能来自并行的其他进程（如后台蒸馏 worker 触发的 lint），不备份就会静默丢数据。值得留档避免下次审计重复踩坑。

## 适用范围

任何多次调用 lint_wiki 或存在并行 codewiki 进程的场景。
