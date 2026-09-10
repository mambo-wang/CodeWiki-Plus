---
type: Doctrine
title: Team Operating Doctrine
status: stable
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 06:04:40+00:00
metadata:
  source_scenarios:
  - wiki/scenarios/IDE-Hook采集链路方法.md
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
  - wiki/scenarios/代码评审与分析工具方法.md
  - wiki/scenarios/任务记忆系统设计方法.md
  - wiki/scenarios/发布与依赖治理方法.md
  - wiki/scenarios/多仓工作区初始化与增量分析.md
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
  - wiki/scenarios/跨进程锁与临时文件治理方法.md
  notes_at_refresh: 73
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:19Z'
stale_after: '2027-03-09'
---

# Team Operating Doctrine

> **Operating Thesis**: 工具做确定性簿记，推理决策永远在调用方与用户手里；入库必经显式确认闸门。

## Core Principles
- 无状态工具 + LLM 外置：提取/聚合/压缩走 prepare→推理→submit，工具不持模型。
- 确认闸门对等：凡落盘知识都先 draft、confirm 生效，绝不静默确认。
- 显式优于缓存：路径与归属「显式参数 > 布局推导 > session 缓存」，跨进程持久化是事故源。
- 单点收敛：同构逻辑只留一份，新逻辑先找收敛点。
- 候选必有去向：一律落 absorbed/deferred/excluded，排除必填原因。

## Reusable SOPs
- 知识聚合：先问用户 → prepare 取清单与容量预警 → 分组写场景块（UPDATE>MERGE>CREATE，每批最多新建 1）→ 退役吸收笔记 → submit → lint。
- 多文件批处理：逐文件处理 → 落盘 → 立即压缩上下文。
- 新增 MCP 工具：handler + registry schema 两处，交付前跑全量测试。
- 归因调优：先跑探测脚本实测计数再下结论，直觉根因必须被数据证伪。

## Decision Logic
- 收敛通用层前先枚举调用点确认语义一致，否则只改收口点。
- 成本可见性优先于新造能力：先让调用方看到代价，再引导按需展开。
- 语义不同的信号并存不去重；合并判定 related ≠ same，拿不准就不合并。
- 锚点选可观测稳定 ID 与既有元数据，捷径分支也须完成持久化。

## Boundaries & Anti-patterns
- 不自动蒸馏/聚合/刷新 Doctrine：hint 提醒先问用户，触发永远显式。
- 不把中文或结构化文本交给 shell 中间层：一律落文件或用精确 subprocess。
- 不依赖下游幂等当安全网。
- 不绕过 dispatch/schema 校验直连 handler；改契约先分清校验层。
- 不静默失败：配置损坏要打日志，未实现的兜底要么做要么删注释。
- 不假设数据结构形状，先读格式再动手；近似输出不当精确结论。
- 依赖升级勿顺手放宽 lint。

## Agent Rules
- 调用工具前先读工具描述确认参数名；传路径显式传 repo_path。
- 子代理自报结果（测试全绿、落盘状态）须独立复核后再转述。
- 重提交必须携带完整正文，只带裁决说明会覆盖原文。
- 重型分析先收窄范围；聚合后必跑 lint。
- 注入/采集类代码 fail-open：永不非零退出、缺依赖降级。

---

> 最后更新：2026-09-08 · 场景：9 · 笔记：75
