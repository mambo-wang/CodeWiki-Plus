---
type: pitfall
title: handle_query_wiki 在 session 存在时每次查询都全量重建检索索引
tags:
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - knowledge_loop
  - wiki_search
  source_ref: conversations/conv-@command-codewiki-变更评估与代码评审（修改后）.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:02:43+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:46Z'
---

## 背景

knowledge_loop.py 的 handle_query_wiki 中，`if not idx_path.exists() or session is not None: build_full_index(...)` —— session 存在时每次查询都触发全量索引重建。build_search_index 无条件 DELETE 三表重建且无锁。

## 影响

这是评审工具卡顿的深层根因，也是并行化前置障碍：4 个 collector 并行查询会并发重建同一 SQLite 索引，浪费且产生数据竞争。

## 正确做法

并行化需三件套：预热一次索引 → 查询走 skip_index_build 跳过重建 → 再并行 collector。只加锁保留每次重建（方案 B）虽安全但性能问题依旧。应复用 index_freshness 的 freshness 判断避免重复重建。

## 根因

索引重建的触发条件过宽（session 存在即重建），没有 freshness 缓存机制。
