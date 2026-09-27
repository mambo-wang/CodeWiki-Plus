---
type: lesson
title: humanizer-zh 润色时字面命中模式清单不等于该改：多模式叠加才是证据，通顺文字不强改
tags:
- codewiki
- lesson
metadata:
  date: 2026-09-27
  confidence_level: weak
  source_session: 9229108d70934c30a5ee699d6afee8d6
  related_modules:
  - skills
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-107386.md
  scene: 文章润色
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 07:02:41+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-27T07:50:25Z'
---

## Background
2026-09-27 用 humanizer-zh 技能润色 `docs/articles/CodeWiki-Plus系列12：四个DeepWiki复刻的源码横评.md` 时，全文命中多处模式清单的字面特征，但逐处回到上下文权衡后全部保留，未做正文修改。

## Lesson
技能规则明确「没有问题的段落可以原样保留」「不要为了展示工作量强行修改已通顺的文字」。字面命中不等于该改：
1. 批评性横评里的立场声明（「这不是要踩谁」）是作者真实立场，不是假想敌辩护；
2. 三个并列论断后文逐一验证，不是强凑三连；
3. 中文技术博客惯用口吻（「值得细品」）不是空尾巴；
4. 逐个检查过的破折号若都承担解释/插入/转折功能，不算滥用；
5. 作者声音的亮点（口语化点评）正是技能要求保护的部分。

判定标准是**多个模式叠加出现**才构成证据，单一特征不动手。

## Rationale
润色技能的价值在于识别真问题而非展示修改量；对已通顺文字强行改动会破坏作者声音，比 AI 腔更有害。
