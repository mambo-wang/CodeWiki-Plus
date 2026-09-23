---
type: pitfall
title: "PowerShell 单引号字符串内联 JSON 时反斜杠转义会失败，改用正斜杠路径"
tags: ["codewiki", "pitfall", "powershell"]
metadata:
  date: 2026-09-20
  confidence_level: weak
  source_session: "e866661e10b142f9a5beed824e215500"
  severity: medium
  source_ref: "conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区.md"
  scene: "hook 脚本模拟事件验证"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.10.1, at: 2026-09-20T15:45:36Z }
stale_after: 2027-03-19
origin: conversation

---

## Background

用 PowerShell 单引号字符串向 hook 脚本 stdin 内联 JSON 模拟事件（如 `'{"session_id":"verify-1","transcript_path":"d:/tmp/conv.json","cwd":"d:\repos\CodeWiki-Plus",...}' | python capture_session_end.py`）时，JSON 中的 `\r`（`d:\repos`）被解析为非法转义导致失败。

## 正确做法

JSON 内路径一律用正斜杠（`d:/repos/CodeWiki-Plus`），避免反斜杠转义问题；重试即通过。

## Rationale

这是 Windows 下验证 hook 脚本的固定摩擦点，正斜杠路径在 Python/JSON 侧完全兼容，可一次性规避。
