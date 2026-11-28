---
type: pitfall
title: "distill-conversations 自动触发是 Doctrine「触发永远显式」边界的用户点名例外：需观察误触发，回退只需删 auto 标记"
tags: ["pitfall"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  task_id: 日常维护
  source_session: "3fcde55205e245a2bb453aed79da0131"
  related_modules: ["sync_skills", "prompts", "distillation"]
  severity: medium
  source_ref: "conversations/conv-现在初始化或者执行codewiki-setup的时候会生成并拷贝24个skill到智能体对应目录，我发现有些skill给.md"
  scene: "技能自动触发改造"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:53:50Z }
stale_after: 2027-05-27
origin: conversation

---

## Background

用户指定把 `distill-conversations` 技能改为模型可自动触发，但 Team Doctrine 的 Boundaries 明确写着「不自动蒸馏/聚合/刷新 Doctrine：hint 先问用户，触发永远显式」。两者直接冲突。

## 处置

- 用户明确要求，实施时照做（commit `484b775`），但需持续观察误触发情况；
- 若发现模型在会话中未经用户确认自动触发蒸馏，回退这一条技能的 auto 标记即可（单点改动，`_PROMPT_REGISTRY` 删 `"auto": True` + 重跑 `codewiki sync-skills`）。

## Rationale

这是「用户显式指令优先于 Doctrine 边界」的已记录例外：Doctrine 是默认做事方式而非硬约束，用户点名时可越界，但例外必须留痕、可回退。后续会话若发现蒸馏被自动触发，应先查本条例外记录再判断是回退还是接受。
