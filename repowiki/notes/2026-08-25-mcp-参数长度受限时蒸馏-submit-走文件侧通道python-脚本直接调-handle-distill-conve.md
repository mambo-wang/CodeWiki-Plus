---
type: pitfall
title: MCP 参数长度受限时蒸馏 submit 应走 distilled_file 文件侧通道（勿内联大 JSON）
tags:
- pitfall
metadata:
  date: 2026-08-25
  task_id: 产品维护
  related_modules:
  - codewiki
  - distill
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-蒸馏对话提取记忆和经验-把已采集的对话（repowiki-9477de.md
  scene: 蒸馏工作流
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
status: stable
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 16:39:13+00:00
stale_after: '2026-10-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T16:42:01Z'
author: mambo-wang
---

## 背景

Mode C 蒸馏流程中，一次 submit 多对话/多笔记的蒸馏 JSON 可能超过 MCP 工具参数长度限制，被 MCP 拒绝（如单条大对话蒸馏出多条笔记+长正文时）。曾以 Python 脚本直连 handler 绕过（旧 workaround），后已从源码层面提供正式通道。

## 正确做法

用 `distill_conversation(mode="submit", distilled_file=<路径>)` 文件侧通道：先把蒸馏 JSON（形状 `{conversation_id: {notes, memories}}`，或单条裸 `{notes, memories}` 配合 conversation_id 参数）用 write_to_file 写入 `repowiki/raw/.distill-*.json`，submit 只传小路径。工具读取后自动删除暂存文件（一次性消费凭证）。小载荷仍可内联 `distilled`（两者可合并，内联优先）。**不要再写临时 Python 脚本调用 handler 绕过。**

## 恢复条件

无——`distilled_file` 已是正式通道，无需恢复旧绕过方案。
