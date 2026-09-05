---
type: decision
title: query_wiki P0 改进四项定案（Rev.2 评审定稿）：est_tokens / by_file v1 仅 notes / 新鲜度判据改 git
  提交时间 / description 契约收尾
tags:
- decision
metadata:
  date: 2026-09-05
  related_modules:
  - query_wiki
  severity: medium
  source_ref: conversations/conv-对-docs-claude-mem借鉴详细设计方案.md-做拷问式评审（grill）：先派子代理核对方案引用的全部代码事.md
  scene: 检索透明化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:33:37+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:35Z'
---

## Decision

claude-mem 借鉴方案评审后 15 项决策全部定案，`docs/claude-mem借鉴详细设计方案.md` 就地修订为 Rev.2（状态「评审定稿」，预计 3 人日）。P0 范围为：P0-1 est_tokens + P0-2 by_file + P1-4（改判据版）+ P0-3 description 改写。

## 关键定案（均经用户采纳）

- **实施顺序**：P0-1 → P0-2+P1-4 → P0-3 收尾。理由：description 是调用时强制可见的契约，不能引用尚不存在的参数。
- **est_tokens 真实价值**：消除最坏场景（单次调用 5 万 token），而非方案宣称的 -35%~-90% 稳定节省（把最坏场景当均值算，虚高）；字段名保留 est_tokens，靠 description 讲清「该篇全文的展开成本」。
- **by_file v1 只覆盖 notes**：生成页是机器对代码的描述，read_code_components 与 BM25 已覆盖，混入会稀释特异性排序信噪比；`wiki_pages_matched` 计数字段是伪需求，砍掉。by_file+query 组合时 query 只做**硬过滤**，排序仍按 (specificity, date)——specificity 是 by_file 立身之本，加权融合系数是拍脑袋参数。
- **P0-2 硬前提**：registry.py:1162 的 `required:["query"]` 是 MCP 层 schema 校验、先于 handler 执行，放宽 by_file 必填**必须改 registry 的 required**。handler 已有 schema 未声明参数先例（repo_path、origin_filter），但不应效仿。
- **兼容性约束**：`test_query_transparency.py:86` 精确断言 check 模式条目字段集 = {file, title, relevance_score}，est_tokens 加入 check 输出会打破此测试，需同步改。
- **命名惯例**：既有提示字段为 *_hint 家族，全仓无 advice 先例，顶层 advice 统一改 hint。
- **P1-4 mtime 新鲜度原样不值得**：mtime 在 clone 场景全量假阳性、1 天缓冲治不了，判据改为 git 最后提交时间（见 ADR-0003）或砍掉。

## Rationale

description 契约先行、最坏场景优先、机器确定性信号（git 提交时间）替代易假阳性信号（mtime）。
