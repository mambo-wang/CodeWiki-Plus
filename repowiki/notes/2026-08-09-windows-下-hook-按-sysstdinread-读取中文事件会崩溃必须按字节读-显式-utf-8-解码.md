---
type: pitfall
title: "Windows 下 hook 按 sys.stdin.read() 读取中文事件会崩溃，必须按字节读 + 显式 UTF-8 解码"
tags: ["pitfall"]
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:51Z }
stale_after: 2026-11-07

metadata:
  date: "2026-08-09"
  origin: "conversation"
  related_components: []
  related_modules: ["team-memory", "mcp", "\"\""]
  source_ref: "raw\\conv-20260808T152648Z.md"
---

## 背景

在中文 Windows 上，IDE 通过 stdin 传入含中文的 JSON 事件（如用户首句含中文）。原 `_load_event` 用 `sys.stdin.read()`，该调用走平台区域编码（cp936）。非 ASCII 字节被解码为 **lone surrogate**（`\udcXX`），随后 `write_text(encoding="utf-8")` 抛 `"'utf-8' codec can't encode … surrogates not allowed"`，中文对话归档直接崩溃。

## 正确做法

stdin 改为 `sys.stdin.buffer.read()` 按字节读，再显式 `bytes.decode("utf-8", errors="replace")`；stdout 在打印含中文的结果前 `sys.stdout.reconfigure(encoding="utf-8")`（带异常兜底）。这样无论平台区域编码如何，中文标题与正文都能正确落盘。

## 根因

Python 在 Windows 上 `sys.stdin` 默认使用控制台 locale 编码（cp936），`sys.stdin.read()` 不会强制 UTF-8，于是 UTF-8 字节被误当作 cp936 解码产生 lone surrogate。

## 适用范围

任何在 Windows 上由外部进程管道调用、且 payload 可能为 UTF-8 的 Python 脚本（尤其 IDE hook、子进程采集器）。
