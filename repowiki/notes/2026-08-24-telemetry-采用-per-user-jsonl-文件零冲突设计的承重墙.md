---
type: decision
title: telemetry 采用 per-user jsonl 文件：零冲突设计的承重墙
tags:
- decision
metadata:
  date: 2026-08-24
  related_modules:
  - telemetry
  - teamai-cli-调研与借鉴分析
  severity: medium
  source_ref: conversations/conv-研究一下-https-github.com-Tencent-teamai-cli，看下跟CodeWiki的对比和可借鉴之.md
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:16:07+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:08Z'
reject_reason: 聚合进场景：MCP-Server薄壳架构与参数约定
---

## 背景

设计团队 telemetry 存储时考虑过「所有用户共用一个 jsonl」的方案。

## 决策

采用 per-user jsonl（telemetry/<user>.jsonl）作为单一事实源。单文件方案有三个致命问题：1) 把冲突面从零变回全量（聚合形态重写整个文件=已退役的 retrieval_stats.db 模式，git 文件级合并语义）；2) 丢下游必需信息（last_hit/幂等 key/distinct_users）；3) 「每天归档」实为写入粒度而非归档动作。

## 根因

git 的冲突粒度是文件级：per-user 文件把并发写天然隔离到不同文件，聚合只在内存中做（几万行 JSONL 几十毫秒，被 mtime 快照压频），不需要持久化聚合表。retrieval_stats.db 整体退役，消除「双写不一致」概念。
