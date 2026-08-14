---
title: WeKnora
type: Entity
description: 腾讯开源的企业级 LLM 知识管理框架：RAG 问答 + ReAct 推理 + 自动 Wiki 一体化
generated: {by: codewiki/5.2.0, at: !!timestamp '2026-08-03 04:55:04+00:00'}
stale_after: 2026-11-01
aliases: [维娜拉, WeKnora 框架, Tencent WeKnora]
sources:
- {id: README_CN, resource: raw/sources/README_CN.md, title: WeKnora（腾讯开源企业级知识库平台）中文
    README，用于测试两阶段知识提取流程, last_modified: 2026-08-03}
metadata:
  source_refs: [README_CN]
  chunk_refs: ['README_CN:59', 'README_CN:304-307', 'README_CN:61', 'README_CN:63',
    'README_CN:61', 'README_CN:61', 'README_CN:63', 'README_CN:63', 'README_CN:227-231',
    'README_CN:186-199', 'README_CN:157', 'README_CN:158', 'README_CN:165-167', 'README_CN:170-172',
    'README_CN:175-181', 'README_CN:233-235', 'README_CN:237-243', 'README_CN:147',
    'README_CN:135']
---
# WeKnora

WeKnora（维娜拉）是腾讯开源的、基于大语言模型（LLM）的知识管理框架，专为企业级文档理解、语义检索与智能推理场景打造 [^src:README_CN:59]。项目基于 MIT 协议发布，可自由使用、修改与分发，但需保留原始版权声明 [^src:README_CN:304-307]。

## 核心能力

框架围绕三大核心能力构建 [^src:README_CN:61]：

- **[[RAG]] 快速问答**：基于知识库的日常知识查询
- **[[ReActAgent|ReAct Agent 智能推理]]**：自主编排知识检索、MCP 工具与网络搜索，完成复杂多步任务
- **[[Wiki模式]]**：Agent 从原始文档中自治生成相互链接的 Markdown 知识库与可视化知识图谱

## 关键特性

- 多源数据接入：飞书 / Notion / 语雀 / RSS 自动同步，覆盖 PDF、Word、图片、Excel 等十余种文档格式 [^src:README_CN:63]
- 企业级多空间 [[空间RBAC]]：四级角色矩阵 + 资源归属 + 空间审计日志 [^src:README_CN:61]
- 网站嵌入 Widget、权限范围 API Key 与 Principal 模型、每空间多实例存储后端 [^src:README_CN:61]
- 全流程模块化：大模型、向量数据库、存储等组件均可灵活替换，支持本地与私有云部署，数据完全自主可控 [^src:README_CN:63]
- 可观测性：集成 [[Langfuse]] 追踪 Agent 运行、Token 消耗与任务流水线 [^src:README_CN:63]
- [[文档知识图谱]]：将文档转化为知识图谱，为索引和检索提供结构化支撑 [^src:README_CN:227-231]

## 部署方式

依赖 Docker 与 Docker Compose；`git clone` 后配置 `.env`，`docker compose up -d` 启动核心服务，访问 http://localhost 使用 [^src:README_CN:186-199]。支持本地 / Docker / Kubernetes (Helm) 部署与私有化离线部署 [^src:README_CN:157]。界面形态包括 Web UI、RESTful API、`weknora` 命令行、Chrome Extension、网站嵌入 Widget 与微信小程序 [^src:README_CN:158]。

## 生态与集成

配套 Chrome 插件（网页内容一键采集） [^src:README_CN:165-167]、微信小程序 [^src:README_CN:170-172]、[[ClawHubSkill|ClawHub Skill]] [^src:README_CN:175-181] 与配套 MCP 服务器 [^src:README_CN:233-235]。WeKnora 同时是 [[微信对话开放平台]] 的核心技术框架，可在公众号、小程序等微信场景中提供问答服务 [^src:README_CN:237-243]。IM 集成覆盖企业微信 / 飞书 / Lark / QQBot / Slack / Telegram / 钉钉 / Mattermost / 微信 [^src:README_CN:147]，检索层支持 BM25、Dense、GraphRAG 等 [[混合检索策略]] [^src:README_CN:135]。

## 相关页面

[[RAG]] · [[ReActAgent]] · [[Wiki模式]] · [[Langfuse]] · [[空间RBAC]] · [[文档知识图谱]] · [[混合检索策略]] · [[微信对话开放平台]] · [[ClawHubSkill]]
