---
type: pitfall
title: subagent 定义的 frontmatter 按宿主家族分发，同名文件不同 schema
tags:
- codebuddy
- codewiki
- pitfall
- readfile
aliases:
- distill-worker frontmatter
- resolved tool set is empty
- subagent 空工具集
- agent_file 变体
- Qoder subagent 定义
metadata:
  date: 2026-08-29
  related_modules:
  - ide_config
  - install_hooks
  severity: medium
  root_cause: subagent 定义的 frontmatter 是宿主专属 schema：CodeBuddy 的 tools/toolsMCP 字段在
    claude 家族（Qoder/Claude Code/Gemini CLI）下无法解析，工具名全部落空导致宿主拒绝加载。
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:32:23+00:00
stale_after: '2027-02-25'
verified:
- by: human:wangbao
  at: '2026-08-29T15:32:29Z'
---

## 背景

CodeWiki 的 `install_for_ide` 曾把同一份 `codewiki/agents/distill-worker.md` 拷给所有 IDE。在 Qoder 会话里 spawn 该 subagent 时报 `Agent type 'distill-worker' is unavailable because its resolved tool set is empty`，补蒸馏委托不可用。

## 根因

各宿主的 subagent frontmatter schema 不同：CodeBuddy 认 `tools: ReadFile` + `toolsMCP: codewiki` + `agentMode/enabled` 等私有字段；claude 家族（Qoder/Claude Code/Gemini CLI）认 `name/description` + `tools: Read, Write, mcp__<server>__<tool>`。把 CodeBuddy 版喂给 claude 家族宿主时，所有字段都解析不出来，工具集为空，宿主直接拒绝该 subagent。

## 正确做法

1. 按宿主家族发变体：`IDE_SPECS` 增加 `agent_file` 契约，qoder/claude-code/gemini-cli 指向 `codewiki/agents/distill-worker.claude.md`（claude 家族 frontmatter），codebuddy 用默认 `distill-worker.md`。
2. 安装后的目标文件名始终是 `distill-worker.md`（宿主按稳定名查找），变体缺失时回退默认源（降级但不断线）。
3. 变体正文里的工具名也要随宿主改（`ReadFile` → `Read` 工具）。
4. 验证注意：宿主的 subagent 注册表是**会话启动时快照**，改完定义文件后本会话内重跑仍报同样错误，必须开新会话才能验证生效。

## 适用范围

所有「同一份配置文件分发到多个宿主」的接线场景（hook 命令、settings.json、agent 定义）：同名≠同 schema，分发前先确认目标宿主的解析格式；新增 IDE 时在 `IDE_SPECS` 登记差异，而不是让所有家族共用一份。
