---
type: pitfall
title: "hook 事件信封合成时须置空 source_session_id，否则 supersede 会覆盖真实 transcript（数据丢失）"
date: 2026-08-09
related_modules: ["team-memory", "mcp", "\"\""]
related_components: []
tags: ["pitfall", "precompact", "sessionend"]
source_ref: "raw\conv-20260808T152648Z.md"
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:52Z }
stale_after: 2026-11-07
origin: conversation

---

## 背景

早期 review 发现：`_ide_hook` 在 SessionEnd/Stop/PreCompact 无 transcript 时合成"事件信封"最小记录，并携带 `source_session_id`。而 `capture_conversation` 的 supersede 去重逻辑按 `source_session_id` 匹配并**替换**同 session 的 pending 文件。典型时序：Stop 每轮带完整 transcript 落盘 → SessionEnd 无 transcript 合成 1 行系统消息 → 同 `source_session_id` → supersede 把完整 transcript **覆盖成一行诊断文本**（数据丢失）。

## 正确做法

信封合成时引入 `is_envelope` 标记，置 `True` 时强制 `source_session_id=""`。这样 `capture_conversation` 中 `if source_session_id:` 守卫为 False，信封被写成新文件而非 supersede 覆盖真实 transcript。

## 根因

supersede 的前提是"每次捕获是前一次的超集"，信封记录打破了该假设（它比真实 transcript 小得多）。

## 适用范围

所有会话级 supersede 去重的采集器；任何 fallback 最小记录都不得复用真实捕获的 session 标识。
