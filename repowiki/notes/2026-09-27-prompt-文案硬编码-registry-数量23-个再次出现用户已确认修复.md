---
type: lesson
title: prompt 文案硬编码 registry 数量「23 个」再次出现，用户已确认修复
tags:
- lesson
metadata:
  date: 2026-09-27
  confidence_level: weak
  source_session: 0a1834db4b12470e8f8ab0fdd5de61b9
  related_modules:
  - mcp-prompts
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-变更评估与代码评审-请对最近代码变更做影响范围评估（修改后.md
  scene: sync-commands 变更评审（ADR-0017）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 07:00:05+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-27T07:50:15Z'
---

## Background
`codewiki/mcp/prompts.py` 的 init-wiki / init-workspace prompt 文案（约 :319、:383）写死「把全部工作流提示词（23 个）编译为…」。数字 23 可由 `len(_PROMPT_REGISTRY)` 派生（`prompts.py:1574-1628` 实数 23）。

## 事件
2026-09-27 评审 sync-commands 变更时发现（评审编号 F1，axis=convention），命中已归档教训 `notes/2026-09-07-硬编码中文常量承载可派生数据必然漂移i18n-集中化时应顺带根除.md` 的同款病灶：registry 未来加第 24 个 prompt 时，这两处文案静默变错。用户明确确认修复（文案去掉数字，或构建时注入 `len(_PROMPT_REGISTRY)`）。

## Lesson
同一根因第二次被抓到（2026-09-07 首次归档、2026-09-27 复发），说明靠写代码时自觉不够；评审时应把「文案中的具体数字」默认列为可疑项，核对是否可由代码派生。

## Rationale
硬编码可派生数据必然随迭代漂移，且漂移是静默的——只有评审清单持续盯防才能拦住。
