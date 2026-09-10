---
type: pitfall
title: 弹框工具的 options 条数建议会诱导 Agent 拆成多框，须在注入文案里显式覆盖
tags:
- pitfall
- sessionstart
aliases:
- ask_followup_question 多框
- 任务关联弹框
- 单框列全
- SessionStart 弹框
- options 条数建议
metadata:
  date: 2026-09-10
  task_id: 产品维护
  related_modules:
  - mcp
  - hooks
  severity: medium
  root_cause: Agent 优先服从工具 schema 的 options 建议条数（2-4），而非注入文案隐含的 UX 预期；且旧文案主动要求了第二步弹框。
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 12:10:27+00:00
stale_after: '2027-03-09'
verified:
- by: human:wangbao
  at: '2026-09-10T12:10:38Z'
---

## 背景

用户反馈 SessionStart 任务关联「经常会弹多个框」。排查确认不是 hook 被注册两次（`.codebuddy/settings.json` 只有一条 `SessionStart`，matcher=`startup`），而是 Agent 侧行为：

1. `ask_followup_question` 的 schema 写着 options 建议 2-4 个，Agent 为遵守该建议把 9 个进行中任务拆进多个 question 或分多次调用弹框；
2. 旧注入文案里还有一条「【新建任务两步弹框】…必须再次调用 ask_followup_question」，这是第二/第三个框的直接来源（`codewiki/hooks/task_session_start.py` 旧版）。

## 正确做法

凡通过 hook additionalContext / AGENTS.md / MCP prompt 指示 Agent 弹结构化选择框，必须把 UI 预期写死成**硬约束**，而不是让它读 schema 自行判断：

- 只调用 **1 次** `ask_followup_question`，`questions` 数组里**只放 1 个 question**（`multiSelect=false`）；
- 这一个 question 的 options **一次性列全**：全部候选项 + 「新建…（在输入框直接输入名称）」+「跳过」；
- 显式写明「**不受 schema 2-4 个 options 的建议限制**」；
- 「新建任务两步弹框」降级为兜底：只有用户选了「新建…」却没给名字时才允许弹第二次；用户直接输入的自由文本即视为新名称，不再弹框。

同时用测试把这段注入文案钉住（`tests/test_task_session_start.py::test_active_tasks_listed_in_one_chooser_box`：断言单框关键词、全部 active 任务出现在同一个 options 块、旧「两步弹框」文案必须消失）。

## 根因

工具 schema 里的 options 条数是给 Agent 的**建议值**，不是 UI 上限——实测 11 个选项渲染正常。Agent 在「schema 建议」与「用户真实体验诉求」冲突时，会稳定地服从前者。所以期望的 UX 如果不写进注入文案，就一定得不到。

## 适用范围

所有由 Agent 触发结构化选择框的场景：任务关联、方案选择、笔记/草稿确认、批量处置裁决等。改注入文案后，下一个新会话才生效（本会话的 additionalContext 在 SessionStart 那一刻已注入）。

## 附：副本同步点

本条涉及三份 hook 副本（`codewiki/hooks/` 为源，`.codebuddy/hooks/`、`.qoder/hooks/` 为项目副本）+ `codewiki/mcp/prompts.py` 的 `_TASK_MEMORY_AGENTS_SECTION` 与 `_prompt_task_workflow` + 仓库 `AGENTS.md` 标记块，五处必须同改，否则 install-hooks 下次 upsert 会回滚。
