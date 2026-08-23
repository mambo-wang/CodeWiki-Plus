---
type: Doctrine
title: "Team Operating Doctrine"
status: draft
generated: { by: codewiki/5.3.0, at: 2026-08-18T01:59:02Z }
metadata:
  source_scenarios: ["wiki/scenarios/IDE-Hook采集链路方法.md", "wiki/scenarios/MCP-Server薄壳架构与参数约定.md", "wiki/scenarios/Wiki页面生成约定与数据结构.md", "wiki/scenarios/任务记忆系统设计方法.md", "wiki/scenarios/对话蒸馏管线与raw暂存区.md"]
  notes_at_refresh: 0
description: "> **Operating Thesis**: 工具只做确定性簿记，推理与决策永远在调用方 agent 与用户手里；一切进入知识库的内容必须经过显式确认闸门。"
---

# Team Operating Doctrine

> **Operating Thesis**: 工具只做确定性簿记，推理与决策永远在调用方 agent 与用户手里；一切进入知识库的内容必须经过显式确认闸门。

## Core Principles
- 无状态工具 + LLM 外置：工具不持模型、不做推断；提取/聚合/压缩一律走 prepare→调用方推理→submit 协议，才能跨 IDE 可移植。
- 确认闸门对等：凡落盘的知识（笔记、任务记忆、场景块、Doctrine）都先 draft/pending，经 confirm 才生效；绝不静默确认。
- 显式优于缓存：路径/归属/优先级解析统一「显式参数 > 可推导 > session 缓存」；不推断、不依赖隐式副作用。
- 单点收敛：同构逻辑只留一份实现（蒸馏落盘一条共同路径覆盖三模式、路径解析单点）；加新逻辑先找已有收敛点。

## Reusable SOPs
- 知识聚合：确认笔记积累超阈值时，先 prepare 取待聚合清单与容量预警 → 按工作对象分组写场景块（UPDATE 优先）→ 退役被吸收笔记 → submit 簿记 → lint 验证。
- 多文件批处理：逐文件处理 → 落盘 → 立即压缩上下文 → 下一文件，不累积。
- 新增 MCP 工具：tools/ 实现 handler + registry 注册 schema（含枚举联动），交付前跑全量测试。

## Decision Logic
- 会话锚点选 IDE 侧可观测的稳定 ID（source_session_id），不选内存态——内存态有 TTL 且并发下会静默污染。
- 噪声暂存文件宁删不留：暂存区不是仓库，显式 keep 是唯一保留途径。
- 合并判定 related≠same，拿不准就不合并。

## Boundaries & Anti-patterns
- 不要自动蒸馏/自动聚合：触发永远显式；提醒类信号（hint/计数器）必须先询问用户再执行。
- 不要绕过 dispatch/schema 校验直连 handler；不要用全局单值文件做并发锚点。
- 不要假设数据结构形状（索引分片 transcript、字符串引用树均已有教训）；先读格式再动手。
- 剥离注入块的正则不要用行首锚点——捕获层可能给行加角色前缀。

## Agent Rules
- 调用工具前先读工具描述确认参数名，不凭记忆猜。
- 传路径时显式传 output_dir，避免被陈旧 session 劫持到错误目录。
- 聚合/压缩知识后必须跑 lint 验证并关注健康分。

---

> **最后更新**：2026-08-18 · **来源场景**：5 个 · **记忆总数**：2 条
