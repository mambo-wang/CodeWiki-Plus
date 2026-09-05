---
type: decision
title: ADR-0003：知识新鲜度判据采用 git 最后提交时间，否决 mtime（clone 场景全量假阳性）
tags:
- decision
metadata:
  date: 2026-09-05
  related_modules:
  - wiki_lint
  severity: high
  source_ref: conversations/conv-对-docs-claude-mem借鉴详细设计方案.md-做拷问式评审（grill）：先派子代理核对方案引用的全部代码事.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:33:40+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:32Z'
---

## Decision

知识/资产「新鲜度」判据定为 **git 最后提交时间**（clone-safe，语义即「代码/内容最后一次变动」），否决 mtime 方案。已落盘 ADR-0003，登记进 CONTEXT.md Key decisions。

## Rationale

- mtime 在 git clone 场景下**全量假阳性**：clone 时间即所有文件 mtime，全部被判陈旧；加 1 天缓冲也治不了本质问题。
- git 提交时间跨 clone 稳定、语义正确（代码最后变动时刻），是确定性机器信号。
- 语义术语沉淀：possibly_stale（可能陈旧）、file knowledge（文件知识）、新鲜度双轴。

## 适用范围

stale_notes / stale_evidence 等一切基于「最后变动时间」的复核判据；设计文档对比表若残留 mtime 表述需改判据为 git 提交时间。
