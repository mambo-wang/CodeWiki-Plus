---
type: pitfall
title: prompt 正文是「逻辑+模板」混合体，不能整块搬进 YAML 语料
tags:
- pitfall
- powershell
metadata:
  date: 2026-09-07
  task_id: 产品维护
  related_modules:
  - mcp
  - prompts
  - i18n
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md
  scene: MCP 国际化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 06:49:04+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:23Z'
---

## 背景

最初估算 i18n 工作量时，把 `codewiki/mcp/prompts.py` 的 22 个 `_prompt_*` 函数（约 1250 行）当作纯文案，认为「整块搬进 YAML 即可」。抽查 `_prompt_init_wiki`（`codewiki/mcp/prompts.py:94-204`）后推翻了这个估算。

## 正确做法

这些函数不是纯文案，而是**逻辑 + 模板**混合体，包含：条件分支（`enable_task_management` 决定是否拼接 `hook_block`、`step_shift` 步进移位）、运行时占位符（`{repo_path}`、`{2 + step_shift}`）、JSON 示例的 `{{ }}` 转义、PowerShell/JSON 代码围栏、对中文常量块（如 `_TASK_MEMORY_AGENTS_SECTION`）的引用。22 个正文函数同构。

因此无法整块搬 YAML——每个函数必须重写为「按语言取模板片段 + 保留原有逻辑」，英文版正文是一次约 1250 行的英文**创作**而非查表翻译。`codewiki/mcp/tools/agents_md.py:217-347` 的 AGENTS.md 约定块是同构结构，落盘产物翻译面临同样问题。

## 根因

文案与生成逻辑写在同一个 f-string 模板里，模板不是纯数据。估 i18n/抽取类工作量前，应先抽查一两个最长的正文函数确认结构，再给结论。
