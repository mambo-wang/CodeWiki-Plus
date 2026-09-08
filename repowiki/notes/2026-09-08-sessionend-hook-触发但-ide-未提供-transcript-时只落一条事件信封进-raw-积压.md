---
type: pitfall
title: SessionEnd hook 触发但 IDE 未提供 transcript 时，只落一条事件信封进 raw 积压
tags:
- pitfall
- sessionend
metadata:
  date: 2026-09-08
  related_modules:
  - hooks
  - capture
  severity: medium
  source_ref: conversations/conv-[team-memory]-SessionEnd-hook-fired-but-the-IDE-provided-no.md
  scene: hook 采集
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:09:38+00:00
stale_after: '2027-03-07'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-08T05:28:21Z'
---

## Background

`repowiki/raw/` 里会出现名为 `conv-[team-memory]-SessionEnd-hook-fired-but-the-IDE-provided-no.md` 的待蒸馏 raw，正文只有一条 user 消息：`[team-memory] SessionEnd hook fired but the IDE provided no inline transcript and no readable transcript_path. Raw event envelope preserved for diagnosis.`

## 事实

SessionEnd hook 确实触发了，但 IDE 既没给 inline transcript，也没给可读的 `transcript_path`。此时 `codewiki/hooks/capture_session_end.py` 只把事件信封（keys：`client`、`cwd`、`hook_event_name`、`reason`、`session_id`、`version`）写进 raw 作为诊断留痕，该会话的对话内容永久丢失。

## 正确做法

- 在 raw 积压里看到这类「空信封」文件属**预期行为**，不是采集 bug；蒸馏时直接给 `{"notes": [], "memories": []}` 跳过，不要当对话内容分析。
- 这与 PreCompact/Stop 的同类问题一致（见 `notes/2026-08-09-同一会话的-precompactstop-不带-transcript-path落空信封会被-duplicate-去重应视.md`）：区别只是这次发生在 SessionEnd 上，说明空信封不局限于已放弃的 PreCompact/Stop 兜底。
- 要真正覆盖这类漏采，只能等 IDE 侧给 hook 带 transcript，或做启动时遗留 transcript 补偿；matcher 层面无解。
