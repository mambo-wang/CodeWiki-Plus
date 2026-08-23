---
type: decision
title: "会话启动时的 query_wiki/蒸馏等重操作委托 subagent 执行，避免阻塞用户正常使用"
tags: ["decision", "readfile"]
metadata:
  date: 2026-08-23
  task_id: 产品维护
  related_modules: ["task_manager"]
  severity: medium
  source_ref: "conversations/conv-开始新对话触发选择任务后，会有query_wiki以及蒸馏操作，这些操作可以放到subagent执行吗，别影响用户正常使.md"
  scene: "任务记忆/补蒸馏"
status: draft
generated: { by: codewiki/5.3.0, at: 2026-08-23T08:00:48Z }
stale_after: 2027-08-23
origin: conversation

---

## Background

用户提出：开始新对话触发选择任务后，会有 query_wiki 以及蒸馏操作，这些操作如果由主 Agent 亲自执行会阻塞用户正常使用——主 Agent 埋头逐条 read_file 读 raw 原文、提取知识，用户提问被明显拖慢，且大量对话原文灌入主会话上下文。

## Decision

将补蒸馏等重操作委托 subagent 执行：创建 `.codebuddy/agents/distill-worker.md`（project 级、agentic 模式，授权 ReadFile + codewiki MCP），主 Agent 在检测到 pending_raw_count > 0 时用 Task 工具 spawn 它后台执行 Mode C 蒸馏（prepare → 逐条 read_file 提取 → submit），主 Agent 不等蒸馏完成，直接开始回答用户提问；在自然停顿点拉取结果并向用户展示待确认项。

## Rationale

- 上下文隔离：raw 原文在 subagent 独立上下文消化，主会话只留摘要级信息。
- 不阻塞：spawn 后主 Agent 立即返回用户问题，蒸馏后台完成。
- 权限最小化 + 评审闸门分离：subagent 仅授权 ReadFile + codewiki MCP，且不执行 confirm_note/confirm_task_memories——正式落盘必须由主 Agent 与用户确认。
