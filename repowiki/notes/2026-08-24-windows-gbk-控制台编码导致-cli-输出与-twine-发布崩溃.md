---
type: pitfall
title: Windows GBK 控制台编码导致 CLI 输出与 twine 发布崩溃
tags:
- pitfall
- powershell
- unicodeencodeerror
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - cli
  - publishing
  severity: medium
  source_ref: conversations/conv-当前项目添加的hook和subagent只支持codebuddy，优化为支持市面上常见的智能体，比如自动检测有.qode.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 03:33:20+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T03:40:50Z'
reject_reason: 聚合进场景：发布与依赖治理方法
author: mambo-wang
---

## 背景

多 IDE hook 接线功能发布时，CLI 输出与 twine 上传在 Windows 控制台崩溃。

## 现象

Windows 控制台默认 GBK 编码，输出含 ✓、→、•（rich 进度条）等非 GBK 可编码字符时抛 UnicodeEncodeError。两处受影响：①工具自身 CLI 输出；②twine 上传时的 rich 进度条（• 符号）。

## 修复

①twine 加 `--disable-progress-bar` 关闭进度条；②通用规避：PowerShell 设置 `$env:PYTHONIOENCODING="utf-8"` 或 `chcp 65001` 切 UTF-8 代码页。

## 根因

Windows 控制台编码与工具内部 UTF-8 不一致，非业务逻辑问题。

## 适用范围

任何在 Windows 控制台输出非 ASCII 符号的 CLI 工具及 Python 发布流程。
