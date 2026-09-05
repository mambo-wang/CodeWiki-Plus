---
type: architecture
title: ponytail 生效机制：单份 SKILL.md 规则经三层加载档位（T1 指令/T2 技能/T3 hooks）在宿主生效
tags:
- architecture
- dietrichgebert
- github
metadata:
  date: 2026-09-05
  task_id: 他山之石
  severity: medium
  source_ref: conversations/conv-https-github.com-DietrichGebert-ponytail-研究下这个技能是如何生效的.md
  scene: 他山之石-ponytail 调研
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:21:59+00:00
stale_after: 2027-09-05
origin: conversation
reject_reason: 用户裁决不保留：与本任务此前已拒绝的 caveman 机制笔记同类（外部技能机制解剖），非本仓库可复用知识
---

## Background

对 GitHub 仓库 DietrichGebert/ponytail 的研究：技能本体只有一份规则文本（SKILL.md），不复制不分发多份。它靠三层「加载档位」在不同宿主上生效——宿主能力越强生效越自动化，能力越弱退化为纯文本指令。

## Architecture（三层加载档位）

| 档位 | 载体 | 触发方式 | 能力 |
|---|---|---|---|
| T1 指令层 | AGENTS.md、.cursor/rules/*.mdc、.clinerules/、.github/copilot-instructions.md、.kiro/steering/ | 宿主自动读取项目规则文件 | 常驻上下文，无模式切换、无命令 |
| T2 技能层 | skills/*/SKILL.md（ponytail 系列 6 个） | 宿主按 frontmatter 的 description 语义自动判定，或 /ponytail-review 显式调用 | 渐进式披露：常驻只有 name+description，激活才注入正文 |
| T3 插件+钩子层 | hooks/*.js + hooks/claude-codex-hooks.json | 生命周期事件驱动 | 自动激活、每轮注入、模式切换、子代理注入、状态栏 |

关键推论：T2 下系统提示只常驻 name+description，正文要等 use_skill 才进上下文——这正是 ponytail 敢把 description 写得很长的原因（它要当「自动激活的判定器」）。

## T3 hooks 完整生效链路（Claude Code / Codex）

SessionStart(matcher: startup|resume|clear|compact) → ponytail-activate.js；SubagentStart → ponytail-subagent.js；UserPromptSubmit → ponytail-mode-tracker.js。

1. activate.js：读默认模式 → 写 flag 文件 → 输出规则集 →（仅 Claude）检测 settings.json 无 statusLine 时追加状态栏配置提示，用 nudge flag 保证只问一次。
2. mode-tracker.js（唯一 stdin 消费者）：正则匹配 ^[/@$]ponytail；lite|full|ultra|off 切会话模式；default <mode> 才写 config（跨会话）；/ponytail 无参只回报当前档；stop ponytail / normal mode 必须整句匹配才关（否则正常需求如 add a normal mode toggle 会误关）。
3. instructions.js：getPonytailInstructions(mode) 直接 readFileSync 读 ../skills/ponytail/SKILL.md，去 frontmatter 后按档位过滤非当前 intensity 的表格行与示例行；读不到走 getFallbackInstructions() 硬编码兜底。规则只有一份事实源，钩子不复制文本。
4. subagent.js：父线程 SessionStart 上下文到不了子代理，故单独一路注入；PONYTAIL_SUBAGENT_MATCHER 可按 agent_type 正则收敛，解析失败/agent_type 缺失一律 fail-open（照注入）。
5. runtime.js 宿主探测（环境变量）+ 输出契约分叉：Claude Code 默认分支 SessionStart 裸 stdout、SubagentStart 必须 hookSpecificOutput.additionalContext；Codex 看 PLUGIN_DATA 输出 systemMessage + additionalContext；Copilot CLI / VS Code 看 COPILOT_PLUGIN_DATA 或 plugin root 含 .vscode/agent-plugins（只读 SessionStart 的 additionalContext）；Qoder 看 QODER_SESSION_ID（无 SessionStart，只能每轮 UserPromptSubmit 注入）。

## State model（状态分两类）

会话模式 = <stateDir>/.ponytail-active 单个 flag 文件（兼作状态栏数据源，删除即 off）；跨会话默认 = ~/.config/ponytail/config.json 的 defaultMode；优先级 PONYTAIL_DEFAULT_MODE > config > full。

## CodeBuddy 落点（T2）

C:\Users\Administrator\.codebuddy\skills\ponytail\SKILL.md（另有 ponytail-audit / ponytail-debt / ponytail-help，缺 ponytail-gain）。与已有 caveman 机制笔记互补：caveman 是三条注入链路，ponytail 显式画出宿主×载体×档位矩阵，并把会话档位与跨会话默认用不同状态文件分开。
