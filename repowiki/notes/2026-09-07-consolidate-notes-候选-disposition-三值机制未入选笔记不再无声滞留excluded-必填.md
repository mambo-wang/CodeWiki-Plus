---
type: decision
title: consolidate_notes 候选 disposition 三值机制：未入选笔记不再无声滞留，excluded 必填 reason
tags:
- codewiki
- decision
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - note_consolidation
  - registry
  - prompts
  severity: medium
  source_ref: conversations/conv-https-mp.weixin.qq.com-s-NwU98lA_P7LpDdyhhkt-cg-调研一下这篇文章，看看对.md
  scene: note 聚合可审计性
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.1
  at: 2026-09-07 01:42:36+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: codewiki/5.6.1
  at: '2026-09-07T01:47:01Z'
reject_reason: consolidated into Wiki页面生成约定与数据结构
---

## Background

有赞《KNOWLEDGE WIKI》一文提出「候选必须有去向，排除要写原因」（生成侧初始化时概念被丢没记录）。对照 CodeWiki，映射到**聚合侧**的同类缺口（方向相反）：consolidate_notes 的 `_pending_confirmed_notes` 只按「status ∈ stable/confirmed 且无 consolidated_into」筛，溯源只写在入选者身上（`consolidated_into` 双向链接），**未入选者零标记**——既没有「为什么没入选」，也没有「这条已经判过」。后果：每次 prepare 都要重新权衡同一批笔记，无法区分「还没轮到」与「判定不值得聚合」；后者永久卡在 pending 顶着 `notes_since_last_consolidation` 计数器（实测 41 / 阈值 10，持续告警）。

## Decision

用户确认实现「候选 disposition 三值机制」（verdict 三值、四处全做，含 excluded 从 pending 剔除以缓解计数器告警）：

- 复用既有收敛点 `_update_frontmatter_meta`（locked RMW）写回，不新建写回函数。
- verdict 三值：`absorbed`（已入场景块，走现有 source_notes ⇄ consolidated_into，不用新增）、`deferred`（本轮不聚合，等素材/同类积累，reason 可选）、`excluded`（判定永不入场景块：一次性任务状态/个人偏好/临时上下文，**reason 必填**）。
- 落盘形态：笔记 frontmatter `metadata.disposition: {verdict, reason?, at}`。

改动清单（4 处约 40 行）：
1. `registry.py` consolidate_notes report 增加可选 `dispositions: [{file, verdict, reason?}]`；
2. `note_consolidation.py` submit 加校验与写回，`excluded` 无 reason 直接进 errors（沿用 `action=deleted` 要求正文为 [DELETED] 的校验风格）；
3. `_pending_confirmed_notes` 候选筛选中 `excluded` 跳过不再进 pending，`deferred` 保留但回带 disposition 字段；
4. 提示词 `_CONSOLIDATE_SYSTEM` 与 `prompts.py` 各加「每条候选必须给出去向」。

## 明确不做

- `lint_wiki` 加「长期 deferred 告警」：覆盖完整性审查的落点在此，但阈值现在定是拍脑袋，等 disposition 积累几轮再定。
- 不改 `distill_conversation`：蒸馏候选是 raw 对话，submit 后即删，不存在滞留问题。

## Rationale

借鉴建议必须先过代码核对，且要纠正方向映射（文章是生成侧「候选无声消失」，我们是聚合侧「候选无声滞留」——同一可审计性缺口，方向相反）。最小做法是复用 `_update_frontmatter_meta`（note_consolidation.py:134，locked RMW），不新建写回路径。
