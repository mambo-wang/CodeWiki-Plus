---
type: task
task_id: Phase5-资产治理实施（置信分层+负反馈）
title: Phase5 资产治理实施（置信分层+负反馈）
status: active
created_at: 2026-08-21T03:37:29.096274+00:00
---

落地 Roadmap Phase 5：资产置信分层（strong/weak/shadow）+ 负反馈闭环（flag_misrecall + 自动降权 + 新鲜度字段）。

任务拆解见 docs/Phase5-资产治理-实现任务拆解.md（T1-T8，约 10-14 人日）。

实施顺序：
- 批次一（置信骨架）：T1 字段与流转 → T2 authority 排序集成 → T3 检索露出 / T4 统计分布
- 批次二（负反馈）：T5 flag_misrecall → T6 自动降权+复核清单 → T8 负例反哺
- 批次三（新鲜度，可并行）：T7 valid_from/valid_to/last_verified_at

关键约束：distill 去重的 apply_authority=False 豁免必须保持（去重是相似度判断不受置信影响）；T1 存量迁移先分支验证；lint 加检查项记得同步 registry.py checks 枚举。
