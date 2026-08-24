---
type: architecture
title: health_score 为扣分制：error-10/warning-3/info-1
tags:
- architecture
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - wiki_lint
  severity: medium
  source_ref: conversations/conv-@command-codewiki-增量更新-Wiki.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:14:21+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:07Z'
reject_reason: 聚合进场景：Wiki页面生成约定与数据结构
---

## 背景

lint 清理后 error=0、warning=0 但 health_score 仍 0/100，与 rebuild_index 重建时计算的 75/100 不一致。

## 事实

_compute_health_score 对每条 issue 扣分：error -10、warning -3、info -1。103 条全部是 info 级提示（no_outlinks 56、superseded_pages 46、note_clusters 1）时扣分仍会把分数压到 0。

## 推论

health_score 被大量提示性 info 拉低不代表格式错误。看分数前先看 error/warning 是否清零；评分逻辑在 handle_lint_wiki 与 rebuild_index 两处一致（都是 0）。
