---
type: Doctrine
title: Team Operating Doctrine
status: stable
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:52:17+00:00
metadata:
  source_scenarios:
  - wiki/scenarios/IDE-Hook采集链路方法.md
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
  - wiki/scenarios/任务记忆系统设计方法.md
  - wiki/scenarios/发布与依赖治理方法.md
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
  notes_at_refresh: 27
verified:
- by: human:wangbao
  at: '2026-08-24T16:13:34Z'
stale_after: '2027-02-21'
---

# Team Operating Doctrine

> **Operating Thesis**: 工具只做确定性簿记，推理与决策永远在调用方 agent 与用户手里；进入知识库的内容必须经显式确认闸门。

## Core Principles
- 无状态工具 + LLM 外置：提取/聚合/压缩走 prepare→调用方推理→submit，工具不持模型不推断，跨 IDE 可移植。
- 确认闸门对等：凡落盘知识（笔记、任务记忆、场景块、Doctrine）都先 draft/pending，经 confirm 生效；绝不静默确认。
- 显式优于缓存：路径/归属/优先级解析统一「显式参数 > 可推导 > session 缓存」；不依赖隐式副作用。
- 单点收敛：同构逻辑只留一份实现；新逻辑先找已有收敛点。

## Reusable SOPs
- 知识聚合：超阈值时 prepare 取清单与预警 → 按对象分组写场景块（UPDATE 优先）→ 退役吸收笔记 → submit → lint。
- 多文件批处理：逐文件处理 → 落盘 → 立即压缩上下文 → 下一文件，不累积。
- 新增 MCP 工具：tools/ 实现 handler + registry 注册 schema（含枚举联动），交付前跑全量测试。

## Decision Logic
- 会话锚点选可观测稳定 ID（source_session_id），不选内存态——有 TTL 且并发会静默污染。
- 噪声暂存宁删不留：暂存区非仓库，显式 keep 才保留。
- 合并判定 related≠same，拿不准就不合并。

## Boundaries & Anti-patterns
- 不要自动蒸馏/聚合：触发永远显式；hint/计数器提醒先询问用户再执行。
- 不要绕过 dispatch/schema 校验直连 handler；不要用全局单值文件做并发锚点。
- 不要假设数据结构形状（索引分片、引用树已有教训）；先读格式再动手。
- 剥离注入块的正则不要用行首锚点——捕获层可能给行加角色前缀。
- 归档副本可能原样保留 token：推送前扫描脱敏，防密钥扫描拦 push。
- 依赖升级勿顺手放宽 lint：显式 select 钉住窄集（Widen deliberately）。

## Agent Rules
- 调用工具前先读工具描述确认参数名，不凭记忆猜。
- 传路径时显式传 output_dir，避免被陈旧 session 劫持到错误目录。
- 聚合/压缩知识后必须跑 lint 验证并关注健康分。
- 子代理「全绿」不可信：lastfailed 缓存空≠全过，关键结论自己实跑验证。

---

> **最后更新**：2026-08-24 · **来源场景**：6 个 · **记忆总数**：2 条
