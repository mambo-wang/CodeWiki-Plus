---
title: "README_CN_2.0"
type: Source
description: "WeKnora 中文 README（v0.8.0）源文档摘要：技能沙箱运行时、空间技能目录、跨会话长期记忆等新能力与功能矩阵"
generated: { by: codewiki/5.6.0, at: 2026-09-05T11:59:30Z }
stale_after: 2026-12-04
aliases: [WeKnora README v0.8.0, WeKnora 中文 README 2.0]
status: stable
metadata:
  source_refs: ["README_CN_2.0"]
  origin: "README_CN_2.0"
  version: "0.8.0"
  category: "竞品产品 README"
  source_refs: ["README_CN_2.0"]
  chunk_refs: ["README_CN_2.0:50-58", "README_CN_2.0:34", "README_CN_2.0:54", "README_CN_2.0:56", "README_CN_2.0:365", "README_CN_2.0:62", "README_CN_2.0:62", "README_CN_2.0:62", "README_CN_2.0:62", "README_CN_2.0:62", "README_CN_2.0:56", "README_CN_2.0:118-133", "README_CN_2.0:134-148", "README_CN_2.0:150-162", "README_CN_2.0:165-175", "README_CN_2.0:204-221", "README_CN_2.0:237-249", "README_CN_2.0:253-259", "README_CN_2.0:63", "README_CN_2.0:65", "README_CN_2.0:69", "README_CN_2.0:72", "README_CN_2.0:177-179", "README_CN_2.0:182-184", "README_CN_2.0:187-193", "README_CN_2.0:195-202", "README_CN_2.0:271-277", "README_CN_2.0:348-355"]
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
sources:
  - id: README_CN_2.0
    resource: raw/sources/README_CN_2.0.md
    title: "WeKnora (维娜拉) 项目 README 中文版 v0.8.0：企业级 LLM 知识管理框架介绍"
    last_modified: 2026-09-05
---
# README_CN_2.0

## 一句话总结

WeKnora（腾讯开源企业级 LLM 知识管理框架）v0.8.0 中文 README，介绍其三大核心能力、v0.8.0 起的技能沙箱运行时与空间技能目录、跨会话长期记忆，以及功能矩阵、部署方式与集成生态 [^src:README_CN_2.0:50-58]。

## 文档概要

该文档是 WeKnora 的中文 README，对应版本 v0.8.0 [^src:README_CN_2.0:34]。WeKnora（维娜拉）是一款开源的、基于大语言模型（LLM）的知识管理框架，专为企业级文档理解、语义检索与智能推理场景打造 [^src:README_CN_2.0:54]。框架围绕三大核心能力构建：RAG 快速问答适合日常知识查询，ReAct Agent 智能推理自主编排知识检索、MCP 工具、技能目录、会话级 Docker / E2B / Cube 沙箱与网络搜索完成复杂多步任务，全新的 Wiki 模式则让 Agent 从原始文档中自治生成相互链接的 Markdown 知识库与可视化知识图谱 [^src:README_CN_2.0:56]。项目基于 MIT 协议发布 [^src:README_CN_2.0:365]。

## 关键要点

### v0.8.0 核心新能力

- **技能沙箱运行时**：会话级常驻 Docker / E2B / Cube 后端，按空间配置网络策略；移除 Local 宿主机进程后端；Docker 需显式开启 [^src:README_CN_2.0:62]
- **空间技能目录**：从 ClawHub / SkillHub / git / zip 安装，按沙箱快照、实时进度、文件浏览/编辑、个人与空间环境变量 [^src:README_CN_2.0:62]
- **跨会话长期记忆**：profile / preference / fact / task / interest，自动抽取需确认，`search_memory` [^src:README_CN_2.0:62]
- 进程内 **anydoc** Office 解析；官方 **DeepSeek Harness 插件** `@wxg-prc-cpg/dsh-weknora` [^src:README_CN_2.0:62]
- GitLab 与腾讯 IMA 数据源；LiteLLM；Exa 与 Metaso 网络搜索；XMind 解析；OIDC JWKS 验签等 [^src:README_CN_2.0:62]

### 三大核心能力

