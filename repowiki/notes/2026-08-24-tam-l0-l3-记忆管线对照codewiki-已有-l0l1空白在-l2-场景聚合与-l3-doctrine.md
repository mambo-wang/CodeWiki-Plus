---
type: architecture
title: TAM L0-L3 记忆管线对照：CodeWiki 已有 L0/L1，空白在 L2 场景聚合与 L3 Doctrine
tags:
- architecture
- codewiki
- personatrigger
- sceneextractor
metadata:
  date: 2026-08-24
  related_modules:
  - consolidate_notes
  - refresh_doctrine
  - 团队记忆融合-L2场景聚合与L3-Doctrine设计方案
  severity: medium
  source_ref: conversations/conv-调研-TencentDB-Agent-Memory-的记忆机制，分析-CodeWiki-CN-能否借鉴.md
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:22:03+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:19Z'
reject_reason: 聚合进场景：对话蒸馏管线与raw暂存区
author: mambo-wang
---

## 背景

分析 TencentDB-Agent-Memory（TAM）的 L0-L3 记忆管线：L0 录制器+hooks 采集、L1 原子记忆提取（调度器批处理）、L2 场景聚合（SceneExtractor）、L3 人格生成（PersonaTrigger）。

## 评估结论

CodeWiki 已借鉴一半：_should_capture_l0/_should_extract_l1 门控已对齐 TAM，L0（capture_conversation→raw/）、L1（distill_conversation→notes/）已有；空白在 L2 只有 lint 信号无聚合实体、L3 完全缺失。

## 决策

新增 consolidate_notes（confirmed 笔记聚合为 ≤15 个 wiki/scenarios/ 场景块，UPDATE>MERGE>CREATE 容量分级）与 refresh_doctrine（压缩 ≤1200 字 doctrine.md 项目操作原则）两个 Mode C 工具。关键适配：触发用计数器信号替代 TAM 定时器级联（wiki_stats/get_task_context 露出）；去重召回用现有 BM25 替代向量、判定交宿主 agent（两段式 submit+四操作）；产物沿用 OKF 三态评审闸门。
