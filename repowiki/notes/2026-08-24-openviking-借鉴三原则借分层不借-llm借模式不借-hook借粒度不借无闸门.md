---
type: decision
title: OpenViking 借鉴三原则：借分层不借 LLM、借模式不借 hook、借粒度不借无闸门
tags:
- codewiki
- decision
- openviking
metadata:
  date: 2026-08-24
  related_modules:
  - knowledge_loop
  - wiki_index
  - OpenViking-调研与借鉴分析
  severity: medium
  source_ref: conversations/conv-调研-OpenViking-对比-CodeWiki.md
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:50+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:18Z'
reject_reason: 聚合进场景：对话蒸馏管线与raw暂存区
author: mambo-wang
---

## 背景

调研 volcengine/OpenViking（AGPLv3，Agent 上下文数据库，L0/L1 分层摘要+混合检索），评估 CodeWiki 借鉴点。

## 决策

P0 三原则：L0 目录级摘要借「分层」不借「LLM」（module 文档规则抽取 overview 段，零模型成本；优先 frontmatter abstract 字段而非 sidecar 文件——sidecar 易漂移，但注意 frontmatter 5-writer 加字段须三处同步）；注入预算降级借「模式」不借「hook」（超预算条目降为 URI+score 一行，与 adoption_hint 天然搭档）；merge_op 预合并借「粒度」不借「无闸门」（同主题多条 draft 字段级预合并产出一条，人只 confirm 一次）。

## 根因

CodeWiki=少而精跟仓库走人审过（知识库），OpenViking=多而活跟用户走全自动（运行时状态）。闸门哲学不丢，机制级优势低成本吸收。定位若成立，CodeWiki 可当 OpenViking 上游生产者（V9 互操作验证）。
