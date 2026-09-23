---
type: decision
title: 腾讯云 Harness 文章调研定案：三项借鉴全部不立项，去向 absorbed/deferred/excluded
tags:
- codebuddy
- codewiki
- decision
- pretooluse
- sessionstart
metadata:
  date: 2026-09-23
  confidence_level: weak
  task_id: 产品维护
  related_modules:
  - codewiki-mcp-prompts
  - codewiki-hooks
  source_ref: https://mp.weixin.qq.com/s/SVm_GONXEElhEsX6CXylKg
  reason: 用户在 grill 评审中明确裁决「先不借鉴了」，三项去向判定已逐项确认
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.12.0
  at: 2026-09-23 03:41:30+00:00
stale_after: '2027-09-23'
verified:
- by: human:wangbao
  at: '2026-09-23T06:02:53Z'
---

## Background

阅读腾讯云开发者文章《AI写得快 ≠ 真正提效：一文讲清 Harness“记忆”和“验证闭环”》（作者焦成杰），按竞品调研 SOP 与 CodeWiki 现状逐点代码核对后，用户定案：三项表面差距全部不立项。

## 三项差距的去向判定

1. **PreToolUse 硬拦截「先读知识库再动手」→ absorbed（并入既有规划）**
   - 文章主张 DENY 语义硬拦截；但本仓 `docs/claude-mem借鉴详细设计方案.md` §10.2 已有源码级反证：claude-mem v5 用 PreToolUse deny 拦截 Read，v13 自己改为 allow + 附加上下文（`file-context.ts:190`），~~P2-1~~（拦截）已永久否决。
   - 文章想解决的问题（软约束遵守度差）由 P2-2（SessionStart 软闸门，P2 档最值得、排在 P0 三项之后）覆盖；附加上下文形态对应悬空项 P2-1'（先 spike 验证 CodeBuddy PreToolUse 能力，采纳率数据出来前不立项）。
   - 文章的增量仅为「软约束遵守度差」的一条独立佐证，不改变既有排序。

2. **等待 skill（轮询到终态/按正确维度等/超时如实上报）→ deferred（归「发版本」任务线）**
   - CodeWiki 写入链路同步落盘，唯一非等不可的具体场景是发版时等 PyPI 生效再验证 pip install，属发版流程局部需求，不独立立项。

3. **/close-loop 验证闭环 command（八步固化/运动员裁判员分离/审查成员工具层禁写/循环上限 3 轮）→ excluded（超产品边界）**
   - 文章闭环七步依赖作者公司的 CI/CD、门禁、工单系统，文章自己也说「平台 skill 可整体替换」。CodeWiki 的比较优势是知识飞轮（闭环第八步「知识复盘」恰好是 CodeWiki 已有能力），其余七步做进产品是通用化陷阱。

## 记忆侧对照结论（方向验证）

文章的知识库设计与 CodeWiki 高度同构且 CodeWiki 更完整：两级索引↔wiki/index.md+模块树；三类内容过滤↔四问过滤+路由表；四级成熟度 draft<verified<proven<archived↔draft/stable/superseded（跨场景 proven 由 promotion 门槛 min_adopted:3 等价覆盖）；衰减按类型定周期↔freshness by_type；弱信号（hook 记读日志）/强信号（复盘声明采纳）双通道↔检索命中（telemetry）/采纳声明双通道。明确不借：Obsidian vault+REST API（CodeWiki 是 MCP 原生）、全库衰减扫描高频跑（lint 按需跑）。

## 微借鉴（唯一保留）

「不在中间任何一步静默停下」作为多步骤 prompt 的写作原则，值得在后续新写 prompt 模板时沿用（task-workflow 已有硬性顺序语言，部分覆盖）。

## Rationale

值得沉淀是因为：这是一次完整的「候选必有去向」实践——表面差距经代码核对后全部在既有规划中找到坑位或否决记录，避免重复立项；同时记录了硬拦截 vs 附加上下文两种模式的坑位差异（拦截：状态追踪/同步延迟/打断工作流；附加：上下文膨胀，由 injection_budget 预算闸门可治）。
