---
type: architecture
title: 架构审查基线（2026-10 @ 99e4ec0）：cache.py/store.py/registry.py/task_manager.py/distill_conversation.py
  五个上帝模块与 14 对循环依赖
tags:
- architecture
- codewiki
- knowledgestore
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: fc9dd122-6339-46c5-9cc7-2a13741b059a
  related_modules:
  - mcp-tools
  - retrieval
  - store
  severity: medium
  source_ref: conversations/conv-system-reminder-The-user-selected-the-following-skills-in-th.md
  scene: 产品维护：架构审查与热点分析
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:02:24+00:00
stale_after: '2027-10-21'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:18Z'
---

## Background

2026-10 对 CodeWiki-Plus（@ 99e4ec0）跑了一次基于依赖图的架构审查（analyze_repo + list_dependencies），规模：2030 个 Python 组件 / 92 叶节点 / 7972 条依赖边。用户确认这是纯代码架构优化方向（功能行为不动），但尚未排期实施。以下为代码核对的事实基线，供后续重构排期参考。

## 层次结构

应用层（cli / hooks / mcp/server.py）→ 编排层（mcp/registry.py 53 工具 dispatch、mcp/tools/*、mcp/cache.py、mcp/workspace.py）→ 核心层（src/store.py [KnowledgeStore](../../codewiki/src/store.py)、src/config.py、src/frontmatter.py、src/retrieval.py）→ vendored 后端（src/be/dependency_analyzer、src/be/documentation_generator，被一等公民代码引用，属项目一部分）。

## 热点文件（按 fan-in）

- `mcp/cache.py`（1885 行，fan-in 316）：SQLite 分析缓存 + [LazyComponentStore](../../codewiki/mcp/cache.py) + 检索内核 re-export，**上帝模块**；`LazyComponentStore.items` 被 131 处调用（全仓最高）。
- `src/store.py`（1505 行，fan-in 277）：[KnowledgeStore](../../codewiki/src/store.py) 全部写入/查询，**上帝模块**。
- `mcp/tools/task_manager.py`（1469 行，fan-in 69）、`mcp/tools/distill_conversation.py`（2106 行，fan-in 58）、`mcp/tools/wiki_lint.py`（2748 行）：**上帝模块**。
- `mcp/registry.py` 3404 行单文件堆 53 个工具 schema，git 冲突热点。

## 循环依赖（14 对 mutual，高风险前几对）

- `mcp/cache.py` ↔ `src/store.py`（缓存 ↔ 领域存储，核心层互染，高）
- `mcp/cache.py` ↔ `src/retrieval.py`（高）
- `src/config.py` ↔ `src/store.py`（中）
- `mcp/tools/workspace_bootstrap.py` ↔ `workspace_layout.py`（中）
- `mcp/tools/wiki_index.py` ↔ `wiki_lint.py`（中）
- `mcp/tools/distill_conversation.py` ↔ `note_ingest.py`（中）

## 候选改进点（审查报告提出，未排期定案）

- C1：`mcp/cache.py` 拆出检索内核适配器（re-export 移到 `mcp/retrieval_adapter.py`，[LazyComponentStore](../../codewiki/mcp/cache.py) 拆 `component_store.py`）——最强候选。
- C2：`registry.py` 改自动发现（每个工具 handler 自带 `TOOL_DEF`，扫 `mcp/tools/*.py`）。
- C3：`store.py` 拆 writer/query/index/locking。
- C4：`distill_conversation.py` 拆 llm 调用层与 submit 协议层。
- C5：`wiki_lint.py` 按检查类别拆。
- C6：抽 `workspace_conventions.py` 纯数据模块解 bootstrap↔layout 循环。
- 报告建议优先级：C1 > C2 > C3 > C6 > C4 > C5。

## Rationale

热点数字与循环依赖对是代码核对的可复用事实，后续任何重构讨论都以此基线为起点，避免重复跑全量分析；候选优先级仅为报告建议，实施前需重新确认。
