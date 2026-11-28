---
type: lesson
title: "auto 技能的 description 须用「触发条件」口径而非「工作流摘要」口径，否则模型无法正确自动路由"
tags: ["codebuddy", "lesson"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  task_id: 日常维护
  source_session: "3fcde55205e245a2bb453aed79da0131"
  related_modules: ["sync_skills", "i18n"]
  severity: medium
  source_ref: "conversations/conv-现在初始化或者执行codewiki-setup的时候会生成并拷贝24个skill到智能体对应目录，我发现有些skill给.md"
  scene: "技能自动触发改造"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:53:43Z }
stale_after: 2027-05-27
origin: conversation

---

## Background

技能改为模型可自动触发（`disable-model-invocation` 移除）后，宿主（CodeBuddy/Claude Code 等）靠 SKILL.md 的 description 判断何时自动路由。原 description 是「工作流摘要」口径（描述这个技能是什么），不含触发时机信息，误触发率会偏高。

## 正确做法

**auto 技能的 description 必须改写为「触发条件」口径**——写清什么场景下该用（如 `ingest-note` 加「完成重要决策/踩坑后使用」、`search-wiki` 写「编码前搜模块文档/做决策前搜 decision 笔记时使用」）。2026-10-24 已对 7 个 auto 技能 zh+en 共 14 处 description 同步改写（`codewiki/mcp/locales/zh.yaml`、`en.yaml`），roundtrip 测试校验 description 与 i18n 一致性。

## Rationale

description 是模型自动路由的唯一依据；摘要口径只告诉模型「这是什么」，触发条件口径才告诉模型「何时该用」。后续任何技能加入 auto 集合时都应按此口径改写 description，否则自动触发形同虚设或误触发频繁。
