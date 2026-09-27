---
type: pitfall
title: sync-commands 的 _STUB_TEMPLATE.format() 对 i18n description 中的花括号零防御
tags:
- keyerror
- pitfall
metadata:
  date: 2026-09-27
  confidence_level: weak
  source_session: 0a1834db4b12470e8f8ab0fdd5de61b9
  related_modules:
  - cli-commands
  - mcp-prompts
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-变更评估与代码评审-请对最近代码变更做影响范围评估（修改后.md
  scene: sync-commands 变更评审（ADR-0017）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 06:58:14+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-27T07:50:13Z'
---

## Background
`codewiki/cli/commands/sync_commands.py` 的 `_render_stub` 用 `_STUB_TEMPLATE.format(...)` 渲染宿主命令文件，title/description 来自 `i18n.t()`（`codewiki/mcp/locales/zh.yaml` / `en.yaml`）。

## Pitfall
`str.format` 会把 description 中的 `{...}` 当占位符解析：未来任何一条 prompt 描述带花括号（如代码示例 `{repo_path}`），`sync-commands` 整体抛 `KeyError` 失败。当前 23 条 zh/en description 均无花括号（`tests/test_i18n.py` 保证两语言同步），所以现在不炸——属脆弱点而非现行缺陷。

## 正确做法
format 前对动态文本转义：`s.replace("{", "{{").replace("}", "}}")`，或改用 `string.Template`。

## Rationale
i18n 文案是持续增长的外部输入，渲染模板对其格式零防御；一旦触发是整命令级失败，且报错点远离根因，排查成本高。
