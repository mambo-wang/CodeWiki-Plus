---
type: architecture
title: 宿主命令映射口径：仅 CodeBuddy 自动映射 MCP prompt，其余宿主均需 sync-commands 薄壳
tags:
- architecture
- codebuddy
metadata:
  date: 2026-10-09
  confidence_level: weak
  task_id: 产品维护
  source_session: 09354b56591d451e887b21cdc7d615c8
  related_modules:
  - codewiki/cli/commands/sync_commands
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-9f00fb.md
  scene: sync-commands 宿主命令编译
status: stable
author: Administrator
generated:
  by: codewiki/5.14.1
  at: 2026-10-09 01:25:39+00:00
stale_after: '2027-10-09'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-09T01:26:57Z'
---

## Fact（用户明确纠正的宿主行为口径）

- 目前已知**只有 CodeBuddy 会自动把 MCP prompt 映射为宿主斜杠命令**；其他宿主（Qoder、Trae、Claude Code、Gemini CLI 等）都需要 `codewiki sync-commands` 把工作流提示词编译为命令薄壳（`<宿主配置目录>/commands/codewiki/*.md`）才有可见入口。旧文案「Trae 会自动转化，跳过也无妨」**不准确**，已按此口径纠正。
- 命令薄壳是薄壳：内容只写「如何调用 `get_prompt(name=...)` 获取全文」，权威源始终在 MCP `get_prompt`；薄壳是 `sync-commands` 生成的快照，手改会被下次覆盖。

## 宿主自动判定（已实现，无需用户选择）

`codewiki/cli/commands/sync_commands.py` 的 `_resolve_targets` 判定优先级：显式 `--ide` 参数 > 枚举项目根下非 codebuddy 的智能体配置目录 > 兜底 `.trae`。「sync-commands 不用用户选、自动判断即可」的产品要求现状已满足。

## Rationale

该口径直接决定 init-wiki/init-workspace 把 sync-commands 列为必做步骤的合理性（无薄壳则多数宿主用户看不到任何命令入口），也是后续任何涉及宿主命令可见性、prompt 到命令映射工作的基础事实，值得跨任务持久。与既有笔记《sync-commands 的 _STUB_TEMPLATE.format() 对 i18n description 中的花括号零防御》主题不同（那条讲模板转义脆弱点，本条讲宿主映射口径），不构成重复。
