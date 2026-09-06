---
type: decision
title: frontmatter deep module 重构四决策：路由收进 module、原地扩展、字节级兼容、先 reader 后 writer
tags:
- decision
metadata:
  date: 2026-08-24
  related_modules:
  - wiki_doc_writer
  - frontmatter
  - architecture-review
  severity: medium
  source_ref: conversations/conv-对-CodeWiki-CN-跑-improve-codebase-architecture-skill.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:37+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:17Z'
reject_reason: 聚合进场景：Wiki页面生成约定与数据结构
author: mambo-wang
---

## 背景

improve-codebase-architecture skill 报告 6 候选，第 1 候选 frontmatter+layout deep module 为 Top rec（3 个 writer 8 个 reader 散落，_unquote_fm 类补丁是症状）。

## 决策

grilling 定稿四个决策：Q1 布局路由（PAGE_TYPE_DIRS）收进 module（查表成本零，算路径与拼 frontmatter 从来连着发生）；Q2 原地扩展 frontmatter.py 而非新建 wiki_layout.py（避免第二真源）；Q3 序列化保持字节级兼容（reader 接受所有旧 parser 的并集，round-trip 不变量 parse(render(x))==x 写成测试锁死）；Q4 先 reader 后 writer 两步各自成提交（reader 纯收敛零行为风险，先消灭引号补丁）。

## 根因

deeep module 重构核心是把「散落的同类职责 + 打补丁的症状」收敛为单一所有权，且每一步都必须零行为风险（先收敛读取端，再动写入端）。
