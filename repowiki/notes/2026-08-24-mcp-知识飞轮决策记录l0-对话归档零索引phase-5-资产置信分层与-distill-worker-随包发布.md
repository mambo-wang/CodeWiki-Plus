---
type: decision
title: mcp 知识飞轮决策记录：L0 对话归档零索引、Phase 5 资产置信分层与 distill-worker 随包发布
tags:
- decision
aliases:
- 置信分层
- 负反馈
- 资产治理
- Phase 5
- confidence level
- negative feedback
- L0 对话归档
- 对话归档零索引
- distill-worker 发布
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - mcp
  - team-memory
  - agents
  - 团队记忆融合-L2场景聚合与L3-Doctrine设计方案
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 02:05:55+00:00
stale_after: '2027-08-24'
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T02:07:50Z'
reject_reason: 聚合进场景：对话蒸馏管线与raw暂存区
author: mambo-wang
---

## 背景

本笔记合并了 `mcp` 模块下 3 篇主题互补的决策笔记：L0 对话归档零索引设计（2026-08-19）、Roadmap Phase 5 资产置信分层与负反馈闭环（2026-08-21）、distill-worker subagent 随包发布（2026-08-23）。三者共同构成 mcp 知识飞轮（蒸馏→归档→检索→治理）的决策记录，合并后本文为唯一权威来源。

## 1. L0 对话归档：链接优先、零索引设计

### 背景

验证发现存量笔记的 source_ref 全部指向蒸馏后被删除的 raw 文件（48/48 断裂），知识溯源链整体失效；同时担心归档拖慢检索。

### 决策内容

1. 蒸馏成功产出知识的对话不再删除，搬家到独立的 repowiki/conversations/ 归档区（raw/ 保持待蒸馏暂存队列语义，采集扫描不受归档量影响）。
2. 归档层不建 BM25 索引（零索引）：检索入口永远是知识层（笔记/场景/Doctrine），对话只是出处；发现路径是链接式——query_wiki 命中笔记时结果露出 metadata.source_ref，agent 按需 view_repo_file 读取原始对话。
3. 蒸馏完成后把所有指向该 raw 的笔记 source_ref 从 raw/ 改写为 conversations/（扫描 notes/ 全量改写，覆盖多轮冲突提交场景）。
4. drop_raw（submit 参数或 raw frontmatter）是隐私显式删除通道；keep_raw 语义收敛为无知识对话也保留。

### 理由

- 基准测试：倒排索引查询耗时与文件数基本解耦（1000 条对话 82ms），但全量重建成本线性增长——归档不进索引则两个成本都不存在。
- 对话是低信噪比文档，混入默认检索会挤掉高价值结果；链接式发现天然规避噪音。
- 溯源是 L0 留档的首要价值：让 source_ref 成为真能点开的链接。

### 边界

- 放弃按对话正文关键词反查能力（值得找回的对话必有笔记指向它）；未来真实需要出现再建索引。
- 已删除的历史 raw 无法找回，方案只向前生效。

## 2. Roadmap Phase 5：资产置信分层与负反馈闭环

### 背景

记忆分层提取（L0-L3）与 authority-aware 排序已落地，但资产仍缺两个治理维度：一是显式置信层级（检索对"验证过的经验"与"未验证的背景"一视同仁），二是负反馈通道（错误召回不改变后续路由，过期知识反复命中）。TAM 团队记忆实践的数据支撑：22,361 条任务关系中仅 231 条是可执行强关系（关联 ≠ 复用）；卡点分布中逻辑返工（1,350）远超缺少上下文（269）——错误经验比缺失经验伤害更大。

### 决策内容

下一期（Roadmap Phase 5 资产治理层，详见 docs/CodeWiki-CN-优化Roadmap.md）做两件事：

**5.1 资产置信分层**：frontmatter 新增 confidence_level: strong（confirmed + 验证证据，可直接执行）/ weak（confirmed 未验证，提示风险）/ shadow（未确认或降权，只参与召回不驱动执行）。升级路径"验证后升级"：shadow→weak 走 confirm_note，weak→strong 需附验证证据（test_ref/commit_ref/reviewed_by）。检索结果带 confidence 字段，默认装配只收 strong；wiki_stats 输出置信分布。

