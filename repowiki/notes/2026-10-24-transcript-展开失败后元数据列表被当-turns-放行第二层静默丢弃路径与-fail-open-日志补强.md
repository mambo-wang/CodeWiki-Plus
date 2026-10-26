---
type: pitfall
title: "transcript 展开失败后元数据列表被当 turns 放行：第二层静默丢弃路径与 fail-open 日志补强"
tags: ["codebuddy", "pitfall", "sessionend"]
metadata:
  date: 2026-10-24
  confidence_level: weak
  task_id: 日常维护
  source_session: "841627794bde4abf9a37b975f7c9b3b5"
  related_modules: ["codewiki/mcp/_ide_hook.py", "codewiki/hooks/capture_session_end.py"]
  severity: medium
  source_ref: "conversations\\conv-我发现内网电脑那个codebuddy我发采集对话记录，分析结果是：根因：transcript-展开失败，采集静默丢弃-采.md"
  scene: "对话采集链路（SessionEnd hook）"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.2, at: 2026-10-24T08:01:41Z }
stale_after: 2027-04-22
origin: conversation

---

## Background

修复 CodeBuddy SessionEnd 采集竞态（见配套笔记）过程中，回归测试 `race_timeout_returns_none` 失败，暴露出比竞态本身更隐蔽的第二层静默丢弃路径。

## Root cause

`_ide_hook.py` 的 `_load_transcript` 裸数组分支在展开失败后把元数据列表原样返回：`normalized or data` 兜底放行——CodeBuddy index 的元数据 `{id,type,role,isComplete}` 恰好带 `role` 字段，被当成合法 turns 传给 capture → 全部无正文 → `"no usable turns"` → 错误被 DEVNULL 吞掉，零痕迹。

## Decision/正确做法

1. 新增 `_is_codebuddy_index` 判定：识别为 CodeBuddy index 但展开失败时返回 `None`（list/dict 两分支都处理），不再让无正文元数据漏成假 turns。
2. 新增 `_log_capture_event`（fail-open）：把「SessionEnd 无可用 turns」「capture 返回 error」「capture 异常」追加写入 `repowiki/.meta/hook_capture.log`——以后再发生静默丢弃，日志里直接可查。

## Rationale

DEVNULL 吞错 + 元数据形状恰好通过校验 = 双重静默，这类 bug 只能靠日志出口在下次发生时留下证据。fail-open 日志（写失败不抛出、不影响采集主流程）是采集类代码的标配：注入/采集代码永不因可观测性补强而新增失败路径。

## Recovery

排查「采集没写 raw/」类问题时，先查 `repowiki/.meta/hook_capture.log`；修复随下个版本（5.16.1 之后）发布，内网机器升级后生效。
