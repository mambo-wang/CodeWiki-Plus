---
type: pitfall
title: "SessionStart 注入的蒸馏积压清单可能与 raw frontmatter 的 task_id 归属不一致：以 prepare(task_id) 返回为准"
tags: ["pitfall", "sessionstart"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  task_id: 他山之石
  source_session: "374cbbe2c2ab47a2a7f4b140b49205d7"
  related_modules: ["distillation", "task_session_start", "task-memory"]
  severity: medium
  source_ref: "conversations/conv-@command-open-code-review-delegate-拉取最新代码并review最近一次提交.md"
  scene: "补蒸馏派发/SessionStart 积压清单"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:34:03Z }
stale_after: 2027-05-27
origin: conversation

---

## Background

一次会话的 SessionStart 注入提示「任务『他山之石』有 2 条待蒸馏积压」，但蒸馏 worker 执行 `distill_conversation(mode="prepare", task_id="他山之石")` 返回 `status=noop`；实际检查 `repowiki/raw/` 发现 2 条 pending raw 的 frontmatter task_id 分别是「发版本」和「日常维护」。

## 正确做法

- 蒸馏 worker 的任务边界以 **prepare(task_id) 的返回为准**，不以 SessionStart 注入的积压清单为准；prepare 返回 noop 即结束，不要手动扫描 raw/ 目录越权处理。
- 主 Agent 派发蒸馏前若发现清单与归属不符，应按 raw frontmatter 的实际 task_id 分别指派（或经用户确认后由 worker 按各 task_id 逐个执行 prepare→read→submit）。

## Rationale

归属不一致时若按注入清单强行蒸馏，会跨任务消费 raw、违反「只蒸馏当前绑定任务」的约束；这条判定规则可避免 worker 与主 Agent 在类似场景下反复空转或越权。

## Root cause

SessionStart 注入的积压统计与 raw frontmatter 的 task_id 归属口径存在不一致（具体成因当时未深究，属待确认项）。与 `notes/2026-09-19-蒸馏-submit-返回-noopraw-被并行流程抢先处理时的正确处置.md` 互补：那条讲 submit 阶段被并行流程抢先，本条讲 prepare 阶段清单口径不一致。
