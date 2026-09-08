---
type: Scenario
title: Wiki页面生成约定与数据结构
description: OKF status 分层与 actor、module_tree 遍历、模板包内单源收敛、schema.yaml 聚合阈值、聚合候选 disposition
  去向
tags:
- CodeWiki-CN
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:55:14+00:00
stale_after: 2026-12-07
aliases:
- Wiki页面生成约定与数据结构
status: stable
metadata:
  generated_from: f08feab
  resource: repo://CodeWiki-CN
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
  source_notes:
  - notes/2026-09-05-schemayaml-模板双源收敛为包内单源删根副本守卫测试只验包内模板清理-init-wikischema-gener.md
  - notes/2026-09-07-consolidate-notes-候选-disposition-三值机制未入选笔记不再无声滞留excluded-必填.md
  summary: 补入配置模板包内单源收敛与聚合候选 disposition 三值去向的可审计性机制
  heat: 4
---
## 工作场景
wiki 页面生成的 OKF/frontmatter 约定、数据结构消费与知识资产治理（模板分发、聚合可审计性）。适用于撰写/修补 wiki 页面、开发实体概念提取、排查 frontmatter 与模块树、配置聚合与模板分发、执行 consolidate_notes。

## 适用条件
开发 write_doc_file / extract-knowledge、写 OKF 测试、遍历 module_tree.json、调整聚合阈值/模板分发、判定聚合候选去向。

## 核心 SOP
1. status 语义分层：`write_doc_file` 代码生成页默认 stable；ingest_note/distill 经验笔记保持 draft（confirm 闸门）。
2. OKF actor 写 `codewiki/<version>`（`config.py actor_id()`），排查先看实际返回值。
3. 遍历 module_tree.json 先判断 children 元素类型：字符串引用需二次查顶层定义节点。
4. 实体/概念提取「识别与举证分离」四步：骨架提取 → query_wiki 语义去重 → 证据校验 → 编译式撰写。
5. 生成路径与修补路径都要写 aliases，两套路径默认键集合保持一致。
6. `lint --fix=true` 自愈顺序：预扫 stale_refs → rebuild_index → 再跑全部检查。
7. doctrine 备份机制已移除（.backup 冗余且污染检索索引）。
8. 聚合/doctrine 阈值等运行参数通过 `repowiki/schema.yaml conventions.aggregation` 覆盖，不改 py 源码默认值。
9. ingest_note 自动写索引；close_session 兜底终态确保索引一致。
10. **配置/脚手架模板收敛为包内单源**：删根副本与 fallback（`init_wiki._SCHEMA_TEMPLATE_ROOT`、`schema_generator._CONFIG_PATH_ROOT`，包内模板存在时永不生效），守卫测试只验包内权威副本。典型事故：开关只加进根 `schema.yaml`，而实际分发的是包内模板 → 新工作区静默拿不到开关。
11. **聚合候选必须有去向**：每条 pending 记 `metadata.disposition{verdict, reason?, at}`——absorbed 走 source_notes ⇄ consolidated_into，deferred 保留在 pending 并回带 disposition，excluded 必填 reason 并永久退出 pending；写回复用既有 `_update_frontmatter_meta`（locked RMW），不新建写回路径。

## 判断逻辑
- 去重三条件：同一真实事物 / 名称变体 / 类型兼容；核心原则 related ≠ same。
- health_score 是扣分制（error -10 / warning -3 / info -1）。
- 双份分发本身就是 bug 源：功能加了但分发模板没跟上 = 静默降级。
- 借鉴外部建议先过代码核对，并纠正方向映射（生成侧「候选无声消失」 vs 聚合侧「候选无声滞留」，是同一可审计性缺口的相反方向）。

## 禁忌与反模式
- 不全局改 `inject_okf_frontmatter` 的 status 默认值；不用 `agent:codewiki/` 旧格式 actor。
- 不用嵌套 dict 假设遍历 module_tree。
- 不给 doctrine 做文件级 .backup；不在 py 源码硬编码聚合阈值。
- 不让未入选的候选无声滞留（无 disposition 会让计数器长期告警、每轮重复权衡）。

## 关键事实依据
- prompt 模板示例曾写 `status: draft` 误导 LLM 照抄产生 draft 页面，模板已同步改 stable。
- disposition 三值机制：4 处约 40 行，excluded 无 reason 直接进 errors。
- 长期 deferred 告警阈值暂不设定（等 disposition 积累几轮再定）。