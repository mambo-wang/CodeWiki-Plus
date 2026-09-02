---
type: lesson
title: "无知识的 raw 对话蒸馏后也应清理，删除条件要用 produced is not None 而非 truthy"
tags: ["lesson"]
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:54Z }
stale_after: 2026-11-07

metadata:
  date: "2026-08-09"
  origin: "conversation"
  related_components: []
  related_modules: ["team-memory", "mcp", "\"\""]
  source_ref: "raw\\conv-20260808T152648Z.md"
author: mambo-wang
---

## 背景

用户提出优化：无需提取知识的对话，蒸馏后应自动删除 raw 文件，避免暂存区膨胀。

## 正确做法

`distill_conversation.py` 删除条件由 `if not keep_raw and produced:` 改为 `if not keep_raw and produced is not None:`。`produced` 在没有知识时为 `{"notes": []}`（空 dict，**truthy**），原条件反而删不掉；改为 `is not None` 后，有知识/无知识都正确清理，`keep_raw` 从 raw frontmatter 读取可保留。

## 根因

`{"notes": []}` 是空内容但非空对象，Python 中 truthy，导致 no_knowledge 的 raw 不被删除。

## 适用范围

任何"判定是否清理暂存"的逻辑；区分"无产出"（None）与"空产出"（空结构）。
