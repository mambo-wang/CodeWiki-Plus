---
type: pitfall
title: sources / wiki-sources / raw-sources / source_refs 四处同名，语义完全不同
tags:
- codewiki
- pitfall
metadata:
  date: 2026-09-05
  task_id: 产品维护
  related_modules:
  - evidence
  - wiki-cache
  - retrieval
  - doc-writer
  severity: medium
  source_ref: conversations/conv-@MCP_Tools_DocWriter.md-23-29-这段内容是如何生成和使用的.md
  scene: 代码证据（OKF sources）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:13:54+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:40Z'
---

## 背景

在 CodeWiki 仓库里按 `sources` 检索会同时命中四种互不相干的东西，改代码或做检索优化时极易改错对象。

## 区分表

| 名称 | 位置 | 语义 |
|---|---|---|
| frontmatter `sources` | 页面 YAML 头 | OKF 代码证据清单（`id` / `resource` / `content_hash`），由证据机制写入，被 lint 的 `stale_evidence` 消费 |
| `wiki/sources/` | 页面类型目录 | 三方文档页（source 类型），检索权重 `-0.20`（`codewiki/mcp/tools/retrieval.py:459`） |
| `raw/sources/` | 暂存目录 | 三方资料暂存，由 `cache.py:1159` 索引 |
| frontmatter `source_refs` / `chunk_refs` | 页面 YAML 头 | 正文 `[^src:...]` 引用同步字段，由 `_resync_source_refs` 维护，与代码证据无关 |

## 正确做法

改证据相关逻辑前先确认目标是 frontmatter `sources`；调检索权重、清理暂存目录或做引用同步时，不要误伤另外三个同名物。

## 与相邻笔记的分工

本条讲「同名歧义、别改错对象」；`frontmatter sources 有三个生产者，字段形态各不相同` 讲「同一字段由哪三条链路写入、如何据字段形态反推来源」。两者互补，不是重复。

## 易混淆的其它 sources

`review_changes` 的 `changed_sources`（变更函数切片）也与本字段无关——untracked 新文件不在分析图谱内时它为空，属另一条链路。
