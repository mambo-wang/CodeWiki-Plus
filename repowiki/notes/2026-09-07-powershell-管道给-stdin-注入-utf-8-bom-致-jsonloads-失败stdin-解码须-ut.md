---
type: pitfall
title: PowerShell 管道给 stdin 注入 UTF-8 BOM 致 json.loads 失败：stdin 解码须 utf-8-sig + lstrip
  双保险
tags:
- pitfall
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - mcp
  - ide-hook
  severity: medium
  source_ref: conversations/conv-@settings.json-27-38-是不是有问题，python-m-codewiki.mcp._ide_hook.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 02:56:34+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:16Z'
---

## 背景

实测 `echo '<json>' | python -m codewiki.mcp._ide_hook --enable` 在 PowerShell 下事件解析直接失败：PowerShell 管道给 stdin 注入 UTF-8 BOM，而 `codewiki/mcp/_ide_hook.py` 的 stdin 分支用 `decode("utf-8", "replace")` 无 BOM 容错（wrapper `capture_session_end.py` 早有 `utf-8-sig` + lstrip 双保险，PowerShell 可能注入多个 BOM）。

## 正确做法

stdin 读事件一律 `decode("utf-8-sig", "replace").lstrip("\ufeff")`。2026-09-07 已修复并补回归测试 `test_stdin_utf8_bom_tolerated`（tests/test_ide_hook_capture.py，54 测试全绿）。

验证 hook 的 stdin JSON 时优先用文件方式（`--conversation <file>`，与 wrapper 转发方式一致）而非管道，最干净。

## 根因

Windows PowerShell 管道编码默认带 BOM；主路径与 wrapper 防御不对齐。
