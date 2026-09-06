---
type: pitfall
title: telemetry 原子写入崩溃会残留孤儿 *.tmp.<PID> 文件，且无自动清理机制
tags:
- keyboardinterrupt
- memoryerror
- pitfall
metadata:
  date: 2026-08-28
  task_id: 产品维护
  related_modules:
  - mcp/tools/telemetry
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-repowiki-.meta-telemetry-Administrator.-2.md
  scene: telemetry 原子写入与运维清理
status: stable
generated:
  by: codewiki/5.4.5
  at: 2026-08-28 04:17:10+00:00
stale_after: '2027-03-03'
origin: conversation
author: mambo-wang
verified:
- by: human:mambo-wang
  at: '2026-09-04T04:10:53Z'
---

## Background

用户发现 `repowiki/.meta/telemetry/Administrator.jsonl.tmp.19748` 这类孤儿临时文件，询问产生机制与删除时机。

## Root cause

`codewiki/mcp/tools/telemetry.py` 的 `_atomic_write_lines()` 采用「临时文件 + `os.replace` 原子替换」实现崩溃安全写入：临时文件命名 = 正式文件名 + `.tmp.<进程PID>`（`19748` 即写入进程 PID）；正常流程写临时文件后 `os.replace(tmp, path)` 原子替换，临时文件自动消失；抛 `OSError` 且进程存活时 `except OSError` 分支 `tmp.unlink()` 清理。但进程在 `write_text` 与 `os.replace` 之间被强杀/崩溃/断电、或抛出非 `OSError` 异常（如 `KeyboardInterrupt`、`MemoryError`）时，临时文件残留为孤儿文件。代码中没有启动流程或定时任务扫描删除 `*.tmp.*` 残留。

## 影响

不影响功能：`aggregate_usage` 用 `glob("*.jsonl")` 扫描 telemetry 目录，孤儿临时文件不以 `.jsonl` 结尾，不会被聚合读入。

## 正确做法

孤儿临时文件只是 git 中 untracked 残留，直接手动删除即可，无副作用。如需根治：为 `_atomic_write_lines` 补充更宽的异常兜底（`finally`/`BaseException` 清理），或在启动流程中加入残留扫描清理。
