---
type: workaround
title: GitHub API 直连被阻时用 PowerShell Invoke-RestMethod 走系统网络栈，token 从 git 凭据管理器提取
tags:
- github
- powershell
- restmethod
- workaround
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - publishing
  severity: medium
  source_ref: conversations/conv-当前项目添加的hook和subagent只支持codebuddy，优化为支持市面上常见的智能体，比如自动检测有.qode.md
status: stable
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 03:33:23+00:00
stale_after: '2026-10-08'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T03:40:51Z'
---

## 背景

发布 v5.4.0 时 curl 直连 GitHub API 被网络策略阻断，但 git push 正常。

## 解法

改用 PowerShell `Invoke-RestMethod`（复用系统代理/网络栈）请求 GitHub Release API；Authorization token 通过 `git credential fill` 从 Windows 凭据管理器提取 github.com 凭据，避免硬编码 token。

## 适用范围

命令行通用工具被网络策略拦截时，复用 git/系统级工具的网络与凭据体系是可靠 fallback。
