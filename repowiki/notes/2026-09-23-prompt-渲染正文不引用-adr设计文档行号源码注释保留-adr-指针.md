---
type: decision
title: "prompt 渲染正文不引用 ADR/设计文档/行号，源码注释保留 ADR 指针"
tags: ["decision"]
metadata:
  date: 2026-09-23
  confidence_level: weak
  task_id: 产品维护
  source_session: "bb80ce6d0e5b4cf8a6af19bcb6e6b54a"
  related_modules: ["codewiki-mcp-prompts"]
  severity: medium
  source_ref: "conversations\\conv-working_memory_content-The-following-is-the-existing-working-4.md"
  scene: "产品维护/prompts.py 清理"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.12.0, at: 2026-09-23T01:11:28Z }
stale_after: 2027-09-23
origin: conversation

---

## Background

`codewiki/mcp/prompts.py` 中渲染进 prompt 正文的内容（发给运行时 Agent 的指令文本、写入 AGENTS.md 的协议块）大量引用了 `ADR-0002`、`ADR-0014`、`docs/xxx设计方案.md §4`、`P1 C 线`、`T2+T3`、`handler: source_ingest.py:741` 等决策溯源信息。用户提出这些引用没有必要，prompts.py 只描述当前实现即可。

## Decision

区分两类受众，分别处理：

1. **渲染进 prompt 正文的内容**：清理所有 ADR 编号、设计文档地址、历史决策变动标签（如 `P1 C 线`、`T2+T3`）、源码行号引用。消费方 Agent 只需要知道「当前行为是什么」，不需要知道「这个行为是哪号决策定的」。
2. **Python 源码注释/docstring**：保留 ADR 指针（如 `# 采集开关（ADR-0014）`），这是给维护者溯源用的，与渲染正文是两个受众。

清理涉及 `_ACTIVE_SETTLE_HOST_SECTIONS`（qwenwork 小节）、`_active_settle_section()` 正文、`_task_management_wiring_steps()`、`distill-conversations` / `task-workflow` / `consolidate-knowledge` / `skill-creator` / `promote-note` / `retract-source` 等 prompt 模板，共清理 13 处；源码注释中剩余 13 处 ADR 指针按约定保留。

## Rationale

对运行时 Agent 而言决策溯源信息是纯噪音，增加 token 消耗且无行为指导价值；而维护者需要 ADR 指针定位历史决策。值得沉淀是因为这是「渲染正文 vs 源码注释」受众分离的通用原则，后续新增 prompt 模板时同样适用。

## 正确做法

- 新写 prompt 模板时，正文只描述当前行为，不带 ADR/文档/行号引用；溯源指针写在 Python 注释里。
- 清理此类字符串前，先搜索 `tests/` 确认没有测试断言渲染后的 prompt 正文包含这些字样（本次确认无断言后才动手，相关 6 个测试文件 144 passed）。
