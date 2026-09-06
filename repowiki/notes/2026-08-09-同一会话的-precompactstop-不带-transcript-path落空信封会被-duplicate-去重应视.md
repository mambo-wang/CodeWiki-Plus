---
type: lesson
title: "同一会话的 PreCompact/Stop 不带 transcript_path，落空信封会被 duplicate 去重，应视为 no-op"
tags: ["lesson", "precompact", "sessionend"]
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:52Z }
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

排查"压缩会话没生成归档文件"时，读 `.hook-diag.log` 发现：PreCompact 与 Stop 事件 `has_transcript_path=False` 且 `has_conv=False`，代码仍合成一条仅含系统提示的"事件信封"落盘。由于信封无 `source_session_id`、内容哈希重复，PreCompact→Stop→Stop 连续触发全部哈希撞车，被 `capture_conversation` 判为 `duplicate` 跳过——表现为"看不到新文件"。真正有正文的是更早的 SessionEnd（`turns=206`）。

## 正确做法

无 `transcript_path` 且无非内联 turns 的 PreCompact/Stop 应**直接 no-op 返回**，不要落空信封。真正的归档只依赖 SessionEnd（唯一带 `transcript_path` 的事件）。若未来 IDE 为 PreCompact 提供 `transcript_path`，再启用其采集。

## 根因

仅有 `session_id` 不足以获取正文；空信封内容固定且不被去重区分同一会话的多次触发，浪费 raw 且制造"没生成"的误判。

## 适用范围

team-memory 采集的 wrapper/hook 设计；凡是"事件触发但无数据来源"的兜底落盘都需评估是否该变成 no-op。
