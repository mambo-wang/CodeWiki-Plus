---
type: pitfall
title: 引用已有笔记前须检查其 status，deprecated 笔记不应被采纳
tags:
- pitfall
metadata:
  date: 2026-08-29
  related_modules:
  - wiki_search
  severity: medium
  source_ref: conversations/conv-根据-D-repos-CodeWiki-CN-docs-多仓Harness工作区-集中式Wiki布局设计方案.md，结合.md
  scene: 知识检索与引用
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:04:49+00:00
stale_after: '2027-02-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-29T15:14:32Z'
author: wandering-bug
---

## Background

撰写文章时用 query_wiki 检索写作经验，找到笔记《技术文章面向业务读者时应削减实现细节增补业务梳理与开发思路》。

## Pitfall

如果直接按笔记内容执行而不检查其 status，可能采纳已被否决的方案。本例中该笔记状态为 deprecated（用户曾确认不采纳），即「面向公众号削减技术细节」的路线已被否决。

## 正确做法

引用 query_wiki 返回的笔记前，先读取原文确认 status 字段。deprecated 状态的笔记表示该方案已被否决或取代，不应作为行动依据。只有 status=draft 或 confirmed 的笔记才可采纳。
