---
type: architecture
title: MCP prompt 与 AGENTS.md 是同一约定的两个载体：静态常驻注入 vs 按需可查询
tags:
- architecture
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - mcp
  severity: medium
  source_ref: conversations/conv-@prompts.py-1294-1308-这个prompt是做什么用的.md
status: stable
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 03:33:29+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T03:40:47Z'
---

## 背景

用户询问 prompts.py 中 task-workflow prompt 是做什么用的。

## 结论

MCP prompt（如 task-workflow）是给 AI 看的按需工作流指引，与 AGENTS.md 是同一套约定的两个载体：
- **AGENTS.md**：静态文档，常驻注入每个会话，token 成本高但零延迟可见；
- **MCP prompt**：注册在 prompts.py（含 description、enabled 开关、arguments 动态参数），通过 prompts/list 按需拉取，可用 prompt 执行器触发（如 task_session_start hook 的 `@command://codewiki/prompt/task-workflow`），且支持传参动态生成正文（如注入当前任务标题）。

prompt 正文里「open the file with the Read tool」这类指引是给 AI 的落地执行指令，不是给人读的文档。

## 适用范围

新增 MCP prompt 或理解 prompts.py 结构时，先判断约定放 AGENTS.md（常驻）还是 MCP prompt（按需）更合适。
