---
type: pitfall
title: 旧生成器 frontmatter metadata list/mapping 混合坏结构会静默崩溃全库索引重建（异常被吞）
tags:
- attributeerror
- pitfall
- weknora
metadata:
  date: 2026-09-07
  related_modules:
  - retrieval
  - extraction
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-c23ccd.md
  scene: 外部文档知识抽取
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:02:40+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:23Z'
---

## 背景

2026-09-05 执行 WeKnora v0.8.0 README 外部文档抽取后，`query_wiki` 持续超时、新页面检索不到。排查发现：`wiki/entities/WeKnora.md`（v5.2.0 旧生成器产物）的 frontmatter `metadata:` 块是**孤儿 list 项 + mapping 键的混合坏结构**，YAML 解析为 list → `retrieval.py` 的 `_meta.get()` AttributeError → `build_full_index` 崩溃 → 全库索引无法重建。

## 关键症状与静默失败模式

- `close_session` 的索引 rebuild 被 try/except 吞掉，异常不上报——`.meta/search_index.json` 时间戳停滞在旧版是最可靠的判据。
- query_wiki 每次经 freshness 门触发全量 rebuild，重建慢/失败叠加 MCP 超时 → 表现为「查询超时」而非索引错误。
- SQLite 索引（repo 根 `.codewiki/analysis_cache.db`）与 JSON fallback 两条路径状态可能不一致。

## 修复

把 `metadata:` 块规范为纯 mapping 结构并去重 chunk_refs 后，205 个文档全部成功索引（55 wiki + 146 notes + 4 sources），检索恢复。

## 教训

旧生成器产出的 frontmatter 是索引重建的隐性地雷：单文件坏结构会静默阻塞全库索引；遇到「query 超时 + 索引时间戳不新鲜」时优先检查最近写入页面的 frontmatter 解析结果。（与 load_project_checklist 的 YAML 静默回退是不同代码路径的同类静默失败模式。）
