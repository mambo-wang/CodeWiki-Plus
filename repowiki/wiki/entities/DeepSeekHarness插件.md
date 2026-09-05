---
title: "DeepSeek Harness 插件"
type: Entity
description: "WeKnora 官方 DeepSeek Harness 插件 @wxg-prc-cpg/dsh-weknora，提供四个只读编码 Agent 工具"
generated: { by: codewiki/5.6.0, at: 2026-09-05T12:00:27Z }
stale_after: 2026-12-04
aliases: [dsh-weknora, @wxg-prc-cpg/dsh-weknora, DeepSeek Harness 插件]
status: stable
metadata:
  category: "集成"
  source_refs: ["README_CN_2.0"]
  source_refs: ["README_CN_2.0"]
  chunk_refs: ["README_CN_2.0:197", "README_CN_2.0:197", "README_CN_2.0:199-202", "README_CN_2.0:197"]
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
sources:
  - id: README_CN_2.0
    resource: raw/sources/README_CN_2.0.md
    title: "WeKnora (维娜拉) 项目 README 中文版 v0.8.0：企业级 LLM 知识管理框架介绍"
    last_modified: 2026-09-05
---
# DeepSeek Harness 插件

## 概述

`@wxg-prc-cpg/dsh-weknora` 是 WeKnora 官方的 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`）插件 [^src:README_CN_2.0:197]。harness 自身不带任何检索、向量或知识库能力，这个插件把你的文档接进编码 Agent：`dsh plugin --profile web add @wxg-prc-cpg/dsh-weknora`，指向一个部署，Agent 的工具集里就会出现四个只读工具 [^src:README_CN_2.0:197]。

## 公开 API

插件向 Agent 暴露四个只读工具 [^src:README_CN_2.0:199-202]：

- **`weknora_search`** — 混合检索，返回原文片段，每条都带可复用的 `knowledge_id`
- **`weknora_read_document`** — 把单个文档的分块按序拼回正文，支持翻页
- **`weknora_ask`** — WeKnora 自己带引用的成稿答案，走 RAG 或 ReAct 流水线
- **`weknora_list_knowledge_bases`** — 知识库名称与 id，便于 Agent 自己缩小检索范围

## 依赖关系

依赖 [WeKnora](WeKnora.md) 部署实例（指向一个部署）；harness 提供编码 Agent 工具集接入能力。

## 使用模式

安装命令：`dsh plugin --profile web add @wxg-prc-cpg/dsh-weknora` [^src:README_CN_2.0:197]。安装后编码 Agent 可通过四个只读工具检索知识库与获取带引用答案。

## 相关页面

[WeKnora](WeKnora.md) · [README_CN_2.0](../sources/README_CN_2.0.md)