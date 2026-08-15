---
type: pitfall
title: no_knowledge 的 raw 由 distill 清理删除，keep_raw 是唯一保留途径
tags:
- pitfall
metadata:
  date: 2026-08-15
  related_modules:
  - distill_conversation
  source_ref: raw\conv-使用codewiki-mcp扫描生成的代码wiki为什么status是draft.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:16:12+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:14Z'
---

## 背景

修复 `tests/smoke_test_mcp.py` 基线失败时发现：测试断言「no_knowledge 的 raw 保留并标记 distilled」，但实现是直接删除。

## 事实

`distill_conversation` 对无知识的 raw 文件（`notes=[]`）按设计**直接清理删除**（噪音不保留），与 AGENTS.md「蒸馏完成后删除」一致；`keep_raw=true` 是**唯一**保留 raw 的途径。

## 教训

写测试或排查 raw 文件去向时，no_knowledge 与 keep_raw 是两条不同路径：前者删、后者留。旧冒烟测试断言「保留并标记 distilled」已过时，正确断言是「文件不存在」；保留行为由 `tests/test_distill_cleanup.py` 单独覆盖。
