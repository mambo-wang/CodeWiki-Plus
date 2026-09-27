---
type: procedure
title: 从 GitHub 仓库安装 CodeBuddy 用户级技能的标准流程（以 humanizer-zh 为例）
tags:
- github
- itemtype
- procedure
metadata:
  date: 2026-09-27
  confidence_level: weak
  source_session: 9229108d70934c30a5ee699d6afee8d6
  related_modules:
  - skills
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-107386.md
  scene: 技能安装
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 07:04:05+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-27T07:50:22Z'
---

## Background
2026-09-27 用户要求安装 GitHub 技能 `op7418/Humanizer-zh`（中文版 AI 味文本改写规则集）。

## Procedure
1. 浅克隆到临时目录：`git clone --depth 1 https://github.com/op7418/Humanizer-zh "$env:TEMP\Humanizer-zh"`；
2. 读 `SKILL.md` 确认技能定义与内容；
3. 创建用户级技能目录并复制：`New-Item -ItemType Directory -Force "$env:USERPROFILE\.codebuddy\skills\humanizer-zh"`，把 `SKILL.md`、`README.md`、`CHANGELOG.md`、`LICENSE` 拷入；
4. 清理临时克隆目录：`Remove-Item -Recurse -Force "$env:TEMP\Humanizer-zh"`。

## 结果
安装到 `C:\Users\<user>\.codebuddy\skills\humanizer-zh\`，与英文版 humanizer 并存：中文文本用 humanizer-zh（31 条中文模式，四字格/排比/连接词处理与英文版不同，明确「普通排比、破折号和连接词不再一律修改」），英文文本用 humanizer。重启 CodeBuddy 或新开会话后生效。

## Rationale
浅克隆 + 只拷所需文件 + 即时清理，避免在临时目录留残渣；用户级目录使技能跨仓库可用。
