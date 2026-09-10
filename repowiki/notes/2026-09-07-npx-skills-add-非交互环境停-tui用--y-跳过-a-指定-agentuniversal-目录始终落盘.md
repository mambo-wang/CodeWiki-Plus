---
type: pitfall
title: npx skills add 非交互环境停 TUI：用 -y 跳过、-a 指定 agent；Universal 目录始终落盘
tags:
- pitfall
metadata:
  date: 2026-09-07
  related_modules:
  - skills
  severity: medium
  source_ref: conversations/conv-安装-npx-skills-add-tt-a1i-archify-g-技能.md
  scene: 技能安装
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 02:59:57+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:15Z'
reject_reason: consolidated into IDE-Hook采集链路方法
---

## 背景

非交互环境（Agent 会话）执行 `npx skills add tt-a1i/archify -g` 时命令停在交互式 TUI（选择安装到哪些 agent），看似未完成。

## 正确做法

1. **加 `-y` 跳过交互提示**；指定目标 agent 用 `-a/--agent codebuddy`（安装到 `~/.codebuddy/skills/`，copy 方式）。
2. Universal 目录（`~/.agents/skills/`）是「always included」的全局位置——即使 TUI 未完成选择，全局安装实际已落盘。
3. `skills@1.5.23` 要求 [Node](../../codewiki/src/be/dependency_analyzer/models/core.py) `>=22.20.0`；本地 [Node](../../codewiki/src/be/dependency_analyzer/models/core.py) v20.19.0 只出 EBADENGINE 警告、不阻塞安装，但后续兼容问题需升级 [Node](../../codewiki/src/be/dependency_analyzer/models/core.py)。
4. 安装 CLI 自带提示：技能以完整 agent 权限运行，首次使用前应浏览 SKILL.md 确认可信。

## 适用范围

npx skills（skills CLI）跨 agent 技能安装；archify 技能用于架构/时序/数据流/状态图渲染为带内联 SVG 的可交互独立 HTML。
