---
type: pitfall
title: patch 已有 frontmatter 路径缺 aliases 默认键
tags:
- pitfall
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - wiki_doc_writer
  severity: medium
  source_ref: conversations/conv-@command-codewiki-增量更新-Wiki.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:14:16+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:05Z'
reject_reason: 聚合进场景：Wiki页面生成约定与数据结构
---

## 背景

lint 报告 30 页面 missing_aliases，全是历史版本（generator_version 1.0）存量页面。

## 正确做法

三个生成路径（_build_okf_frontmatter、_inject_lightweight_frontmatter、rebuild_index）都写 aliases，唯独 _okf_patch_defaults 只补 type/title/description/generated/status/stale_after，缺 aliases。

## 根因

生成路径与修补路径不一致：新页面不会缺，但 agent 手写 frontmatter 或历史页面编辑时不会补。治本是与生成路径对齐，而非事后 backfill 脚本（治标）。
