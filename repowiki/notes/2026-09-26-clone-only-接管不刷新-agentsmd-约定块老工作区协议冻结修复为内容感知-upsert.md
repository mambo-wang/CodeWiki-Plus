---
type: pitfall
title: clone-only 接管不刷新 AGENTS.md 约定块（老工作区协议冻结），修复为内容感知 upsert
tags:
- codewiki
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 184920b147de4d1f9e2ce9a39d25a453
  related_modules:
  - MCP_Tools_Workspace
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-2.md
  scene: 多仓工作区初始化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:26:36+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:20Z'
---

## Background
用真实老版本工作区（CodeWiki-Plus-Harness）重跑 init_workspace 实测：骨架齐备走 clone-only 接管时，`CodeWiki LLM Wiki` 块仍是旧措辞（缺「产出语言」节、旧采纳声明）。

## Root cause
`_adopt_initialized_workspace` 的 clone-only 分支设计为「AGENTS.md is left untouched（adopted workspaces stay clean）」——本意保护手工搭建的工作区不被重写，但副作用是老版本初始化的工作区永远无法通过重跑 init_workspace 升级约定块。install-hooks 每次都 upsert 它管的两块，init_workspace 却在接管路径跳过，行为不一致。

## 修复（commit d0180eb）
clone-only 分支增加两个块的内容感知 upsert：`write_workspace_conventions`（约定块）+ `write_agents_md`（CodeWiki 使用块），语义与 install-hooks 一致——标记区间内刷新为最新模板、区间外不动、内容一致零写盘；写入失败降级为 WARNING 不阻塞接管。

## 验证
重跑返回 `agents_md_conventions: refreshed`，「产出语言」「主动沉淀协议」等新节全部到位；更新 2 个旧断言 + 新增老版本块升级用例。

## Rationale
工具维护块必须走统一 upsert 语义，否则协议升级无法同步到老工作区（2026-09-21 实测实锤的缺口）。注意：改动后 MCP server 旧进程仍加载旧代码，需重启后才生效。
