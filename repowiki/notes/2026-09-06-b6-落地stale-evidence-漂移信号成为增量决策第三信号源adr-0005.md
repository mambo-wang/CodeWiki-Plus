---
type: decision
title: B6 落地：stale_evidence 漂移信号成为增量决策第三信号源（ADR-0005）
tags:
- decision
metadata:
  date: 2026-09-06
  related_modules:
  - mcp_tools_analysis
  - evidence
  severity: high
  source_ref: conversations/conv-调研-openwiki、deepwiki-open、OpenDeepWiki、deepwiki-rs-四个-DeepWi.md
  scene: 增量更新
  consolidated_into:
  - wiki/scenarios/多仓工作区初始化与增量分析.md
status: deprecated
author: local
generated:
  by: codewiki/5.5.0
  at: 2026-09-06 08:23:44+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:12Z'
reject_reason: consolidated into 多仓工作区初始化与增量分析
---

## 背景

D1（证据哈希）落地后，stale_evidence 检查结果只进 lint 报告，不参与 analyze_repo 的增量决策。B6 把它接入，成为与 affected_modules（git diff 驱动）、stale_pages（D2 manifest 驱动）并列的第三信号源，覆盖 git diff 摸不到的共享池页（notes/entities/concepts 不在模块树里）。

## 决策

1. 信号形态：changes_info["stale_evidence_pages"] = {页面: {stale/missing/unresolvable 计数}}，明细留在 lint（lint_wiki(checks=['stale_evidence']) 按需取），hint 引导复核+re-stamp 而非重写（守"证据只驱动提醒"红线）。
2. 单点收敛：collect_evidence_drift()（codewiki/mcp/tools/evidence.py）作为 lint 与增量的共享采集点；wiki_lint._check_stale_evidence 改薄包装，行为不变。
3. no_changes 路径静默（ADR-0005，用户拍板）：analyze_repo 的 no_changes 短路不跑证据漂移扫描，与 stale_pages 在该路径 enrich 的行为不对称是显式接受的取舍；漂移出口是显式 lint。
4. stale_pages 与 stale_evidence_pages 两字段并存不去重：语义不同（文件级变更 vs 证据级漂移），同页双命中是诚实的双重报告，不改 D2 已落地契约。
5. 挂点：_enrich_stale_evidence 紧跟 _enrich_stale_pages 之后，只挂 handle_analyze_repo 变更路径；_build_no_change_response 里不调（实现时误挂过一次后撤掉，注释指向 ADR-0005）。

## 验证

tests/test_stale_evidence_signal.py 10 项 + 定向回归 119 过 + ruff 过（全量 pytest 亦通过）。提交 784e285。
