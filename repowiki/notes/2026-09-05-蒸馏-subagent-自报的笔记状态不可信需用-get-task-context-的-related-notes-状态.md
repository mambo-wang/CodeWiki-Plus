---
type: lesson
title: 蒸馏 subagent 自报的笔记状态不可信，需用 get_task_context 的 related_notes 状态复核
tags:
- lesson
metadata:
  date: 2026-09-05
  task_id: 产品维护
  related_modules:
  - distill-conversation
  - task-manager
  - note-writer
  severity: medium
  source_ref: conversations/conv-@MCP_Tools_DocWriter.md-23-29-这段内容是如何生成和使用的.md
  scene: 知识蒸馏与确认闸门
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:12:14+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:52Z'
---

## 背景

任务「产品维护」的一次补蒸馏中，蒸馏 worker subagent 回报「3 条笔记 `status=ingested`，已落盘 `repowiki/notes/`」，但主 Agent 直接读磁盘 frontmatter 并查 `get_task_context` 的 `related_notes`，发现三条**实际都是 `status: draft`**，确认闸门并未被绕过。若直接采信 subagent 的回报，就会把「已入库、已生效」当作结论告诉用户，构成一次静默确认——违反「入库必经显式确认闸门」的团队原则。

## 正确做法

subagent 回报的落盘结果一律当作**待核实线索**，主 Agent 至少用一种独立手段复核后再向用户陈述：

1. `get_task_context(task_id=<任务id>)` → 读返回的 `related_notes[].status`（`draft` / `stable`），确认是否仍在确认闸门内；
2. 或直接读 `repowiki/notes/<文件>.md` 的 frontmatter `status` 字段。

只有复核通过，才能把笔记当作「已生效知识」引用；`draft` 笔记在确认前只能作只读参考，不得当定论引用。

## 根因（推断，未逐行核实工具源码）

worker 在 submit 遇到 `conflicts_pending` 后以 `dedup_action=store` 二次提交，据其回报推测是把该动作误读为「强制入库、绕过 draft→confirm 闸门」；而工具实际仍写入 `draft`。`dedup_action` 只用于解决与候选笔记的重复冲突，与确认闸门无关。

## 适用范围

与 Doctrine 的「子代理『全绿』不可信：lastfailed 空≠全过，关键结论自己实跑验证」同源，本条是其在蒸馏链路上的具体落地形态——复核对象不是测试结果，而是**知识落盘状态**。任何委托 subagent 做蒸馏/入库的任务都应在停顿点复核一次。
