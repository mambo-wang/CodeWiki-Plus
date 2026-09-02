---
type: pitfall
title: 对话归档原样保留用户消息密钥导致 push 被 GitHub 密钥扫描拦截
tags:
- github
- pitfall
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - capture_conversation
  - distill_conversation
  severity: high
  source_ref: conversations/conv-@command-codewiki-增量更新-Wiki.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:14:17+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:06Z'
reject_reason: 聚合进场景：发布与依赖治理方法
author: mambo-wang
---

## 背景

推送 develop 分支时被 GitHub 密钥扫描拦截：repowiki/conversations/ 中对话归档原样保留了用户消息里的 PyPI token（pypi-AgEI 开头）。

## 正确做法

定位归档文件后：1) 将 token 脱敏为 pypi-***（已脱敏）；2) 高熵 secret 扫描确认无其他残留；3) amend 提交后重新推送。事后吊销并重新生成泄露 token；本地 repowiki/raw/（gitignore 未推送）也可能含 token，需删除。

## 根因

capture_conversation 归档是用户消息原样副本，不做密钥识别。含真实密钥的对话一旦进入 git 跟踪就会被 GitHub 密钥扫描拦截。
