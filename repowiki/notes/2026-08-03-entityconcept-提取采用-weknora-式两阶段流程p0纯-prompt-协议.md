---
type: decision
title: Entity/Concept 提取采用 WeKnora 式两阶段流程（P0：纯 prompt 协议）
tags:
- codewiki
- decision
- weknora
aliases:
- extraction_dedup
- 两阶段提取
- WeKnora借鉴
- 编译器纪律
- granularity透传
- related≠same
status: deprecated
generated:
  by: codewiki/5.2.0
  at: 2026-08-03 04:46:14+00:00
stale_after: '2026-11-01'
verified:
- by: human:mambo-wang
  at: '2026-08-03T04:46:38Z'
metadata:
  date: 2026-08-03
  related_modules:
  - mcp
  - prompt_server
  related_components: []
  source_ref: WeKnora prompts_wiki.go (Tencent/WeKnora)
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
reject_reason: consolidated into Wiki页面生成约定与数据结构
author: mambo-wang
---

## 背景

CodeWiki-CN 的 entity/concept 提取原为单轮 LLM 一步到位（识别+撰写一体），无防幻觉、防误并机制，准确性全靠事后 lint。调研 Tencent/WeKnora（Go 实现）后确认其多阶段流水线的核心思想是"识别与举证分离"。

## 决策内容

P0 期采用纯 prompt 协议落地（不加 MCP 端点、不改数据结构）：

1. `prompts.py::_prompt_extract_knowledge` 重写为四步流程：骨架提取（Pass 0 只输出 JSON 骨架，禁止写正文）→ query_wiki 语义去重（create/merge/drop 三分类）→ 证据校验（source_ref 行范围必须实质性讨论该项，无引用不成立）→ 编译式撰写（merge 分支 edit_doc_file 追加不覆盖）。
2. `prompt_server.py` 新增 `extraction_dedup` 模板：合并三条件（同一真实事物/名称变体/类型兼容）+ 正反例库（混元≠通义、GPT-4≠GPT-3.5、居民身份证≠工作居住证等），核心原则 related ≠ same，拿不准就不合并。
3. `extraction_scan` 升级：granularity 三级回退（显式变量 → schema.yaml extraction_granularity → standard），经 handle_get_prompt 注入 `_schema_granularity`；新增 aliases 字段（严格同一事物）与 focused/standard/exhaustive 的 include/exclude 细则。
4. entity_page/concept_page/source_summary 注入编译器纪律：贴近原文措辞、禁修辞填充、范围纪律（拒绝与标题不符的材料）、不过度结构化、无引用不成立；source_summary 另加空内容规则（不得从文件名猜主题）。

## 原因

- 项目理念：Agent 行为偏好纯 prompt 协议（AGENTS.md + get_prompt），不新增 MCP 端点。
- 复用存量资产：`[^src:name:a-b]` 行范围脚注已自动入 frontmatter（doc_writer.py），extraction_scan 已有 granularity 雏形——只补流程不加设施。
- 明确不采纳 WeKnora 的：pg_trgm（无 PG 依赖）、Go Map-Reduce 服务端编排（Agent-in-loop 架构）、物理子目录 taxonomy、c001 chunk 别名（行范围引用更可读）。

## 验证

冒烟 94/94、OKF 回归 67/67 与基线一致；e2e 确认 schema 默认回退/显式覆盖/无 schema 默认 standard 三条路径。

## 影响范围与后续

涉及 codewiki/mcp/prompts.py、codewiki/mcp/tools/prompt_server.py。方案全文见 docs/Entity-Concept提取优化方案.md。P1（chunker + lint cite_refs 引用校验）、P2（chunk 级索引、page_merge、taxonomy 一致性）未实施，待真实文档冒烟后决策。
