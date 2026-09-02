---
type: pitfall
title: IDE hook 的 SessionEnd envelope 须用 user 角色，system 角色会被 transcript 提取丢弃
tags:
- pitfall
- sessionend
metadata:
  date: 2026-08-15
  related_modules:
  - _ide_hook
  - distill_conversation
  source_ref: raw\conv-review最近两次提交.md
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:11:35+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:11Z'
reject_reason: consolidated into IDE-Hook采集链路方法
author: mambo-wang
---

## 背景

修复 `3969dc3` 提交回归时发现：SessionEnd hook 采集的 envelope 内容永远为空。

## 根因

`_ide_hook.py` 生成 SessionEnd envelope 时用 `"role": "system"`，但 `_extract_transcript` 的 `_KEEP_ROLES` 只保留 `user`/`assistant` 角色，导致 system 角色的 envelope 在 transcript 提取阶段被静默丢弃。

## 正确做法

IDE hook 生成的 envelope 必须用 `user` 角色（而非 `system`），才能通过 `_extract_transcript` 的角色过滤。已在 `_ide_hook.py` 修复。

## 教训

任何向 raw transcript 注入内容的路径，都要先确认 `_extract_transcript` 的 `_KEEP_ROLES` 白名单（user/assistant），否则内容会被静默丢弃且无报错。
