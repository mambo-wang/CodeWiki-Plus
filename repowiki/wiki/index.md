---
okf_version: "0.2"
---

<!-- 自动生成于 2026-08-08T23:19:36+08:00 | Health Score: 0/100 | 本文件由系统自动维护 -->

# 项目文档索引

## 模块文档

* [AnalysisPipeline](modules/AnalysisPipeline.md) - title: AnalysisPipeline
* [AnalyzerModels](modules/AnalyzerModels.md) - title: AnalyzerModels
* [AnalyzerUtils](modules/AnalyzerUtils.md) - title: AnalyzerUtils
* [CLI](modules/CLI.md) - title: CLI
* [CLI_Adapter](modules/CLI_Adapter.md) - title: CLI_Adapter
* [CLI_Commands](modules/CLI_Commands.md) - title: CLI_Commands
* [CLI_Config](modules/CLI_Config.md) - title: CLI_Config
* [CLI_Utils](modules/CLI_Utils.md) - title: CLI_Utils
* [DependencyAnalyzer](modules/DependencyAnalyzer.md) - title: DependencyAnalyzer
* [DocVisualizer](modules/DocVisualizer.md) - title: DocVisualizer
* [Frontend](modules/Frontend.md) - title: Frontend
* [GraphAndSort](modules/GraphAndSort.md) - title: GraphAndSort
* [LLM_Backend](modules/LLM_Backend.md) - title: LLM_Backend
* [LanguageAnalyzers](modules/LanguageAnalyzers.md) - title: LanguageAnalyzers
* [MCP_Cache](modules/MCP_Cache.md) - title: MCP_Cache
* [MCP_Core](modules/MCP_Core.md) - title: MCP_Core
* [MCP_Prompts](modules/MCP_Prompts.md) - title: MCP_Prompts
* [MCP_Server](modules/MCP_Server.md) - title: MCP_Server
* [MCP_Tools_Analysis](modules/MCP_Tools_Analysis.md) - title: MCP_Tools_Analysis
* [MCP_Tools_Dependency](modules/MCP_Tools_Dependency.md) - title: MCP_Tools_Dependency
* [MCP_Tools_DocWriter](modules/MCP_Tools_DocWriter.md) - title: MCP_Tools_DocWriter
* [MCP_Tools_Knowledge](modules/MCP_Tools_Knowledge.md) - title: MCP_Tools_Knowledge
* [MCP_Tools_Quality](modules/MCP_Tools_Quality.md) - title: MCP_Tools_Quality
* [RouteExtractors](modules/RouteExtractors.md) - title: RouteExtractors
* [SharedConfig](modules/SharedConfig.md) - title: SharedConfig
* [WebApp](modules/WebApp.md) - title: WebApp

## 实体

* [ClawHubSkill](entities/ClawHubSkill.md) - WeKnora 发布在 ClawHub 平台上的技能：文档导入、混合检索与知识管理
* [Langfuse](entities/Langfuse.md) - WeKnora 集成的全链路可观测性追踪后端，追踪 ReAct 循环、Token 消耗与任务流水线
* [WeKnora](entities/WeKnora.md) - 腾讯开源的企业级 LLM 知识管理框架：RAG 问答 + ReAct 推理 + 自动 Wiki 一体化
* [微信对话开放平台](entities/微信对话开放平台.md) - 微信生态智能问答平台，以 WeKnora 为核心技术框架，支持零代码部署与公众号/小程序集成

## 概念

* [RAG](concepts/RAG.md) - 检索增强生成：WeKnora 基于知识库的快速问答能力
* [ReActAgent](concepts/ReActAgent.md) - WeKnora 的 ReAct 多步推理能力：自主编排知识检索、MCP 工具与网络搜索
* [Wiki模式](concepts/Wiki模式.md) - WeKnora 的 Agent 驱动自动 Wiki 能力：从原始文档自治生成相互链接的 Markdown 知识页面
* [文档知识图谱](concepts/文档知识图谱.md) - WeKnora 将文档转化为段落关联知识图谱，为索引与检索提供结构化支撑
* [混合检索策略](concepts/混合检索策略.md) - WeKnora 检索策略组合：BM25 / Dense / GraphRAG / 父子分块 / 多维度索引
* [空间Rbac](concepts/空间RBAC.md) - WeKnora 多空间权限控制：四级角色矩阵 + 资源归属 + 空间审计日志

## 外部文档

* [README_CN](sources/README_CN.md) - WeKnora 中文 README（v0.7.0）源文档摘要：三大核心能力、部署方式、功能矩阵与集成生态

## 知识笔记

* [Entity/Concept 提取采用 WeKnora 式两阶段流程（P0：纯 prompt 协议）](../notes/2026-08-03-entityconcept-提取采用-weknora-式两阶段流程p0纯-prompt-协议.md) - decision (decision, 2026-08-03)
* [MCP 工具 schema 不声明 session_id，handler 隐式读取](../notes/2026-08-03-mcp-工具-schema-不声明-session-idhandler-隐式读取.md) - lesson (lesson, 2026-08-03)
* [2026-08-08-codebuddy-ide-transcript-path-指向的-indexjson-只存元数据真实内容在-messa](../notes/2026-08-08-codebuddy-ide-transcript-path-指向的-indexjson-只存元数据真实内容在-messa.md) - note
