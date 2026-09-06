---
type: architecture
title: query_wiki 的 check 模式是轻量预检：不计入检索统计、不污染 usage/heat 排序信号；工作流若不内建到工具描述，精心设计会失效
tags:
- architecture
- codewiki
metadata:
  date: 2026-09-05
  related_modules:
  - knowledge_loop
  - query_wiki
  severity: medium
  source_ref: conversations/conv-https-github.com-thedotmack-claude-mem-blob-main-docs%2Fi18n.md
  scene: 检索透明化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:39:41+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:36Z'
---

## 事实

- `query_wiki(mode=check)`（query_mode_check）是轻量预检模式，注释明确「不记录检索统计，避免污染 usage/heat 信号」（knowledge_loop.py:1729-1735 一带）。
- `usage`/`heat` 权重参与排序（BM25 + authority + usage heat 三重加权），check 不计热度使预检不污染真实检索信号。
- 若 Agent 不知道 check 模式存在（默认用普通检索当预检），真实检索信号会被预检稀释——设计就无效。

## 结论（P0-3 的动机）

工作流/模式选择必须**内建到工具描述**（claude-mem 用永远可见的 `important_workflow` 工具，CodeWiki 靠 AGENTS.md 文字约束可能不被读到）。「低成本让已有设计真正生效」优先于「新造能力」。检索类工具的描述应写明：轻量预检用 check、需要历史/全字段再走默认检索。
