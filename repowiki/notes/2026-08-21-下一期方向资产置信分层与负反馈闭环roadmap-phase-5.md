---
type: decision
title: 下一期方向：资产置信分层与负反馈闭环（Roadmap Phase 5）
tags:
- codewiki
- decision
aliases:
- 置信分层
- 负反馈
- 资产治理
- Phase 5
- confidence level
- negative feedback
metadata:
  date: 2026-08-21
  related_modules:
  - mcp
  - team-memory
  source_ref: tam-team-memory-practice
status: stable
generated:
  by: codewiki/5.3.0
  at: 2026-08-21 02:27:01+00:00
stale_after: '2027-08-26'
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:21Z'
---

## 背景

记忆分层提取（L0-L3）与 authority-aware 排序已落地，但资产仍缺两个治理维度：一是显式置信层级（检索对"验证过的经验"与"未验证的背景"一视同仁），二是负反馈通道（错误召回不改变后续路由，过期知识反复命中）。TAM 团队记忆实践的数据支撑：22,361 条任务关系中仅 231 条是可执行强关系（关联 ≠ 复用）；卡点分布中逻辑返工（1,350）远超缺少上下文（269）——错误经验比缺失经验伤害更大。

## 决策内容

下一期（Roadmap Phase 5 资产治理层，详见 docs/CodeWiki-CN-优化Roadmap.md）做两件事：

**5.1 资产置信分层**：frontmatter 新增 confidence_level: strong（confirmed + 验证证据，可直接执行）/ weak（confirmed 未验证，提示风险）/ shadow（未确认或降权，只参与召回不驱动执行）。升级路径"验证后升级"：shadow→weak 走 confirm_note，weak→strong 需附验证证据（test_ref/commit_ref/reviewed_by）。检索结果带 confidence 字段，默认装配只收 strong；wiki_stats 输出置信分布。

**5.2 负反馈闭环**：flag_misrecall 标记误召回并计数；达阈值自动降为 weak/shadow + 进待复核清单（lint 新增 disputed_assets）；降权写回 authority 排序。新鲜度字段 valid_from/valid_to/last_verified_at 替代纯天龄判 stale。误召回记录沉淀为负例库，蒸馏/聚合时相似模式给提示。

## 与已有实现的衔接

authority-aware 排序（2026-08-21 落地，5de090f）已完成 P0：status/note_type 权重（draft -0.25 / stable +0.05 / deprecated -0.35）。Phase 5 是在此基础上把隐式权重显式化为置信层级，并补上负反馈闭环。去重召回已豁免 authority 权重（相似度判断不受评审状态影响），5.1 实施时保持该豁免。

## 验收要点

- 置信可流转且检索按置信标注排序，shadow 不进默认任务上下文
- 负反馈可改变资产权重：同查询不再优先命中被降权资产
- 误召回历史可追溯（任务/原因/降权时间）
