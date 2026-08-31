---
type: Doctrine
title: Team Operating Doctrine
status: stable
generated:
  by: human:wangbao
  at: 2026-08-29 15:25:11+00:00
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
  notes_at_refresh: 69
verified:
- by: human:wangbao
  at: '2026-08-29T15:25:42Z'
stale_after: '2027-02-25'
---

# Team Operating Doctrine

> **Operating Thesis**: 工具做确定性簿记，推理决策永远在调用方与用户手里；入库必经显式确认闸门。

## Core Principles
- 无状态工具 + LLM 外置：提取/聚合/压缩走 prepare→调用方推理→submit；工具不持模型，跨 IDE 可移植。
- 确认闸门对等：凡落盘知识（笔记/记忆/场景块/Doctrine）都先 draft，confirm 生效；绝不静默确认。
- 显式优于缓存：路径/归属/优先级「显式参数 > 可推导 > session 缓存」；不依赖隐式副作用。
- 单点收敛：同构逻辑只留一份实现；新逻辑先找已有收敛点。

## Reusable SOPs
- 知识聚合：超阈值 prepare 取清单与预警 → 按对象分组写场景块（UPDATE 优先）→ 退役吸收笔记 → submit → lint。
- 多文件批处理：逐文件处理 → 落盘 → 立即压缩上下文 → 下一文件，不累积。
- 新增 MCP 工具：tools/ 实现 handler + registry 注册 schema，交付前跑全量测试。

## Decision Logic
- 会话锚点选可观测稳定 ID（source_session_id），不选内存态（TTL+并发静默污染）。
- 增量锚点复用既有元数据不新造；捷径/接管分支也须完成持久化契约。
- 合并判定 related≠same，拿不准就不合并。

## Boundaries & Anti-patterns
- 不自动蒸馏/聚合/生成重型产物：触发永远显式，hint 提醒先问用户。
- 不绕过 dispatch/schema 校验直连 handler；不用全局单值文件做并发锚点。
- 不假设数据结构形状，先读格式再动手；分析输出（近似行区间、陈旧缓存）不当精确，核对源码再用。
- 剥离注入块的正则勿用行首锚点——捕获层可能给行加角色前缀。
- 归档副本可能原样保留 token：推送前扫描脱敏。
- 依赖升级勿顺手放宽 lint：显式 select 钉住窄集。
- 噪声暂存宁删不留：显式 keep 才保留。
- 多宿主分发：同名配置 schema 各异（hook 命令、agent frontmatter），按家族发变体、缺失回退默认源。

## Agent Rules
- 调用工具前先读工具描述确认参数名，不凭记忆猜。
- 传路径显式传 output_dir，防陈旧 session 劫持目录。
- 重型分析先收窄范围防挂起；聚合后必跑 lint 验健康分。
- 子代理「全绿」不可信：lastfailed 空≠全过，关键结论自己实跑验证。

---

> 最后更新：2026-08-29 · 场景：8 · 笔记：34
