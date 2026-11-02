---
type: pitfall
title: SKILL.md 正文的 get_prompt(name=...) 调用块必须恒为英文 kebab
tags:
- pitfall
metadata:
  date: 2026-10-30
  confidence_level: weak
  task_id: 产品维护
  source_session: 0545f1a6caee476aa40bd29e52e72553
  related_modules:
  - sync_skills
  - prompts
  severity: medium
  source_ref: conversations/conv-codewiki-setup命令，生成的skill为什么没有根据语言生成不同的内容和名称-@SKILL.md-2-2.md
  scene: 技能 name 国际化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.6
  at: 2026-10-30 09:24:57+00:00
stale_after: '2027-04-29'
origin: conversation
verified:
- by: codewiki/5.16.6
  at: '2026-10-31T01:16:46Z'
---

## Background

技能 name 国际化（2026-10-30）后，zh 产物 frontmatter name 是中文（如 `codewiki-蒸馏对话提取记忆和经验`），但 SKILL.md 正文里的 `get_prompt(name="distill-conversations", ...)` 调用块保持英文 kebab。

## Pitfall

`get_prompt` 的 `name` 参数是 MCP prompt registry 标识符（`codewiki/mcp/prompts.py:1692-1695` 只认 registry 名），写成中文会直接查不到 prompt。本地化 name 只影响 frontmatter `name` 与「由用户显式调用 /{skill_name} 触发」提示（sync_skills.py:97-98），标识符与展示层必须分离。

## Rationale

标识符（registry 名、目录名）跨语言稳定，`/` 触发解析（skill_match.parse_skill_frontmatter）、AGENTS.md 引用、prune 口径才能全部锚定同一字符串。值得持久化：编辑技能模板时最容易顺手把调用块一起「本地化」而踩坑。

## 正确做法

编辑技能模板时：frontmatter name / description / 触发提示随 `--lang` 双态；`get_prompt(name=...)`、目录名恒为英文 kebab。`tests/test_sync_skills.py` 已有对应断言（get_prompt 调用块恒英文）。
