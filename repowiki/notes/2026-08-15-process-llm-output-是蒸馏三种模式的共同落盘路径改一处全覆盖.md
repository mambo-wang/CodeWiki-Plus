---
type: architecture
title: _process_llm_output 是蒸馏三种模式的共同落盘路径，改一处全覆盖
tags:
- architecture
metadata:
  date: 2026-08-15
  related_modules:
  - distill_conversation
  source_ref: raw\conv-codewiki蒸馏对话.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:13:08+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:03Z'
---

## 背景

`distill_conversation` 支持三种模式：Mode A（subagent 注入 `llm` async 回调，内联）、Mode B（`run_in_background=true` 从 `MAIN_MODEL`/`LLM_BASE_URL` 环境变量构建 LLM）、Mode C（IDE Agent 当 LLM，`prepare`/`submit` 两段走纯 MCP JSON）。

## 事实

三种模式的产物（notes + memories）最终都汇聚到 `_process_llm_output` 统一处理：解析 → 去重 → ingest draft → memories 暂存 → mark/delete raw → 重建索引。

## 维护含义

给蒸馏产物加逻辑（如 memories 确认闸门、返回字段改名）只需改 `_process_llm_output` 一处即可覆盖三种模式，无需分别改动各模式入口。