**5.2 负反馈闭环**：flag_misrecall 标记误召回并计数；达阈值自动降为 weak/shadow + 进待复核清单（lint 新增 disputed_assets）；降权写回 authority 排序。新鲜度字段 valid_from/valid_to/last_verified_at 替代纯天龄判 stale。误召回记录沉淀为负例库，蒸馏/聚合时相似模式给提示。

### 与已有实现的衔接

authority-aware 排序（2026-08-21 落地，5de090f）已完成 P0：status/note_type 权重（draft -0.25 / stable +0.05 / deprecated -0.35）。Phase 5 是在此基础上把隐式权重显式化为置信层级，并补上负反馈闭环。去重召回已豁免 authority 权重（相似度判断不受评审状态影响），5.1 实施时保持该豁免。

### 验收要点

- 置信可流转且检索按置信标注排序，shadow 不进默认任务上下文
- 负反馈可改变资产权重：同查询不再优先命中被降权资产
- 误召回历史可追溯（任务/原因/降权时间）

## 3. distill-worker subagent 随包发布

### 背景

会话启动补蒸馏已改为委托「蒸馏 worker」subagent（distill-worker.md）执行。此前该定义文件只手工放在项目 `.codebuddy/agents/` 下，用户要求把定义文件存入 CodeWiki 源码目录，并在启用 hook 时自动拷贝到目标项目，避免每个项目手工复制、版本漂移。

### 决策内容

`distill-worker.md` 的权威版本只存在 **`codewiki/agents/distill-worker.md`**（随 `codewiki` 包发布），任何项目启用 hook 时自动拷贝到目标项目的 `.codebuddy/agents/distill-worker.md`，与 `hooks/*.py` 的安装方式完全对称。具体落地：

1. 源码副本：`codewiki/agents/distill-worker.md`，与项目内 `.codebuddy/agents/distill-worker.md` 内容一致，包内为权威版本。
2. hook 启用时自动拷贝（`codewiki/mcp/prompts.py` 两处）：`_prompt_init_wiki`（init 流程）与 `_prompt_team_memory_hook`（步骤 2A）——创建 `.codebuddy/agents/` 目录、从包内 `agents/distill-worker.md` 强制拷贝、校验命令增加 `assert` 确认 md 存在且以 `---` 开头、回退逻辑（`CODEWIKI_HOME`）同步支持 agents 拷贝。
3. 关闭步骤 2B 说明：`distill-worker.md` 可保留也可删除，重新启用自动补回。
4. 打包声明：`pyproject.toml` 的 `package-data` 增加 `"agents/*.md"`——否则 pip 安装时非 `.py` 文件默认不打包，`.md` 不会随包发布。

### 理由

subagent 定义与 hook 脚本同属「启用即部署」的配套资源，与 `hooks/*.py` 走同一安装路径可降低维护成本；源码只存一份避免双副本漂移。

### 验证

- `prompts.py` 语法 OK；`tests/test_task_session_start.py` 4 个测试全部通过；无 lint 错误。
- 待验证点：`distill-worker.md` 的 frontmatter（`toolsMCP` 字段名、agentic 模式下 Task 工具是否能直接 spawn）依赖 IDE 对 subagent 定义的解析，需在下次新会话观察 hook 是否成功把蒸馏委托出去；若解析方式有差异只需调整该文件 frontmatter 字段名，不影响其他改动。

## 相关文档

- [对话蒸馏管线与 raw 暂存区](../wiki/scenarios/对话蒸馏管线与raw暂存区.md)
- [任务记忆系统设计方法](../wiki/scenarios/任务记忆系统设计方法.md)
- [MCP 工具质量](../wiki/modules/MCP_Tools_Quality.md)

## Sources

- `2026-08-19-l0-对话归档采用链接优先零索引设计.md`
- `2026-08-21-下一期方向资产置信分层与负反馈闭环roadmap-phase-5.md`
- `2026-08-23-distill-worker-subagent-定义随包发布hook-启用时自动拷贝到项目-codebuddyagent.md`

