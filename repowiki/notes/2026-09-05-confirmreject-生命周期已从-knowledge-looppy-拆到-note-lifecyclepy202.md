---
type: architecture
title: confirm/reject 生命周期已从 knowledge_loop.py 拆到 note_lifecycle.py（2026-09 重构），旧文件为兼容门面
tags:
- architecture
metadata:
  date: 2026-09-05
  related_modules:
  - knowledge_loop
  - note_lifecycle
  severity: medium
  source_ref: conversations/conv-基于本仓库代码逐层说明「准确性-可信度」是怎么保证的。-##-核心立场-工具做确定性簿记，推理决策永远在调用方与用户手里.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:31:51+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:33Z'
---

## 事实

2026-09 拆分后 `codewiki/mcp/tools/knowledge_loop.py` 仅 2.4KB，是**兼容门面**；confirm/reject 真实实现已移至 `codewiki/mcp/tools/note_lifecycle.py`：

- `handle_confirm_note`（note_lifecycle.py:56-91）：把 draft 笔记升为 `stable`，append `verified` 条目（传 `by` 时记 `human:<id>`，否则 `codewiki/<version>`），并续期 `stale_after`。
- `handle_reject_note`（note_lifecycle.py:94 起）：转 `deprecated`。
- `batch_set_status`（note_lifecycle.py:171-290）：批量仅允许 `stable/deprecated`，支持 dry-run。

## 启示

引用 `knowledge_loop.py:996-1058` 之类行号的旧资料已过时，定位确认/驳回逻辑应查 `note_lifecycle.py`。核查大文件重构后的行为同理：先确认文件是否已拆分为门面，再按语义找真实实现。
