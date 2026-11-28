---
type: decision
title: tree repair 默认观察显式应用且只修复确定性漂移
tags:
- decision
aliases:
- tree repair
- 模块树修复
- observe apply
metadata:
  date: 2026-11-26
  confidence_level: strong
  task_id: 他山之石
  verification:
    test_ref: tests/test_tree_repair.py
status: stable
author: wanderingbug
generated:
  by: codewiki/5.16.8
  at: 2026-11-26 14:51:55+00:00
stale_after: '2027-11-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-11-27T00:41:12Z'
---

## 决策

- 模块树修复作为纯函数接入现有增量链路，不新增 MCP 工具，也不把 LLM 聚类或路由搬进工具层。
- 默认 observe：`analyze_repo.changes.tree_repair` 与 `save_module_tree` 只返回计划，保存宿主提交的原树；只有显式 apply 才应用修复。
- 固定顺序为 rename → delete → 后序剪空节点 → add。rename 目标冲突时保留原树；重复组件归属显式报错；未知 ID 不被猜成删除；rename 源缺失时当前目标重新进入 add/orphan。

## 归因与增长

- add 依次使用同文件严格多数、同目录唯一 leaf、一跳正反依赖邻居严格多数；最终仍无法唯一归属时保留候选并进入 unplaced，不把相对多数冒充严格多数。邻居投票包含非 leaf owner。
- growth 只按实际新增组件占修复后 leaf 组件数计算，默认阈值 0.33；超阈值仅告警，不创建新 leaf、不触发重聚类。

## 会话与真源

- 复用 B1 的本轮 `component_changes` 和 B2 的 owner map/严格多数/邻居投票，避免第二套 diff 与归属语义。
- 同仓重分析按创建顺序选最新会话；缓存恢复会话没有本轮 diff 时拒绝 apply，避免拿空 diff 或旧图执行修复。
- 位置证据统一 Windows 分隔符、`./` 与平台大小写语义。工具不自动改正文，不绕过 confirm/lint 闸门。
