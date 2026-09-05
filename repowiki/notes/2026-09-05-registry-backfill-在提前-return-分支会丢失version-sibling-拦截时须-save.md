---
type: pitfall
title: registry backfill 在提前 return 分支会丢失：version_sibling 拦截时须 _save_registry，且任何被算过的条目都要标记
  backfilled
tags:
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - source_ingest
  - registry
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-2.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:35:09+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:37Z'
---

## Background

source_registry 对老条目做相似度指纹惰性 backfill（首次比较时读一次 raw 补算）。

## 缺陷（2026-09-05 实测发现）

1. backfill 只在内存写条目，**`version_sibling` 提前 return 时没走到 `_save_registry`**，下一次导入还得重读盘重算。
2. `backfilled` 标记只记录「成为 best」的条目——被计算过但没胜出的老条目下轮还得重算。

## 正确做法

任何触发 backfill 的路径（含提前 return 的闸门分支）都要保证注册表落盘；只要条目参与了相似度计算就标记 `backfilled`，避免重复读盘。
