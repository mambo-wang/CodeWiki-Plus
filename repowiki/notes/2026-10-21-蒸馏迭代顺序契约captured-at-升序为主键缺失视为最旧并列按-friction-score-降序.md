---
type: architecture
title: "蒸馏迭代顺序契约：captured_at 升序为主键，缺失视为最旧，并列按 friction_score 降序"
tags: ["architecture"]
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 日常维护
  source_session: "d1684b0203bc487398ca761a4bfce9fd"
  related_modules: ["mcp-tools-distill-conversation", "task-memory"]
  severity: medium
  source_ref: "conversations/conv-现在蒸馏对话的时候，是否会按采集时间从早到晚的顺序来蒸馏？.md"
  scene: "蒸馏/任务记忆"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.15.0, at: 2026-10-21T11:58:43Z }
stale_after: 2027-10-21
origin: conversation

---

## Background

有用户询问：蒸馏（distill_conversation）待处理 raw 对话时，是否按采集时间从早到晚的顺序处理。经核对代码确认：是。

## 结论

`codewiki/mcp/tools/distill_conversation.py:363-385` 的 `_iter_raw_files` 决定蒸馏迭代顺序，prepare 与 submit 共享该顺序：

1. **主键 `captured_at` 升序**（ISO-8601 UTC 时间戳字典序即时间序，见 `distill_conversation.py:334-335`），最早的最先蒸馏；
2. **缺失 `captured_at` 的老格式采集文件视为最旧**，排最前；
3. **同一时刻并列时**按 `friction_score` 降序（摩擦分高的排前），再按文件名；
4. 已 `distilled` 状态的文件直接跳过。

## Rationale

这是一个跨模块契约而非实现细节：prepare→submit 共享此迭代顺序，批量蒸馏时任务记忆按「最旧→最新」追加，保持 memory reader 依赖的「最新条目在末尾」约定（`entries[-max_memories:]` 截断才正确）。改动排序逻辑会破坏 memory reader 的截断语义，值得持久记录以防误改。

## 依据

本次会话中经读取 `codewiki/mcp/tools/distill_conversation.py:360-400` 核对确认（2026-10-21，codewiki 5.16.0）。
