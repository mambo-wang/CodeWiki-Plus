---
type: workaround
title: Windows PowerShell 下 git commit -m 传中文会乱码或被拆词：改用 UTF-8 消息文件 + git commit -F
tags:
- github
- powershell
- workaround
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-docs-团队知识库支持优化设计方案.md-@d-repos-CodeWiki-3.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:41:29+00:00
stale_after: '2026-10-20'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:48Z'
---

## 问题

在 Windows PowerShell 里直接 `git commit -m "中文提交信息"` 会把中文搞乱（乱码或被拆词）。

## 可行做法（多日多次实测有效）

把提交信息写入 UTF-8 文件（如从文章/文件首行读取标题写入），再 `git commit -F <message_file>`；提交后核对 commit message 显示为中文无误。

## 适用范围

含中文/emoji 的提交信息、或需要在 agent 执行器里传长参数给 git 的场景；同源问题也见于给 git credential fill 喂 stdin（见「git credential fill stdin」笔记）与 GitHub Release 正文编码，均源于 cmd/PowerShell 中间层对参数/编码的破坏。
