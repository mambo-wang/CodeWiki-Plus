---
type: decision
title: "归档对话文件名用用户首句 slug，且与 conversation_id 必须一致（蒸馏链路依赖此约束）"
tags: ["decision"]
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:53Z }
stale_after: 2026-11-07

metadata:
  date: "2026-08-09"
  origin: "conversation"
  related_components: []
  related_modules: ["team-memory", "mcp", "\"\""]
  source_ref: "raw\\conv-20260808T152648Z.md"
---

## 背景

用户希望归档文件名与 IDE 展示的对话主题一致，而非时间戳。

## 决策

`capture_conversation` 文件名改为 `conv-{首句slug}.md`：
- 新增 `_slugify(text)`（替换 `<>:"/\|?*` 及控制字符为 `-`、折叠空白与连字符、限长 60 字符）与 `_first_user_text(turns)`（取首条 user 轮，兼容字符串或 content 块数组）。
- 冲突时追加 `-2`/`-3` 后缀；无用户文本时回退时间戳 `conv-{timestamp}.md`。
- **关键约束**：`conversation_id` frontmatter 必须等于文件 stem（去掉 `conv-` 前缀），因为蒸馏链路的 supersede/去重与读取都依赖 `conversation_id` 与文件名一致。

## 取舍

- 选 slug 而非时间戳：可读性、与 IDE 对话名对齐。
- 保留时间戳回退：防止首句缺失时丢失归档。
- 限长 60 + 冲突后缀：避免文件系统问题且保证唯一。

## 适用范围

raw 文件命名约定；任何读取 raw 文件名推导 conversation_id 的代码都必须保持 stem 一致。
