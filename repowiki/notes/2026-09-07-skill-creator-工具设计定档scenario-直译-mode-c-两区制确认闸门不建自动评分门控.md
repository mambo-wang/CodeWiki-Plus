---
type: decision
title: skill-creator 工具设计定档：scenario 直译 + Mode C + 两区制确认闸门，不建自动评分门控
tags:
- codewiki
- decision
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - skill_creator
  - note_consolidation
  - note_types
  severity: medium
  source_ref: conversations/conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md
  scene: 技能产物类型建设
  disposition:
    verdict: deferred
    at: '2026-09-08'
    reason: 技能产物建设组尚在推进中，等定稿落地后再立块
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.1
  at: 2026-09-07 01:41:38+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: codewiki/5.6.1
  at: '2026-09-07T01:47:01Z'
---

## Background

调研 wikiskill（arXiv:2608.27454 开源实现）后评估 CodeWiki 能否自动生成 SKILL。用户授权 Q1–Q4 全按推荐，先定档产出 `repowiki/wiki/comparisons/自动生成SKILL可行性-…md`，随后深化设计产出 `repowiki/wiki/queries/skill-creator设计方案.md`。

## 决策

- 可行性：能实现。CodeWiki 已走完"经验→结构化知识"半程（蒸馏已有），缺口集中在"技能产物类型"+"生成工具"两个新增件，非重构。
- 推荐形态 = 半闭环：MVP 先做单向编译器（confirmed notes/scenarios → SKILL.md draft → 确认闸门 → `.codebuddy/skills/`），稳定后再接回流迭代。
- 不建自动评分门控（无 held-out 基准，确认闸门已担质量职责）；生成走 Mode C（工具簿记、宿主 agent 写正文）；先仓库内闭环再家族分发。
- 落地顺序：skill 词汇 → skill_creator 工具 → SKILL.md lint → 闭环验证 → 回流。

## 关键设计点（Q6–Q11 定稿）

- 素材：scenario 直译为主（每份已确认 scenario → 一份 SKILL），单条高价值 pitfall 作补充（走 `_pending_confirmed_notes` 同类扫描）。
- 入口：prepare 列候选清单（默认 UPDATE 优先、最多新建 1 份/批），同时支持 topic/sources 显式指定；不做全自动（违反"触发永远显式"）。
- **两区制**（最关键）：草稿落 `repowiki/skills/<name>/SKILL.md`（不生效、进索引、进 lint），确认后 install 到 `.codebuddy/skills/`（生效）。直接落 `.codebuddy/skills/` 并标 status:draft 不可行——草稿期坏技能会在确认前就影响 agent 行为。
- 更新：重写 + frontmatter `metadata.revisions` 记录变更（不做 unified diff 引擎）；退役沿用 reject_note 语义（草稿区标记 deprecated + 生效区 uninstall）。
- 回流验证：note 反馈 + 薄 frontmatter（`metadata.effectiveness.last_evaluated_at`）；超期（建议 90 天）列为 UPDATE/retire 候选。
- lint：草稿区必须纳入 `lint_wiki`；生效区容量硬顶 12；必检 `description` 非空含触发条件、`name` 匹配 `^[a-z0-9-]+$`、无绝对路径/密钥、正文 ≤4000 字、`source_refs` 目标存在、`status ∈ {draft, stable, deprecated}`。

## Rationale

- 复用 `note_consolidation.py` 作为平行工具模板（Mode C prepare/submit + 容量 + 双向溯源 + 软删除 + 索引重建）；`note_types.py` 是 note_type 权威表可扩展。
- scenario 页章节骨架（工作场景/适用条件/核心 SOP/判断逻辑/禁忌）约等于 SKILL.md 正文骨架；`description` 天然对应"适用条件"。不建技能索引会重复生成（skill_creator 需 scenario_index 对等件）。
