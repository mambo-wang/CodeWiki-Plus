---
type: pitfall
title: "distill_conversation submit MCP 超时后仍会执行且不幂等——超时重试导致任务记忆重复写入与字节交错损坏"
tags: ["pitfall", "unicodedecodeerror"]
aliases: ["distill submit 幂等", "任务记忆损坏", "per-user memories 文件", "distill 重复写入"]
metadata:
  date: 2026-08-26
  severity: high
status: stable
generated: { by: codewiki/5.4.4, at: 2026-08-26T04:31:03Z }
stale_after: 2027-02-22
---

## 背景

distill_conversation(mode="submit") 连续三次 MCP 调用超时无响应，调用方每次超时后重试，导致同一批 4 条任务记忆被重复写入 2–3 次，且写入过程中出现字节交错损坏。

## 现象

- 调用超时 ≠ 未执行：MCP 响应通道断开但 server 端实际继续执行，超时重试即重复执行，distill submit 不幂等。
- per-user 任务记忆文件 `tasks/<task_id>/memories/<user_id>.md` 出现重复条目 + GBK/UTF-8 字节交错（截断碎片、非法字节），进而导致 `get_task`/`get_task_context` 读取时抛 UnicodeDecodeError 崩溃。

## 根因

无状态工具执行中响应通道断开，调用方超时重试重复执行；多次写入交错破坏 UTF-8 编码。

## 正确做法

- submit 前检查目标记忆文件是否已含相同条目（幂等保护），或超时后先核实落盘状态再决定是否重试，勿盲目重发。
- 记忆落盘路径为 `tasks/<task_id>/memories/<user_id>.md`（per-user 零冲突设计，git 级互斥），AGENTS.md 中 `<task_id>/memories.md` 为存量只读兼容层，勿按旧描述定位记忆。

## 恢复条件

文件损坏时：删除重复组、保留最后一次完整组重建；清理非法字节（Python 二进制读 + errors='replace' 定位）；`get_task` 验证恢复。
