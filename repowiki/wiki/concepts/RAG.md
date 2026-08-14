---
title: RAG
type: Concept
description: 检索增强生成：WeKnora 基于知识库的快速问答能力
generated: {by: codewiki/5.2.0, at: !!timestamp '2026-08-03 04:55:39+00:00'}
stale_after: 2026-11-01
aliases: [RAG 快速问答, 检索增强生成, Retrieval-Augmented Generation]
sources:
- {id: README_CN, resource: raw/sources/README_CN.md, title: WeKnora（腾讯开源企业级知识库平台）中文
    README，用于测试两阶段知识提取流程, last_modified: 2026-08-03}
metadata:
  source_refs: [README_CN]
  chunk_refs: ['README_CN:61', 'README_CN:117', 'README_CN:130', 'README_CN:135',
    'README_CN:121', 'README_CN:123']
---
# RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是 [WeKnora](../entities/WeKnora.md) 三大核心能力之一，定位为“快速问答”，适合日常知识查询 [^src:README_CN:61]。其形态是基于知识库的问答：根据用户问题在知识库中检索相关内容，再由大模型生成回答 [^src:README_CN:117]。

## 在 WeKnora 中的实现

- 知识库类型支持 FAQ / 文档 / Wiki，支持文件夹导入、URL 导入、多标签管理与在线录入 [^src:README_CN:130]
- 检索层支持 BM25 稀疏召回、Dense 稠密召回、GraphRAG 图谱增强等 [[混合检索策略]] [^src:README_CN:135]
- 对话侧支持在线 Prompt 编辑、检索阈值调节、多轮上下文感知与按 Agent 的引用输出开关 [^src:README_CN:121]
- 回答附带引用浮层与引用抽屉，区分网络与知识库来源，并展示 RAG 流水线分阶段进度 [^src:README_CN:123]

## 相关页面

[WeKnora](../entities/WeKnora.md) · [[混合检索策略]] · [[ReActAgent]] · [[文档知识图谱]]
