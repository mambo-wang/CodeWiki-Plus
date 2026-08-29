---
type: decision
title: analyze_workspace 增量模式：内部自动判断做主路径，锚点复用 metadata.json
tags:
- decision
metadata:
  date: 2026-08-29
  task_id: 多仓工作区
  related_modules:
  - workspace_analyzer
  - analysis
  severity: high
  source_ref: conversations/conv-工作区已有部分初始化痕迹（bootstrap.ps1-登记了业务仓、.gitignore-已排除等）时，init_wor.md
  scene: 多仓工作区增量分析设计
  consolidated_into:
  - wiki/scenarios/多仓工作区初始化与增量分析.md
status: stable
generated:
  by: codewiki/5.5.0
  at: 2026-08-29 15:03:52+00:00
stale_after: '2027-08-29'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-29T15:14:31Z'
---

## Background

analyze_workspace 产出跨仓拓扑缓存（routes/links/infra）+ 工作区 overview.md。单仓层增量链已闭环（watch_repo + analyze_changes + agent 改写 + review_changes/doc_update_notify），缺的是 workspace 层增量编排。

## Decision

不补新工具，给 analyze_workspace 加增量模式。内部自动判断做主路径（agent 多半无脑传全量，显式参数增量名存实亡）；留 force=true 逃生门，repos=[...] 白名单不加（YAGNI）。

### 锚点设计

复用 metadata.json 已有的 commit_id 作锚点，不新建 analysis_state.json。一个机制覆盖首跑/新登记仓/代码变更/版本升级/锚点或缓存丢失，后两者安全降级为该仓全量，零配置。

### 三档分派

workspace_analyzer 对每个仓判定为：跳过复用缓存 / 全量重跑 / deferred。拓扑合并从各仓 SQLite 缓存读 routes，跳过仓近乎零增量成本。overview 对跳过仓读持久化 summary.json 补统计。

### 正文层增量

变更仓仍重跑 analyze_repo 刷新图和路由避免拓扑失真。增量收益拿在正文层：analyze_changes 出受影响清单，agent 只重写清单页面（prompt 补增量规则）。改写归 agent，工具不持模型。

### 分叉定案

A1 变更仓重跑 analyze_repo 进 v1；A2 watch 机制单次增量同步（指纹判定/缓存原子写/并发竞态）作后续优化不进 v1。

## 实施细节

cache.py 引入 analysis_meta_dir / resolve_analysis_meta_file 缝（centralized 下 metadata.json/module_tree.json 落 <ws>/.codewiki/<repo>/，colocated 不变）。踩坑：git status untracked 噪音需过滤；Path 对象不能直接 JSON 序列化（需 str()）。验证：ruff 过、全量 593 个测试通过。
