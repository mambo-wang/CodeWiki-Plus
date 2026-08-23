---
title: Wiki页面生成约定与数据结构
type: Scenario
description: status 语义分层、OKF actor 约定、module_tree 字符串引用、实体概念提取识别与举证分离四步流程
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:51:49+00:00
stale_after: 2026-11-16
aliases:
- Wiki页面生成约定与数据结构
status: stable
metadata:
  source_notes:
  - notes/2026-08-15-write-doc-file-默认-statusstable与笔记蒸馏的-draft-语义分层.md
  - notes/2026-08-15-okf-7-actor-约定是-codewikiversion旧格式-agentcodewiki-已废弃.md
  - notes/2026-08-15-module-treejson-的-children-是字符串引用而非嵌套对象.md
  - notes/2026-08-03-entityconcept-提取采用-weknora-式两阶段流程p0纯-prompt-协议.md
  summary: status 语义分层（wiki 页 stable/经验笔记 draft）；OKF actor 约定；module_tree 字符串引用；实体概念提取识别与举证分离四步流程与
    related≠same 原则
  heat: 1
---
## 工作场景
wiki 页面生成中的 OKF 约定、frontmatter 语义与 wiki 数据结构消费的方法体系。适用于撰写/修补 wiki 页面、开发实体/概念知识提取、排查 frontmatter 与模块树问题。

## 适用条件
开发 write_doc_file / extract-knowledge 流程、写 OKF 相关测试、遍历 module_tree.json。

## 核心 SOP
1. status 语义分层区分默认值：write_doc_file 代码生成页默认 stable（确定性产出无需审核）；ingest_note/distill 经验笔记保持 draft（confirm 闸门）——两类知识信任度不同，frontmatter 三条注入路径（session/sessionless/patch）都要对齐。
2. OKF actor 写 codewiki/<version>（config.py actor_id()）；排查 actor 问题先看 actor_id() 实际返回值，不按旧文档臆断。
3. 遍历 module_tree.json 先判断 children 元素类型：children 是字符串引用（模块 id）需二次查顶层定义节点，不是嵌套 dict。
4. 实体/概念提取按「识别与举证分离」四步：骨架提取（Pass 0 只出 JSON 骨架、禁写正文）→ query_wiki 语义去重（create/merge/drop）→ 证据校验（source_ref 行范围必须实质性讨论该项，无引用不成立）→ 编译式撰写（merge 用 edit 追加不覆盖）。

## 判断逻辑
- 去重三条件：同一真实事物 / 名称变体 / 类型兼容；核心原则 related ≠ same，拿不准就不合并。
- 提取粒度三级回退：显式变量 → schema.yaml extraction_granularity → standard。

## 禁忌与反模式
- 不要全局改 inject_okf_frontmatter 的 status="draft" 默认值：capture（pending）与蒸馏链路（未审核语义）依赖它；改动只收敛在 doc_writer 的 wiki 生成路径。
- 不要用 agent:codewiki/ 旧格式 actor（已废弃，agent: 前缀不在规范内）。
- 不要用嵌套 dict 假设遍历 module_tree（'str' object has no attribute 'get'）。

## 关键事实依据
- prompt 模板示例写 status: draft 曾误导 LLM 照抄产生 draft 页面，模板已同步改 stable。
- P0 采用纯 prompt 协议落地（不加 MCP 端点、不改数据结构），是项目「Agent 行为偏好纯 prompt 协议」理念的体现。