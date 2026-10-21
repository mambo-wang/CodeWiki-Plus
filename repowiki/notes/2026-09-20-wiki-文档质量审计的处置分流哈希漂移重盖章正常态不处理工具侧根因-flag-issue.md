---
type: procedure
title: Wiki 文档质量审计的处置分流：哈希漂移重盖章、正常态不处理、工具侧根因 flag_issue
tags:
- codewiki
- procedure
metadata:
  date: 2026-09-20
  confidence_level: weak
  source_session: f880020901b44931982aa724834955df
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-文档质量审计-请对-Wiki-文档执行全面质量审计。按以下-3ed82e.md
  scene: Wiki 文档质量审计
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 11:40:34+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:00:11Z'
---

## 背景

对 CodeWiki-Plus 仓库执行全量 `lint_wiki(checks=["all"])` 审计（557 项：0 error / 56 warning / 501 info），需要一套处置分流判据，避免把正常态当问题修、或把工具侧极源问题手工修补。

## 处置分流模式（实测跑通）

1. **stale_evidence（warning）**：逐条读涉及页面并核对当前代码——若文档论断与代码仍一致（只是源码邻近改动导致内容哈希漂移），用 `stamp_evidence` 重新盖章刷新哈希；若论断确实过时才改文档。实测 18 条全部属哈希漂移。
2. **missing_aliases（info）**：直接 `edit_doc_file` 补 aliases。
3. **skill_lint 源材料退役**：SKILL.md 引用的源笔记已聚合进场景页退役时，skill 内容本身仍有效——`flag_issue` 记录待统一更新 source_refs，不要手工改。
4. **工具写入行为导致的 okf_conformance**：如 `distill_conversation.py` 直接写顶层键 `source_conversations`——根因在工具侧，`flag_issue` 等工具修复后批量迁移，不宜手工改产物。
5. **正常态不处理**：`superseded_pages`（知识聚合退役的正常生命周期）、notes 的 `no_outlinks`（笔记无出链是常态）、`isolated_components`（代码结构问题非文档问题）。
6. **无法立即修复的**（low_adoption 重写、coverage 补齐、wiki 页面 no_outlinks 回链）一律 `flag_issue` 落 `.meta/issues.json` 供后续批量处理。
7. **验证**：修复后重跑全量 lint 确认目标项清零。

## Rationale

这是一次完整跑通并验证的审计分流（warning 56→38，stale_evidence/missing_aliases 清零），判据区分了「哈希漂移 vs 真过时」「正常态 vs 真问题」「工具侧根因 vs 产物手工修补」，未来重复审计可直接套用。

## 适用范围

CodeWiki 仓库的周期性文档质量审计；其他仓库可参考分流思路但检查项集合可能不同。
