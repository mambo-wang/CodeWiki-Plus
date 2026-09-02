---
type: architecture
title: query_wiki 索引机制：frontmatter 除 6 个 boost 字段外一律剥离不进 BM25，metadata 折叠与 json.dumps
  转义不影响检索
tags:
- architecture
metadata:
  date: 2026-08-15
  related_modules:
  - codewiki/mcp/cache.py
  - codewiki/mcp/tools/wiki_index.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:35+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
author: mambo-wang
---

## 事实

query_wiki 索引构建链路为 build_full_index → _build_indexable_text → BM25。索引文本只由两部分组成：① 6 个 boost 字段（tags 3x / description 2x / title 2x / aliases 3x / severity 2x / related_modules 2x）以 2-3 倍权重进索引；② 正文 body = 正则剥离 frontmatter 块后的 content。

## 推论

- frontmatter 除 6 个 boost 字段外一律不进索引（设计如此，非本次改动引入）。
- 私有键折叠进 metadata 与否、json.dumps 转义与否，对检索无差别（这些字段本就不进索引）；source_ref 的消费方是 source_ingest 的 _clean_source_refs/_count_source_refs，那里用完整 yaml.safe_load 解析，转义值能正确还原。
- 若未来想让 metadata 内字段可检索，需在 _build_indexable_text 显式加 boost（示例：把 _meta 里的 source_ref 追加进 parts 参与 1x BM25）。
