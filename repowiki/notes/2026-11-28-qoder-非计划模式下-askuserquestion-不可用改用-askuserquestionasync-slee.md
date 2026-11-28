---
type: workaround
title: "Qoder 非计划模式下 AskUserQuestion 不可用：改用 AskUserQuestionAsync + Sleep 等待，无响应按不关联继续"
tags: ["askuserquestion", "askuserquestionasync", "sessionstart", "workaround"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  source_session: "81fc45f7-e7a0-4e83-9538-f6c14de91c4b"
  related_modules: ["task_session_start", "hooks"]
  severity: medium
  source_ref: "conversations/conv-现在codewiki-mcp用的是本地codewiki-plus代码还是pypi依赖.md"
  scene: "Qoder 任务关联流程"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:57:16Z }
stale_after: 2027-01-12
origin: conversation

---

## Background

Qoder 宿主下执行任务关联流程时，`AskUserQuestion` 报错：`AskUserQuestion is only available in Plan mode when async user interaction is enabled. Use AskUserQuestionAsync instead.`——该工具仅计划模式可用。

## 正确做法（Workaround）

1. 改用 `AskUserQuestionAsync` 发布问题（同样只调用一次，保持任务关联框只弹一次的约束）；
2. 发布后无即时回答（返回 `Questions published. No user answer has been received`），用 `Sleep 60000` 等待一个窗口；
3. 仍无回答则按「本次不关联任务」继续正事，不阻塞用户提问——任务关联是可选流程，用户未响应不应死等。

## Rationale

SessionStart hook 硬性要求任务关联弹框先行，但 Qoder 非计划模式下原生工具不可用；这个降级路径保证流程不因工具限制卡死。后续 Qoder 会话遇到同样报错可直接走此路径，不必重新探索。与 `notes/2026-10-21-qoder-任务弹框-4-选项是宿主硬约束不可单框突破优化走正文清单其他输入改-hook-源文件须同步-qoder-副本.md`（options 数量约束）互补：那条讲选项条数上限，本条讲工具的模式可用性。

## 恢复条件

若 Qoder 后续版本放开 AskUserQuestion 的模式限制，可回归同步弹框；hook 指引文案若按宿主区分工具名，本条可退役。
