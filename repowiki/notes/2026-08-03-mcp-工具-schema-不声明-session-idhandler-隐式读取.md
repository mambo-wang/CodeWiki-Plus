---
type: lesson
title: MCP 工具 schema 不声明 session_id，handler 隐式读取
tags:
- codewiki
- lesson
aliases:
- session_id约定
- inputSchema约定
- MCP工具schema约定
status: stable
generated:
  by: codewiki
  at: 2026-08-03 01:32:32+00:00
stale_after: '2027-02-22'
metadata:
  date: 2026-08-03
  related_modules:
  - MCP_Tools
  - MCP_Core
  related_components: []
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:20Z'
---

## 背景

给 get_prompt 补充 bundle 定位参数时，发现其 inputSchema 缺 session_id，便顺手在 registry.py 里声明了该参数，被用户纠正：项目约定 session_id 不在工具 schema 中声明。

## 正确做法

CodeWiki 的 MCP 工具约定：session_id 是隐式参数——registry.py 的 inputSchema 不声明它，handler 内直接 `arguments.get("session_id")` 读取。绝大多数工具（write_doc_file、ingest_note、lint_wiki 等）都遵循此约定。

因此：
- 新增或修改工具 schema 时，不要声明 session_id
- 改 schema 前先对照同类既有工具的写法，而不是只看目标工具自身是否"完整"
- get_prompt 的 bundle 定位优先级为 output_dir（最直接）> repo_path > session_id（隐式）

## 根因

只检查了单个工具 schema 的参数完整性，未对照项目既有约定；"看起来缺参数"不等于"应该补声明"。

## 相关文档

- [MCP 薄壳架构与参数约定](../wiki/scenarios/MCP-Server薄壳架构与参数约定.md)
