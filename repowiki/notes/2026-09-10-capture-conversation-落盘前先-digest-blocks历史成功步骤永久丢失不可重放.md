---
type: architecture
title: capture_conversation 落盘前先 digest_blocks：历史成功步骤永久丢失、不可重放
tags:
- architecture
metadata:
  date: 2026-09-10
  task_id: 技能提取
  related_modules:
  - capture
  - tool_digest
  severity: medium
  source_ref: conversations/conv-现在创建技能的整个流程中，是不是只依赖于-@d-repos-CodeWiki-CN-repowiki-wiki-scen.md
  scene: 技能提取 / 采集层
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:43:37+00:00
stale_after: '2027-09-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:09Z'
---

## Background
排查「技能编译漏掉流程主干」时，根因比蒸馏层更靠前一层：信息在采集层就丢了。

## 事实
`codewiki/mcp/tools/capture_conversation.py:221` 在写 raw 之前调用 `digest_blocks(content)`，落盘的是已压缩内容；成功结果早已被 `tool_digest` 的 `return ""` 丢弃。因此**已落盘的对话无法重放**，改 `tool_digest` 只对未来对话有效——历史 188 条笔记 / 9 场景 / 2 技能不会自动变好，也没有任何重放手段。

## 决策/Root cause
采集与压缩耦合在落盘前。这决定了方案取舍：接受历史永久残缺（只保未来不丢），而非人工回填（回填内容无法用原始数据校验、污染溯源链，等于把记忆里的东西装成「从对话蒸馏出来的」）。

## 适用范围
任何「补采集 / 补蒸馏」类需求的边界判断：先确认数据是否还在 raw 里，否则只能改未来。与 decision『技能编译素材以笔记为主、场景为辅』同属本次技能提取改造的底层依据。