框架围绕三大核心能力构建：RAG 快速问答、ReAct Agent 智能推理（自主编排知识检索、MCP 工具、技能目录、会话级 Docker / E2B / Cube 沙箱与网络搜索）、Wiki 模式（Agent 从原始文档中自治生成相互链接的 Markdown 知识库与可视化知识图谱，支持人工编辑、版本历史与一键回滚）[^src:README_CN_2.0:56]。

### 功能矩阵（功能概览）

- **智能对话**：智能推理、快速问答、Wiki 模式、技能目录与沙箱、长期记忆、工具调用、对话策略、推荐问题、临时附件、引用与 RAG 进度、会话管理 [^src:README_CN_2.0:118-133]
- **知识管理**：知识库类型 FAQ / 文档 / Wiki、文件夹树、分块编辑与版本历史、按批次解析配置、批量重新解析、数据源导入、十余种文档格式、自动打标签、检索策略、批量选择与打标签、端到端测试 [^src:README_CN_2.0:134-148]
- **集成与扩展**：模型厂商、向量数据库、Embedding、对象存储、IM 集成、网站嵌入、网络搜索、API 集成、MCP Server [^src:README_CN_2.0:150-162]
- **平台能力**：部署、界面、权限控制、安全、可观测性、任务管理、模型管理 [^src:README_CN_2.0:165-175]

### 部署与运行

环境要求 Docker 与 Docker Compose；`git clone` 后配置 `.env`，`docker compose up -d` 启动核心服务，访问 http://localhost 使用 [^src:README_CN_2.0:204-221]。可选 Docker Compose Profile 按需叠加启动：`full`（全部功能）、`neo4j`（知识图谱）、`minio`（对象存储）、`langfuse`（链路追踪）[^src:README_CN_2.0:237-249]。服务地址：Web UI http://localhost、后端 API http://localhost:8080、Langfuse http://localhost:3000 [^src:README_CN_2.0:253-259]。

### 版本演进（v0.8.0 → v0.2.0）

v0.7.2 上线官方产品文档站（VitePress，六大板块约 50 篇）与知识库文件夹树、分块编辑与版本历史、Wiki 页面版本历史 [^src:README_CN_2.0:63]；v0.7.0 引入细粒度权限范围 API Key 与 Principal 模型、运行时任务队列可观测面板与 Worker 池治理、多实例存储后端 [^src:README_CN_2.0:65]；v0.6.0 引入空间 RBAC（四级角色矩阵）[^src:README_CN_2.0:69]；v0.5.0 Wiki 模式正式版 [^src:README_CN_2.0:72]。

### 扩展形态

Chrome 插件支持在浏览器中直接将网页内容采集到知识库 [^src:README_CN_2.0:177-179]；微信小程序提供轻量移动端客户端 [^src:README_CN_2.0:182-184]；ClawHub Skill 经 REST API 提供文档导入、混合检索与知识管理 [^src:README_CN_2.0:187-193]；DeepSeek Harness 插件 `@wxg-prc-cpg/dsh-weknora` 提供四个只读工具 [^src:README_CN_2.0:195-202]。WeKnora 同时是微信对话开放平台的核心技术框架 [^src:README_CN_2.0:271-277]。

### 安全声明

从 v0.1.3 版本开始提供登录鉴权功能；生产环境建议部署在内网/私有网络环境，避免将服务直接暴露在公网上 [^src:README_CN_2.0:348-355]。

## 与本项目的关系

本仓库（CodeWiki-CN）同样面向「LLM Wiki 家族」知识管理场景，此 README 用于竞品调研与功能对照，重点观察技能沙箱运行时、跨会话长期记忆与分块编辑/版本历史等与团队知识飞轮相关的机制。

## Referenced By

[WeKnora](../entities/WeKnora.md) · [[技能目录与沙箱运行时]] · [[跨会话长期记忆]] · [[分块编辑与版本历史]] · [[DeepSeekHarness插件]] · [[WeKnoraMCP_Server]] · [RAG](../concepts/RAG.md) · [ReActAgent](../concepts/ReActAgent.md) · [Wiki模式](../concepts/Wiki模式.md) · [空间RBAC](../concepts/空间RBAC.md) · [混合检索策略](../concepts/混合检索策略.md)
