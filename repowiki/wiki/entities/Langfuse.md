---
title: "Langfuse"
type: Entity
description: "WeKnora 集成的全链路可观测性追踪后端，追踪 ReAct 循环、Token 消耗与任务流水线"
generated: { by: codewiki/5.2.0, at: 2026-08-03T04:55:04Z }
stale_after: 2026-11-01
aliases: [Langfuse 追踪, 链路追踪]
source_refs: ["README_CN"]
chunk_refs: ["README_CN:61", "README_CN:63", "README_CN:161", "README_CN:69", "README_CN:70", "README_CN:213", "README_CN:225"]
sources:
  - id: README_CN
    resource: raw/sources/README_CN.md
    title: "WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程"
    last_modified: 2026-08-03
---
# Langfuse

在 [WeKnora](WeKnora.md) 中，Langfuse 是集成的全链路可观测性追踪后端 [^src:README_CN:61]。WeKnora 无缝集成 Langfuse，为 Agent 运行、Token 使用及任务流水线提供全面的可观测性追踪 [^src:README_CN:63]。

## 在 WeKnora 中的角色

- 作为唯一追踪后端，追踪 ReAct 循环、Token 消耗、工具调用和任务流水线 [^src:README_CN:161]
- v0.6.2 起移除 Jaeger，仅保留 Langfuse 追踪 [^src:README_CN:69]
- v0.6.1 引入内置的 Langfuse 风格文档解析追踪时间线，逐阶段展示解析进度 [^src:README_CN:70]

## 部署

通过 Docker Compose 的 `langfuse` profile 启动：`docker compose --profile langfuse up -d` [^src:README_CN:213]。启动后服务地址为 http://localhost:3000 [^src:README_CN:225]。

## 相关页面

[WeKnora](WeKnora.md) · [[ReActAgent]]
