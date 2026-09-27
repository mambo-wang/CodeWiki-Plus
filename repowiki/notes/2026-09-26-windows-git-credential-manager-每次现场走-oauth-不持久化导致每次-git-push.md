---
type: pitfall
title: Windows Git Credential Manager 每次现场走 OAuth 不持久化，导致每次 git push 弹账号选择框
tags:
- github
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 0bf7597a49a6454d97c6523997109749
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5af19e.md
  scene: 发布流程
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:20:57+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:24Z'
---

## Background
发布 v5.11.0 期间每次 `git push` / `git fetch` / Python 脚本里调 `git credential fill` 都弹出账号选择框，用户多次手动点击。

## Root cause
GCM（Git Credential Manager）里没有持久化的 GitHub 凭证——每次弹框都是现场走 OAuth 生成新 token，从未存入凭证存储，所以每次都弹。

## 正确做法
执行 `gh auth login`（或 `gh auth login --with-token`）后运行 `gh auth setup-git`，让 gh 成为 git 的凭证助手，一次完成 gh 登录与 git 凭证持久化，之后 push/fetch 不再弹框。

## Rationale
自动化发布流程被弹框阻塞很常见，根因是凭证未持久化而非 git 配置问题。
