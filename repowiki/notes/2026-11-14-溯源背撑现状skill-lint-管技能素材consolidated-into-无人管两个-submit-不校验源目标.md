---
type: architecture
title: "溯源背撑现状：skill_lint 管技能素材，consolidated_into 无人管，两个 submit 不校验源目标"
tags: ["1", "architecture"]
metadata:
  date: 2026-11-14
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["MCP_Tools_Quality", "MCP_Tools_Knowledge"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的.md"
  scene: "溯源背撑 lint 落地（provenance backstop）"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-14T01:36:07Z }
stale_after: 2027-11-14
origin: conversation

---

## 背景

为落地「溯源背撑 lint」（TAM Ontology 文章借鉴候选 #1，用户已要求落地、设计细节走 /grill-me 逐轮裁决）做写前事实核查：先派只读子代理摸 wiki_lint 工程事实，再对关键断言亲自 Read/Grep 复核。以下行号均为实际读取。

## 现有覆盖（重叠面）

- `skill_lint` 的 possibly_stale 段（`codewiki/mcp/tools/wiki_lint.py:1801-1827`）已做素材级溯源校验：`source_refs` 目标文件缺失、素材 `status` ∈ deprecated/superseded/rejected、正文 `[DELETED]` 软删 → warning。三个已知局限：**不区分吸收性退役**（会话实测 6 个 SKILL.md 的 20 条 source_refs 中 7 条属正常吸收退役，即现存误报源）、**不查降回 draft**、**每技能只报首条就 `break`**（:1827 注释 "one warning per skill is enough to trigger review"）。
- `scenario_orphan` 读 `metadata.source_notes` 但仅判非空（:1510-1579，判定在 :1552）。
- 全文件无任何检查读 `consolidated_into` / `compiled_into` / `promoted_to`（grep 0 命中）。
- 名字相近但语义不同：`stale_refs`/`broken_links` 只扫**正文**链接（:307-424）；`stale_sources` 只扫正文 `[^src:]` 脚注（:826-837）；`stale_evidence` 读 frontmatter `sources` 的 repo:// 哈希；`superseded_pages` 只报页面自身状态、不追引用（:876-899）；`layout_violations` 的 "missing provenance" 指 repo:/repos: 工作区归属标签（:2157-2161），另一语义。
- `okf_conformance` §11 已把 frontmatter 解析失败报 **error**（:1893-1894）——损坏资产并非完全无信号；新增溯源检查对解析失败的文件应跳过，不重复发同一信号。

## 写路径缺口（根因）

两条 submit 都**不校验源目标文件存在**：

- `consolidate_notes` submit：`codewiki/mcp/tools/note_consolidation.py:562-578` 只做 `_norm_rel` + 空串过滤，随后 `_append_meta_list` 写 `source_notes`；回链阶段对不存在的路径做 basename 兜底（:577-578），但源名本身不校验、不报错 → 截断名照样入库。
- `skill_creator` submit：`codewiki/mcp/tools/skill_creator.py:498-523` 只校验非空 list + 路径逃逸，无 `is_file` 存在校验。

因此「背撑」哲学（submit 已校验、lint 兜住绕过工具的手写手改，`wiki_lint.py:1663-1664`）在溯源这一环前提不成立：submit 没校验，lint 背撑只是补救。

## 对既有草稿的修正

`notes/2026-11-13-tam-ontology-文章借鉴处置1-候选待裁决3-缓做8-排除.md` 中「3 条断链至今无任何 lint 覆盖」需限定：**断链本身**确无检查覆盖，但承载它们的 frontmatter 解析失败已由 `okf_conformance` 报 error；「wiki_lint 无任何检查读 source_notes」也应补充 `skill_lint` 已覆盖技能侧 `source_refs`（只是不区分吸收性退役）。本条与该处置笔记分工：那条记「12 候选去向」，本条记「落地前的工程事实与重叠面」。

## 待裁决（不是已定案）

会话结束时 grill 第 1 轮 9 问仍待用户回答：收敛策略（抽共享纯函数、新检查管场景块+笔记双向、skill_lint possibly_stale 改调同一函数并去 break）vs 各自为政；四类失效形态（缺失/非吸收性 deprecated/降回 draft/`[DELETED]` 软删）；warning 级 hint-only 不自动修复；2 个损坏场景块 frontmatter 重建；两个 submit 加源目标存在校验；命名 `provenance_backstop`；消息走 i18n 双语料；计数文案全量同步。**以上均为助手推荐方案，未经用户确认，不得当作项目决策引用。**

## Rationale

落地溯源检查前必须先知道重叠面与根因位置：否则会重复造检查、技能被双重报告、或只修数据不堵写路径而反复再脏。
