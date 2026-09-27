---
type: decision
title: agentmemory 调研定案：重运行时全自动路线与 CodeWiki 哲学相反，组件不移植；唯一立项 CODEWIKI_TOOLS=core 工具面裁剪（P2）
tags:
- codewiki
- decision
- typescript
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 他山之石
  source_session: d66c8f4336854d4e993cc7be40a0ef77
  related_modules:
  - registry
  - retrieval
  - task_manager
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-c11099.md
  scene: 他山之石
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:45:47+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:14Z'
---

## 背景

「他山之石」任务调研 rohitg00/agentmemory（TypeScript，v0.9.x，~42K LOC）：给 AI 编码 agent 做持久记忆的项目，全部运行时由 iii-engine 三原语（worker/function/trigger）组合，SQLite 存储 + BM25/向量内存索引，9 类 hook 全量自动采集、自动巩固、自动驱逐。

## 总体判断

agentmemory 是「重运行时、全自动」路线的极致样本；CodeWiki 是「轻文件、显式确认」路线。哲学相反，直接移植任何组件都会破坏 CodeWiki 的架构前提。自动采集/自动巩固/自动驱逐这条全自动路线，CodeWiki 明确不走。

## 候选处置（Round 1）

| 候选 | 去向 | 理由 |
|---|---|---|
| 合成压缩（零 LLM） | absorbed | 与确认闸门冲突，仅作未来降本备选认知 |
| 记忆衰减/自动驱逐 | deferred | 与「候选必有去向」Doctrine 冲突，等 lint_wiki low_adoption 数据再评估 |
| slots 固定槽位 | excluded | MEMORY.md + AGENTS.md + 任务记忆三件套已覆盖同等语义 |
| PreCompact 重注入 | excluded | UserPromptSubmit 薄触发是超集；被动注入与 Agent 驱动模型前提相反 |

## Round 2 小优化裁决（2026-09-25，用户 grill 逐题确认）

| 候选 | 去向 |
|---|---|
| MCP 工具面裁剪开关 `CODEWIKI_TOOLS=core` | **立项（P2，归产品维护）**——60+ 工具 schema 全量注入 IDE 上下文是真缺口，registry 加 filter 成本低 |
| 会话多样性约束（每 session 最多 3 条） | deferred——单源霸屏未实测出现，等重复笔记数据 |
| RRF 多路召回融合 | excluded——单流 BM25 无第二路可融，为 RRF 而 RRF 是伪需求 |
| related_notes 语义召回 | excluded——任务上下文注入要确定性，语义召回违背「工具不持模型」 |
| 同义词扩展 / CJK 分词 / SHA-256 去重 | 本仓已有等价，无需行动 |

## 参考

agentmemory 的存储：SQLite（iii-engine StateModule → `data/state_store.db`）+ 50 个 KV scope（mem:memories / mem:obs:<sessionId> / mem:semantic / mem:procedural 等），BM25 与向量索引是进程内存结构；衰减/驱逐建立在 KV 原子更新之上，搬到 Markdown 文件体系没有落点。完整调研存档：`repowiki/wiki/queries/agentmemory-调研.md`。
