---
type: task
task_id: Experience-通道调研
title: Experience 通道调研
status: active
created_at: 2026-09-12T00:26:14.959275+00:00
---

评估 HL-Mem 的 Experience 通道（Episode/Trace/Policy 归纳，src/hl_mem/experience/service.py）是否值得本仓借鉴（来源：docs/HL-Mem-调研与借鉴分析.md §六「明确不借鉴」末行——与任务记忆/场景块职责部分重叠但形态不同，值得单独立项评估，本轮不 absorb）。

核心问题：Episode/Trace/Policy 与本仓任务记忆（任务作用域进度知识）+ 场景块（检索知识）的职责边界在哪，是否存在真实缺口。克隆已归位 D:/repos/hl_mem（基线 aa5d0688 / v1.1.7 / 2026-09-09）。
