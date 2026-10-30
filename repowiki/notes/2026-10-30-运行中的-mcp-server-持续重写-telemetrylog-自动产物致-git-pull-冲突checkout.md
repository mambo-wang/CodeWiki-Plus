---
type: pitfall
title: "运行中的 MCP server 持续重写 telemetry/log 自动产物致 git pull 冲突：checkout 无效，用 git stash push 指定路径后丢弃"
tags: ["pitfall"]
metadata:
  date: 2026-10-30
  confidence_level: weak
  task_id: 发版本
  source_session: "5dee23d20a5649afa4429fdc1594bc07"
  related_modules: ["repowiki"]
  severity: medium
  source_ref: "conversations/conv-@command-windows-python-release-发布版本5.16.3.md"
  scene: "产品维护"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.5, at: 2026-10-30T03:28:58Z }
stale_after: 2027-04-28
origin: conversation

---

## 现象

`git pull` 因本地 `repowiki/.meta/telemetry/*.jsonl`、`repowiki/wiki/log-*.md` 有未提交改动而与远端冲突。这些是运行中的 MCP server 持续重写的自动产物，`git checkout -- <file>` 恢复后立刻又出现新改动，治标不治本。

## 正确做法

`git stash push -m "auto-products-before-pull" -- <自动产物路径>` 后再 pull，stash 直接丢弃（自动产物以远端为准，本地改动无保留价值）。

## Rationale

自动产物与远端冲突时取远端即可；运行中的进程会持续产生本地噪音改动，stash 一次性清掉后 pull 才能 fast-forward 成功。
