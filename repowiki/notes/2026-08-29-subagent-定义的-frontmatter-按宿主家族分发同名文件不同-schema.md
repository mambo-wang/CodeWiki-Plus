---
type: pitfall
title: subagent 定义按宿主家族分发：同名不同 schema，且 MCP 权限模型各异
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
- subagent MCP 不透传
metadata:
  date: 2026-08-29
  related_modules:
  - ide_config
  - install_hooks
  severity: medium
  root_cause: 三层宿主差异叠加——frontmatter schema 不同（CodeBuddy 私有字段在 claude 家族解析为空工具集）；tools
    显式枚举的 mcp__ 限定名不透传给子代理； MCP 服务器连接本身不透传给自定义子代理运行时。
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:32:23+00:00
stale_after: '2027-02-25'
verified:
- by: human:wangbao
  at: '2026-08-29T15:32:29Z'
- by: human:wangbao
  at: '2026-08-29T15:49:48Z'
---

## 背景

CodeWiki 的 `install_for_ide` 曾把同一份 `codewiki/agents/distill-worker.md` 拷给所有 IDE。在 Qoder 里补蒸馏委托接连撞上三个问题：先是报 `Agent type 'distill-worker' is unavailable because its resolved tool set is empty`，修好 frontmatter 后又发现子代理拿不到 MCP 工具，Mode C 蒸馏走不通。

## 根因（三轮实证）

1. **schema 差异**：CodeBuddy 认 `tools: ReadFile` + `toolsMCP: codewiki` + `agentMode/enabled` 等私有字段；claude 家族（Qoder/Claude Code/Gemini CLI）认 `name/description` + 可选 `tools`。把 CodeBuddy 版喂给 claude 家族宿主，字段全部解析不出来，工具集为空，宿主直接拒绝加载。
2. **显式枚举不透传**：claude 家族变体写 `tools: Read, Write, mcp__codewiki__distill_conversation` 时，内置工具名（Read/Write）解析正常，但 `mcp__` 限定名不进子代理工具集。
3. **MCP 连接不透传给自定义子代理**：省略 `tools` 行（继承语义）后 spawn 正常、内置工具与 MCP 元工具（mcp_list/get/call）齐备，但自定义子代理运行时**不连接任何 MCP 服务器**（其 `mcp_list` 为空），Mode C 仍走不通。对照：宿主**内置**子代理类型（如 general-purpose）有 MCP 权限。

## 正确做法

1. 按宿主家族发变体：`IDE_SPECS.agent_file` 契约，qoder/claude-code/gemini-cli 指向 `distill-worker.claude.md`，codebuddy 用默认源；目标文件名恒为 `distill-worker.md`，变体缺失回退默认源（降级但不断线）。
2. claude 家族变体**省略 `tools` 行**（继承最稳），不要枚举 `mcp__` 限定名。
3. 在 MCP 不透传自定义子代理的宿主（Qoder 实测），补蒸馏委托改为 spawn **内置 general-purpose 子代理**，以 `distill-worker.md` 正文为执行剧本（其 Mode C 流程描述宿主无关）。
4. 验证注意：宿主 subagent 注册表是**会话启动时快照**，改完定义文件必须开新会话验证；MCP 权限问题要用子代理自己的 `mcp_list` 确认，不能只看 spawn 成功与否。

## 适用范围

所有「同一份配置分发到多宿主」的接线场景：同名≠同 schema，同 schema≠同权限模型（工具名解析与 MCP 路由是两层，须分别实测）。新增 IDE 时在 `IDE_SPECS` 登记差异并用独立新会话实测两层，而不是让所有家族共用一份。
