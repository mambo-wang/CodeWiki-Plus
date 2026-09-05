---
type: pitfall
title: 删除 raw/sources 下某 source 前先盘点引用与 source id 所有权：删后 10 页断链 + README_CN source
  id 易主导致张冠李戴
tags:
- pitfall
- weknora
metadata:
  date: 2026-09-05
  related_modules:
  - retract_source
  - wiki_pages
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-2.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:35:12+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:50Z'
---

## Background

2026-09-05 清掉误导入的 WeKnora README_CN（raw/sources/README_CN.md + wiki/sources/README_CN.md），随后发现 `README_CN` 这个 source id 已被 TAM README 独占。

## 后果（已实测确认）

- WeKnora 系 10 个页面（entities 4 + concepts 6）frontmatter 写 `resource: raw/sources/README_CN.md`、正文用 `[^src:README_CN:59]`，文件删除后**全部断链**，溯源能力丢失。
- 更隐蔽：这些页面继续用 `README_CN` 这个 source id，而它现在归 TAM 独有——按 `README_CN:59` 溯源会跳到 TAM 文档 `.env` 配置段，得到**张冠李戴的错误证据**。

## 正确做法

删除/重命名 source 前先盘点：①哪些页面引用该文件（resource 字段）；②引用它的 source id 是否会被其他源占用。断链有 lint（stale_refs/broken_links）可查，但 id 易主造成的语义错引 lint 查不出。

## 备注

清理时保留与 source 无关的自身决策笔记（如 2026-08-03 的 WeKnora 两阶段提取决策）是对的——记录方法论的笔记不随某次抽取产物删除。
