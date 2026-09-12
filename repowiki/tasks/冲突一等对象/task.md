---
type: task
task_id: 冲突一等对象
title: 冲突一等对象
status: active
created_at: 2026-09-12T00:26:14.917582+00:00
---

把「两条 Wiki 笔记矛盾」做成一等对象（ADR-0007，来源：HL-Mem 调研 docs/HL-Mem-调研与借鉴分析.md A1）。

**范围（刻意收窄）**：顶级 conflicts/ 页面类型 + flag_conflict（手动声明）+ adjudicate_conflict（动作集 keep_a/keep_b/coexist/reject，内部复用 reject_note 原语 note_lifecycle.py:93-123）；账本 = git，不建独立 ledger。

**明确不做**：自动冲突发现（HL-Mem 依赖 slot 注册表底座 domain/claims/conflicts.py:119-160，本仓自由 Markdown 无此物 + Mode C 蒸馏「弱冲突多为误报」前科）、CAS/fingerprint 并发控制（单写者 + git）、generation 世代。

**接入面**：query_wiki 命中 claimant 附加「存在未裁决冲突」标注；lint_wiki 对 open 冲突超期发 warning（新 check 须同步 registry.py 枚举）。

**排期**：与 Phase5 批次二（T5/T6，动同一片 note_lifecycle/note_query 区域）错开，等用户指令开工。合入前按惯例 spawn 独立评审代理。
