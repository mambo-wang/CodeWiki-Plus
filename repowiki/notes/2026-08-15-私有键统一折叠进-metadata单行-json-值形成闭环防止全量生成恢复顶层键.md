---
type: decision
title: 私有键统一折叠进 metadata:（单行 JSON 值）形成闭环，防止全量生成恢复顶层键
tags:
- decision
metadata:
  date: 2026-08-15
  related_modules:
  - codewiki/mcp/tools/doc_writer.py
  - codewiki/src/frontmatter.py
  - codewiki/mcp/tools/knowledge_loop.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:34+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
author: mambo-wang
---

## 背景

OKF v0.2 要求顶层只保留标准键，生产者私有键（source_ref/root_cause/date/related_components/task_id 等）须折叠进嵌套的 `metadata:` 节点。早期只有 ingest_note 折叠，doc_writer 三路径（会话生成器 / sessionless / edit refs 同步）仍可能把私有键写回顶层，全量重新生成会恢复旧格式。

## 决策

- 折叠收敛为统一规则：私有键以单行 JSON 值折叠进 `metadata:`（`metadata: {"source_ref": "...", ...}`），保证单行可解析。
- doc_writer 三条 frontmatter 生成路径与 ingest_note 走同一套折叠逻辑，形成闭环，防止全量生成恢复顶层私有键。
- 消费端读取兼容两态：`_extract_frontmatter` 既能读顶层旧键也能读 `metadata:` 内折叠键（元数据回带走这条路径）。

## 根因

折叠规则分散在多个写路径，缺少单一事实来源；顶层/折叠两态并存导致生成器与消费端不一致。
