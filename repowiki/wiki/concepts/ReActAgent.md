---
title: "ReActAgent"
type: Concept
description: "WeKnora 的 ReAct 多步推理能力：自主编排知识检索、MCP 工具与网络搜索"
generated: { by: codewiki/5.2.0, at: 2026-08-03T04:55:40Z }
stale_after: 2026-11-01
aliases: [ReAct Agent, ReAct 智能推理, ReACT]
source_refs: ["README_CN"]
chunk_refs: ["README_CN:61", "README_CN:116", "README_CN:119", "README_CN:149", "README_CN:161"]
sources:
  - id: README_CN
    resource: raw/sources/README_CN.md
    title: "WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程"
    last_modified: 2026-08-03
---
# ReActAgent

ReAct Agent 智能推理是 [WeKnora](../entities/WeKnora.md) 三大核心能力之一：采用 ReACT 渐进式多步推理，自主编排知识检索、MCP 工具与网络搜索完成复杂多步任务 [^src:README_CN:61] [^src:README_CN:116]。

## 工具调用

Agent 可调用的工具包括内置工具、MCP 工具（含 OAuth2 远程服务与会话内 OAuth 授权）与网络搜索；支持 `@Skill / @MCP` 提及以按轮次范围化 Agent 运行时 [^src:README_CN:119]。网络搜索后端支持 DuckDuckGo / Bing / Google / Tavily / Baidu / Ollama / SearXNG / Keenable / 智谱 AI [^src:README_CN:149]。

## 可观测性

ReAct 循环、Token 消耗与工具调用由 [Langfuse](../entities/Langfuse.md) 作为唯一追踪后端进行追踪 [^src:README_CN:161]。

## 相关页面

[WeKnora](../entities/WeKnora.md) · [RAG](RAG.md) · [Langfuse](../entities/Langfuse.md)
