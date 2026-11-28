---
type: decision
title: ownership closure 用严格多数和删除前旧图避免漏归属
tags:
- decision
aliases:
- ownership closure
- owner 候选
- unresolved_deletions
metadata:
  date: 2026-11-26
  confidence_level: strong
  task_id: 他山之石
  verification:
    test_ref: tests/test_ownership.py
status: stable
author: wanderingbug
generated:
  by: codewiki/5.16.8
  at: 2026-11-26 13:14:22+00:00
stale_after: '2027-11-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-11-27T00:41:12Z'
---

## 决策

- owner 真源是 module tree 节点的完整层级路径；组件未直接登记时，按 `file::Class.method` 逐级回溯 enclosing class。
- 规则固定为同文件 → 同目录 → 一跳正反依赖邻居；只有最高票严格过半才形成唯一候选。最高票并列时保留全部并列候选，唯一相对多数不冒充严格多数。

## 删除与降级

- 删除组件必须用覆盖缓存前的旧图归因；SQLite incremental 与 legacy/full 两条路径都要先快照，否则删除项会从 changes 与 `unresolved_deletions` 中消失。
- `ownership_tree_status` 区分 `loaded/missing/invalid`；树损坏时通过 `ownership_warning` 与日志显式告警，未分配组件继续保留，无法归属的删除进入 `unresolved_deletions`。

## 边界

- 工具只返回 `effective_owner_candidates`，由宿主确认；不修改 module tree 或文档正文，不调用 LLM，也不进入 `change_plan/job_state`。
