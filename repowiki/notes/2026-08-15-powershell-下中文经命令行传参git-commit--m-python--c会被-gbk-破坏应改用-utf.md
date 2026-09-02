---
type: workaround
title: PowerShell 下中文经命令行传参（git commit -m / python -c）会被 GBK 破坏，应改用 UTF-8 文件方式
tags:
- powershell
- workaround
metadata:
  date: 2026-08-15
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-raw-conv-system_reminder-请注意，当.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 08:57:56+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T08:58:59Z'
reject_reason: 聚合进场景：发布与依赖治理方法
author: mambo-wang
---

## 背景

在 Windows PowerShell 下执行 `git commit -m "中文消息"` 或 `python -c "中文代码"` 时，中文字符串在传参过程中被 GBK 编码破坏，导致 commit message 或脚本内容乱码。

## 现象

- git commit message 实际存储的字节就是乱码（PowerShell 传参时中文被 GBK 编码破坏），用 Python 校验 commit 对象可确认是存储问题而非终端显示问题
- `python -c` 内嵌的中文在 PowerShell 传参时就被破坏，所以写入临时文件的内容本身就是坏的

## 正确做法

- 提交含中文的 commit message：用 `git reset --soft HEAD^` 撤销（保留暂存区），再用 UTF-8 文件方式重新提交（如 `git commit -F <文件>`）
- 执行含中文的 Python 代码：避免 `python -c` 内嵌中文，改用 write_to_file 直接写 UTF-8 脚本文件再运行

## 根因

Windows PowerShell 默认用系统 ANSI 代码页（GBK）解释命令行参数，与 UTF-8 不一致。

## 相关文档

- [CLI 命令](../wiki/modules/CLI_Commands.md)
- [文档索引](../wiki/index.md)
