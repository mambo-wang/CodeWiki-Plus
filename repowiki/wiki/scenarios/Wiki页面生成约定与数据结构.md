---
title: Wiki页面生成约定与数据结构
type: Scenario
description: status 语义分层、OKF actor 约定、frontmatter 约定、doctrine/聚合配置参数化、知识摄入链路
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:51:49+00:00
stale_after: 2026-11-16
aliases:
- Wiki页面生成约定与数据结构
status: stable
metadata:
  summary: doctrine 备份机制已移除；聚合阈值通过 schema.yaml conventions.aggregation 覆盖；ingest_note
    自动写索引
  heat: 3
  source_notes:
  - notes/2026-08-25-移除-doctrine-备份机制backup-冗余且备份文件会污染检索索引.md
  - notes/2026-08-25-聚合doctrine-阈值等运行参数通过-repowikischemayaml-conventionsaggregati.md
  - notes/2026-08-29-引用已有笔记前须检查其-statusdeprecated-笔记不应被采纳.md
  - notes/2026-08-29-生成文章后应-spawn-子代理对源文档做交叉事实核查.md
---
## 工作场景
wiki 页面生成中的 OKF 约定、frontmatter 语义与 wiki 数据结构消费的方法体系。适用于撰写/修补 wiki 页面、开发实体/概念知识提取、排查 frontmatter 与模块树问题、配置聚合/doctrine 运行参数。

## 适用条件
开发 write_doc_file / extract-knowledge 流程、写 OKF 相关测试、遍历 module_tree.json、调整聚合阈值与 doctrine 行为。

## 核心 SOP
1. status 语义分层区分默认值：write_doc_file 代码生成页默认 stable；ingest_note/distill 经验笔记保持 draft（confirm 闸门）。
2. OKF actor 写 codewiki/<version>（config.py actor_id()）；排查 actor 问题先看实际返回值。
3. 遍历 module_tree.json 先判断 children 元素类型：children 是字符串引用需二次查顶层定义节点。
4. 实体/概念提取按「识别与举证分离」四步：骨架提取 → query_wiki 语义去重 → 证据校验 → 编译式撰写。
5. 生成路径与修补路径都要写 aliases：两套路径默认键集合保持一致。
6. lint --fix=true 自愈过期索引要「预扫 stale_refs → 先 rebuild_index → 再跑全部检查」。
7. **doctrine 备份机制已移除**：.backup 冗余且备份文件会污染检索索引——不做 doctrine 文件级备份。
8. **聚合/doctrine 阈值等运行参数通过 repowiki/schema.yaml conventions.aggregation 覆盖**，不改 py 源码默认值——项目级配置优先于代码默认值。
9. **知识摄入到自动检索链路**：ingest_note 自动写索引；close_session 兜底终态确保索引一致性。

## 判断逻辑
- 去重三条件：同一真实事物 / 名称变体 / 类型兼容；核心原则 related ≠ same。
- health_score 是扣分制（error -10 / warning -3 / info -1）。
- 修复顺序类 bug 先看数据流时序。
- 运行参数外部化到 schema.yaml 避免改源码发版才能调参。

## 禁忌与反模式
- 不要全局改 inject_okf_frontmatter 的 status="draft" 默认值。
- 不要用 agent:codewiki/ 旧格式 actor。
- 不要用嵌套 dict 假设遍历 module_tree。
- 不要给 doctrine 做文件级 .backup（冗余且污染索引）。
- 不要在 py 源码中硬编码聚合阈值（应走 schema.yaml 覆盖）。

## 关键事实依据
- prompt 模板示例写 status: draft 曾误导 LLM 照抄产生 draft 页面，模板已同步改 stable。
- P0 采用纯 prompt 协议落地，是项目「Agent 行为偏好纯 prompt 协议」理念的体现。
- frontmatter deep module 重构四决策：路由收进 module、原地扩展、字节级兼容、先 reader 后 writer。
