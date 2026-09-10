---
type: pitfall
title: Windows PowerShell 下 git add 中文路径会静默失败，导致 commit --amend 漏掉改动
tags:
- pitfall
- powershell
metadata:
  date: 2026-09-08
  related_modules:
  - release
  severity: medium
  source_ref: conversations/conv-推送代码.md
  scene: 发布推送
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:07:11+00:00
stale_after: '2027-03-07'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-08T05:28:18Z'
---

## Background

脱敏后执行 `git add repowiki/conversations/conv-发布新版本.md && git commit --amend --no-edit`。PowerShell 下 `git add` 因中文路径编码乱码失败，但命令链继续往下走，amend 只重提了旧内容——新提交 `69eaa79` 仍含 secret，直到 `git grep` 校验才发现。

## 正确做法

- 用 `git add -u`（或 `git add -A`）暂存，避免手写中文路径。
- **不要用退出码判断 amend 是否成功**：amend 本身几乎永远成功。改完必须验证提交内容，例如 `git grep -c "<token 前 30 位>" <新 sha>`（无匹配才算干净），并 `git status --short` 确认工作区已无待暂存改动。
- 确实要按路径暂存中文文件时，先确认终端为 UTF-8 编码。

## Root cause

PowerShell 传给 git 的中文路径字节被 git 按另一编码解释 → pathspec 不匹配 → git 报错；用 `&&` 串联时该错误被后续命令掩盖，工作区仍显示 `M`，amend 变成一次「空改写」。
