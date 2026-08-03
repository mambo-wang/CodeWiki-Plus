---
title: "Wiki模式"
type: Concept
description: "WeKnora 的 Agent 驱动自动 Wiki 能力：从原始文档自治生成相互链接的 Markdown 知识页面"
generated: { by: codewiki/5.2.0, at: 2026-08-03T04:55:40Z }
stale_after: 2026-11-01
aliases: [Wiki 模式, 自动 Wiki, Agent Wiki]
source_refs: ["README_CN"]
chunk_refs: ["README_CN:61", "README_CN:118", "README_CN:74", "README_CN:72", "README_CN:68"]
sources:
  - id: README_CN
    resource: raw/sources/README_CN.md
    title: "WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程"
    last_modified: 2026-08-03
---
# Wiki模式

Wiki 模式是 [WeKnora](../entities/WeKnora.md) 三大核心能力之一：Agent 驱动从原始文档中自动生成并维护结构化、相互链接的 Markdown Wiki 知识页面 [^src:README_CN:61] [^src:README_CN:118]。

## 版本演进

- v0.5.0 发布 Wiki 模式正式版：Agent 从原始文档自治生成结构化、相互链接的 Markdown Wiki 页面及知识图谱，并提供 Wiki 浏览器与可视化图谱 [^src:README_CN:74]
- v0.5.2 Wiki 入库支撑万级文档知识库（任务队列 + 死信队列） [^src:README_CN:72]
- v0.6.3 引入 Wiki 文件夹与层级导航 [^src:README_CN:68]

## 相关页面

[WeKnora](../entities/WeKnora.md) · [[文档知识图谱]] · [RAG](RAG.md)
