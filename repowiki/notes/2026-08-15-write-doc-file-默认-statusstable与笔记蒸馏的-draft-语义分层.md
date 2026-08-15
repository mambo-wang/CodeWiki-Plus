---
type: decision
title: write_doc_file 默认 status=stable，与笔记/蒸馏的 draft 语义分层
tags:
- decision
metadata:
  date: 2026-08-15
  related_modules:
  - doc_writer
  - prompt_server
  - knowledge_loop
  - distill_conversation
  source_ref: raw\conv-使用codewiki-mcp扫描生成的代码wiki为什么status是draft.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:16:10+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:09Z'
---

## 背景

用户问「代码扫描生成的 wiki 为什么 status 是 draft」，并要求「代码生成 wiki 场景默认就是 stable」。

## 决策

区分「代码生成 wiki 页面」与「经验笔记」的 status 语义：

- **`write_doc_file`（代码生成 wiki）默认 `status: stable`**：代码扫描是确定性产出，无需人工审核。三条 frontmatter 注入路径全部补齐默认值——`_build_okf_frontmatter`（session 模式）、`_inject_lightweight_frontmatter`（sessionless 模式）追加 `status: {extra.get('status') or 'stable'}`，`_okf_patch_defaults` 增加补丁项「仅当已有 frontmatter 缺失 status 时补 stable，已写 draft 的不覆盖」。同步改 `prompt_server.py` 模板示例 `status: draft` → `status: stable`，避免 Agent 照抄示例生成 draft。
- **`ingest_note`/`distill_conversation`（经验笔记）保持 `draft`**：须 `confirm_note` 确认后才成 stable，是知识飞轮的质量闸门。

## 关键约束（勿踩）

**不要全局改 `inject_okf_frontmatter` 的 `status="draft"` 默认值**：它被 `capture_conversation`（显式传 `pending`）和蒸馏链路（「未审核」语义）依赖，全局改会破坏 raw/ 暂存与蒸馏语义。改动只收敛在 `doc_writer.py` 的 wiki 生成路径。
