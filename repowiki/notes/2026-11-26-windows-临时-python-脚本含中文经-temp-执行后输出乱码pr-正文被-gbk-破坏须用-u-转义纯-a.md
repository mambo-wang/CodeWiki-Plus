---
type: pitfall
title: "Windows 临时 Python 脚本含中文经 %TEMP% 执行后输出乱码：PR 正文被 GBK 破坏，须用 \\u 转义纯 ASCII 源码"
tags: ["49", "appdata", "github", "pitfall", "powershell"]
metadata:
  date: 2026-11-26
  confidence_level: weak
  task_id: 发版本
  source_session: "2ab7a61e2f8a4461bcac02b382a185a5"
  related_modules: ["release-workflow"]
  severity: medium
  source_ref: "conversations/conv-@command-windows-python-release-发布小版本5.16.7.md"
  scene: "发版本"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.7, at: 2026-11-26T03:21:18Z }
stale_after: 2027-05-25
origin: conversation

---

## Background

v5.16.7 发布流程中，用 write_to_file 把含中文正文的 Python 脚本（建 PR / 修 PR 正文）写到 `C:\Users\...\AppData\Local\Temp\`，再经 PowerShell 执行调 GitHub REST API。创建 PR #49 后发现 PR 正文中文全部乱码——脚本源文件在 Windows 编码层被按 GBK 解读，中文以错误编码发给了 API。

## 正确做法

- 含中文的临时 Python 脚本不要直接写中文字面量；把所有非 ASCII 字符改写成 `\uXXXX` 转义，使源码为纯 ASCII，从根上绕开编码层歧义。
- 出现乱码后可用同样的纯 ASCII 源码脚本 PATCH PR 正文修复（本次 PR #49 正文即这样修复，Release 正文无乱码）。

## Rationale

Windows 控制台默认 GBK 代码页，`%TEMP%` 路径 + PowerShell 子进程链路中任何一环按本地代码页解读源文件都会破坏中文；纯 ASCII 源码在任何代码页下字节不变，是确定性绕法。与既有笔记《PowerShell 下命令输出与临时文件的四个编码/语法坑》互补：那条讲 shell 语法层（%TEMP% 不展开、重定向 UTF-16），本条讲 Python 脚本源文件编码层。

## Root cause

脚本源文件编码层问题：中文以 UTF-8 写入但被按 GBK 解读（或反之），非 GitHub API 侧问题。
