---
type: decision
title: 设计文档落盘分工：docs/ 存「正在想的事」(方案/ADR)，repowiki/ 存「想明白的结论」(note/query/comparison)
tags:
- decision
metadata:
  date: 2026-09-10
  related_modules:
  - docs
  - repowiki
  - convention
  severity: medium
  source_ref: conversations/conv-我做方案设计的时候，是否应该把设计方案放到repowiki中呢.md
  scene: 落盘分工 / 知识库约定
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:48:15+00:00
stale_after: '2027-09-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:14Z'
---

## Background
用户问「做方案设计时，是否应该把设计方案放到 repowiki」。结论：方案正文放 `docs/`，结论回流 `repowiki/`，不要二选一。

## Decision / 落盘分工
| 位置 | 性质 | 证据 |
|---|---|---|
| `docs/plans/<slug>.md`、`docs/*.md` | 人写的设计方案家园，git 版本化、可评审迭代（「正在想的事」） | 现有 20+ 篇 `XXX设计方案.md`；`docs/plans/knowledge-store-rfc.md:3` 用 Status/Date/Origin 头部 |
| `docs/adr/NNNN-*.md` | 架构级决策，Agent 被要求**先读**、冲突显式标注 | `docs/adr/README.md:3-4`、`docs/agents/domain.md:9,47-51` |
| `repowiki/` | 工具产出/采集的知识层，供 `query_wiki` 检索（「想明白的结论」） | `repowiki/schema.yaml:358-438` page_types 路由 + 新鲜度/lint |

## 具体做法
1. 写方案 → `docs/plans/<slug>.md`（沿用 Status/Date/Origin 头部），长篇/要讨论的版本放这。
2. 收敛出架构决策 → `docs/adr/NNNN-kebab-case-title.md`（判据：会约束未来改动、会被反问「为什么不是另一种」）。
3. 结论沉进 repowiki：`write_doc_file(page_type="query")`→`wiki/queries/`（含问题描述/调研/权衡/结论）；横向对比→`comparison`；技术选型→`ingest_note(note_type="decision")`；踩坑→`pitfall`。

## Root cause
`repowiki/notes/`、`wiki/` 走 OKF frontmatter + `stale_after` + `lint_wiki` 检查，手塞 md 缺 frontmatter 会报警、且 notes 要过 draft→confirm 闸门；设计文档需「讨论中状态」，而 repowiki 语义是「已确认知识资产」。

## 适用范围
任何「这段内容该放哪」的判断。一句话：`docs/` 存正在想的事，repowiki/ 存想明白的结论，中间用 `ingest_note`/`write_doc_file` 显式搬运。
