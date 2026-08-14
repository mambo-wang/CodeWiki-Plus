---
title: README_CN
type: Source
description: WeKnora 中文 README（v0.7.0）源文档摘要：三大核心能力、部署方式、功能矩阵与集成生态
generated: {by: codewiki/5.2.0, at: !!timestamp '2026-08-03 04:54:33+00:00'}
stale_after: 2026-11-01
aliases: [WeKnora README, WeKnora 中文 README]
sources:
- {id: README_CN, resource: raw/sources/README_CN.md, title: WeKnora（腾讯开源企业级知识库平台）中文
    README，用于测试两阶段知识提取流程, last_modified: 2026-08-03}
metadata:
  source_refs: [README_CN]
  chunk_refs: ['README_CN:39', 'README_CN:59', 'README_CN:304-307', 'README_CN:61',
    'README_CN:63', 'README_CN:63', 'README_CN:63', 'README_CN:63', 'README_CN:63',
    'README_CN:186-199', 'README_CN:203-215', 'README_CN:219-225', 'README_CN:74',
    'README_CN:71', 'README_CN:67', 'README_CN:165-167', 'README_CN:170-172', 'README_CN:175-181',
    'README_CN:233-235', 'README_CN:237-243', 'README_CN:289-296']
---
# README_CN

## 一句话总结

WeKnora（腾讯开源企业级 LLM 知识管理框架）的中文 README，介绍其 RAG 问答、ReAct Agent 推理与自动 [[Wiki模式]] 三大核心能力，以及部署方式、功能矩阵与集成生态。

## 文档概要

该文档是 WeKnora 的中文 README，对应版本 v0.7.0 [^src:README_CN:39]。WeKnora（维娜拉）是一款开源的、基于大语言模型的知识管理框架，专为企业级文档理解、语义检索与智能推理场景打造 [^src:README_CN:59]。项目基于 MIT 协议发布 [^src:README_CN:304-307]。

## 关键内容

### 三大核心能力

框架围绕三大核心能力构建：[[RAG]] 快速问答适合日常知识查询；[[ReActAgent|ReAct Agent 智能推理]] 自主编排知识检索、MCP 工具与网络搜索完成复杂多步任务；[[Wiki模式]] 让 Agent 从原始文档中自治生成相互链接的 Markdown 知识库与可视化知识图谱 [^src:README_CN:61]。

### 数据与集成

- 支持从飞书、Notion、语雀等外部平台自动同步知识，覆盖 PDF、Word、图片、Excel 等十余种文档格式 [^src:README_CN:63]
- 可通过企业微信、飞书、Slack、Telegram 等 IM 频道直接提供问答服务 [^src:README_CN:63]
- 模型层面兼容 OpenAI、DeepSeek、Qwen、智谱、混元、Gemini、MiniMax、NVIDIA、Ollama 等主流厂商 [^src:README_CN:63]
- 全流程模块化设计，大模型、向量数据库、存储等组件均可灵活替换，支持本地与私有云部署 [^src:README_CN:63]
- 无缝集成 [[Langfuse]]，为 Agent 运行、Token 使用及任务流水线提供全链路可观测性追踪 [^src:README_CN:63]

### 部署与运行

环境要求 Docker、Docker Compose 与 Git；`git clone` 后配置 `.env`，`docker compose up -d` 启动核心服务，访问 http://localhost 使用 [^src:README_CN:186-199]。可选 profile 可叠加启动：`full`（全部功能）、`neo4j`（知识图谱）、`minio`（对象存储）、`langfuse`（链路追踪） [^src:README_CN:203-215]。服务地址：Web UI http://localhost、后端 API http://localhost:8080、Langfuse http://localhost:3000 [^src:README_CN:219-225]。

### 版本演进（摘要）

v0.5.0 发布 [[Wiki模式]] 正式版 [^src:README_CN:74]；v0.6.0 引入 [[空间RBAC]] [^src:README_CN:71]；v0.7.0 引入权限范围 API Key 与 Principal 模型、运行时任务队列可观测面板与 Worker 池治理、每空间多实例存储后端 [^src:README_CN:67]。

### 扩展形态

Chrome 插件支持网页内容一键采集到知识库 [^src:README_CN:165-167]；微信小程序提供轻量移动端客户端 [^src:README_CN:170-172]；[[ClawHubSkill|ClawHub Skill]] 提供 REST API 方式的文档导入、[[混合检索策略|混合检索]] 与知识管理 [^src:README_CN:175-181]；另提供配套 MCP 服务器 [^src:README_CN:233-235]。WeKnora 同时是 [[微信对话开放平台]] 的核心技术框架 [^src:README_CN:237-243]。

### 安全声明

自 v0.1.3 起提供登录鉴权；生产环境建议部署在内网/私有网络，避免服务直接暴露公网 [^src:README_CN:289-296]。

## 相关页面

[[WeKnora]] · [[Langfuse]] · [[微信对话开放平台]] · [[ClawHubSkill]] · [[RAG]] · [[ReActAgent]] · [[Wiki模式]] · [[文档知识图谱]] · [[空间RBAC]] · [[混合检索策略]]
