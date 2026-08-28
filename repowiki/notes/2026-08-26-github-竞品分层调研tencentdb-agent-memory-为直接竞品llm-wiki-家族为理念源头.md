---
type: general
title: GitHub 竞品分层调研：TencentDB Agent Memory 为直接竞品，LLM Wiki 家族为理念源头
tags:
- codegraph
- codewiki
- general
- github
- tencentcloud
aliases:
- 竞品调研
- TAM 对照
- TencentDB Agent Memory
- LLM Wiki
metadata:
  date: 2026-08-26
  task_id: 产品维护
status: stable
generated:
  by: codewiki/5.4.4
  at: 2026-08-25 23:35:25+00:00
stale_after: '2026-12-24'
verified:
- by: human:Administrator
  at: '2026-08-26T04:31:03Z'
---

## 结论

GitHub 上与 CodeWiki「团队记忆+知识管理」最相近的仓库分三层：

1. **直接竞品**：TencentDB Agent Memory（TencentCloud/tencentdb-agent-memory，~19.9k stars，MIT）——团队级 Agent 记忆中枢，四记忆资产（Chat Memory / Skill / Wiki / CodeGraph），与 CodeWiki「对话采集→蒸馏→知识飞轮」几乎一一对应（CodeGraph↔repowiki、Wiki↔query_wiki 笔记、对话蒸馏↔capture/distill_conversation、任务上下文↔task memory）。最值得盯防/借鉴。
2. **理念同源**：Andrej Karpathy LLM Wiki（2026-04 开源）——「LLM 增量编译并维护持久 Markdown wiki」模式，衍生实现 nvk/llm-wiki、owenliang/llm-wiki 等；awesome-llm-wiki 汇总列表。可作 README/对外表述的类比。
3. **通用 Agent 记忆层**：mem0（事实记忆 SDK）、Letta/MemGPT（带记忆的 Agent 框架）、Zep（Graphiti 时序知识图谱）、Cognee（知识图谱+向量双模）——定位不同，设计可参考。

## 与竞品差异点

| 维度 | TencentDB Agent Memory | CodeWiki |
|---|---|---|
| 代码库原生 | CodeGraph 偏向调用关系图 | repowiki 架构文档 + OKF |
| 知识确认 | 偏自动沉淀 | 显式确认闸门（draft→confirm） |
| 任务记忆 | 团队级共享 | 任务级有界记忆 + 压缩归档（ADR-0001/0002） |
| 对话蒸馏 | 异步提取 | 三态 Mode A/B/C，无状态工具 + LLM 外置 |

## 后续行动

可深扒 TencentDB Agent Memory 仓库架构做逐点对比；对外表述用 LLM Wiki 家族作类比。
