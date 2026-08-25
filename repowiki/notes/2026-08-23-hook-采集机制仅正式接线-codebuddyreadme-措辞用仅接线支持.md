---
type: architecture
title: hook 采集机制仅正式接线 CodeBuddy，README 措辞用「仅接线支持」
tags:
- architecture
- codebuddy
- sessionend
- sessionstart
metadata:
  date: 2026-08-23
  task_id: 产品维护
  related_modules:
  - task-memory
  - mcp
  severity: medium
  source_ref: conversations/conv-现在codewiki-plus开启hook机制，支持那些智能体，目前我只知道支持codebuddy-@prompts.p.md
  scene: team-memory-hook 支持范围
status: stable
generated:
  by: codewiki/5.3.0
  at: 2026-08-23 07:40:26+00:00
stale_after: '2027-08-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:21Z'
---

## Background

用户询问 codewiki-plus 开启 hook 机制后支持哪些智能体。排查源码后确认：目前**仅 CodeBuddy 正式接线并验证**，但采集脚本底层已对 Claude Code 留了兼容设计，README 需准确描述这一边界。

## 支持范围（分层结论）

1. **正式支持：仅 CodeBuddy**。接线层完全 CodeBuddy 特有：`.codebuddy/settings.json` 注册 `hooks.SessionStart/SessionEnd`（命令是写死的绝对路径）；`.codebuddy/hooks/task_session_start.py`、`capture_session_end.py` 按 CodeBuddy 期望的 `{continue, systemMessage}` 形状输出；MCP prompt `team-memory-hook` 只操作 `.codebuddy/settings.json`。
2. **采集脚本层对 Claude Code 有显式兼容（未接线、未验证）**：`_ide_hook.py` 载荷解析事件无关（`transcript_path`/`transcript` + 内联 turns 多 key 兜底）；`task_session_start.py` 仓库路径解析优先级 `CODEBUDDY_PROJECT_DIR`（CodeBuddy）→ `CLAUDE_PROJECT_DIR`（compat）→ 事件 `cwd`。即只要其他 agent 的 hook 能注入 transcript 载荷即可被消费，缺的只是 `.claude/settings.json` 注册文件。
3. **其他 agent（Cursor/Windsurf/Gemini CLI 等）**：无代码无文档提及，属「理论上可用、实际未适配」。

## README 表述决策

用户要求把「hooks 暂时仅支持 codebuddy」写进 README。**措辞用「仅接线支持」而非「仅支持」**：因为底层采集脚本已做 CodeBuddy/Claude-Code 兼容的事件载荷解析，只是缺少其他 IDE 的注册文件，用「仅接线支持」更准确、避免误导。已同步写入 README 中英两处「团队记忆融合→关键约束」章节（中文 ~383-387 行、英文 ~996-1000 行）。

## 扩展其他 IDE 的方法

仿照 `.codebuddy/settings.json` 生成 `.claude/settings.json`，把 `SessionEnd`/`SessionStart` 事件注册到同一批 wrapper 脚本即可。

## Rationale

「仅支持」会让人误以为底层完全不兼容其他 IDE；实际采集层已通用化，缺口只在注册文件，因此「仅接线支持」是准确表述。

## 相关文档

- [IDE-Hook 采集链路方法](../wiki/scenarios/IDE-Hook采集链路方法.md)
