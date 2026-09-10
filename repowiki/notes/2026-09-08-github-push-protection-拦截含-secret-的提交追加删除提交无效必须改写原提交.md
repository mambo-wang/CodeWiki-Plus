---
type: pitfall
title: GitHub Push Protection 拦截含 secret 的提交：追加删除提交无效，必须改写原提交
tags:
- github
- pitfall
metadata:
  date: 2026-09-08
  related_modules:
  - release
  severity: medium
  source_ref: conversations/conv-推送代码.md
  scene: 发布推送
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:07:03+00:00
stale_after: '2027-03-07'
origin: conversation
verified:
- by: wangbao
  at: '2026-09-08T05:27:33Z'
---

## Background

推送 `develop` 被 GitHub Push Protection 拦截：本地提交 `77ad5bb` 的 `repowiki/conversations/conv-发布新版本.md:294,340` 原样保留了完整 PyPI API Token。这是会话捕获把用户手动粘贴的 secret 原文写进对话归档造成的，正是 AGENTS.md「归档副本可能原样保留 token」警告的场景。

## 正确做法

Push Protection 扫描的是**本次推送的全部新提交**，在含 secret 的提交之上追加一个「删除」提交没有用——原提交仍含 secret，推送依旧被拒。必须让含 secret 的提交本身不再含 secret：本地**未推送**的提交用 `git commit --amend` 改写后再 push；已推送到远端的历史则需要 `git filter-repo` 之类的更强手段。

本次的做法（用户已确认）：把 3 处 token（294/340 完整 + 301 行截断前缀）替换为 `pypi-<REDACTED>` 占位符 → `git add -u` → `git commit --amend --no-edit`（保留原提交信息）→ 重新 push，本地 `77ad5bb` 变为 `1feefee`。

## 补充

- token 一旦明文进过本地仓库与归档，即便从提交中删除，**仍建议立即到 PyPI 轮换**。
- 后续可在 pre-push 加 secret 扫描（如 gitleaks）作为闸门。

## 适用范围

CodeWiki 会把对话原文归档进 `repowiki/conversations/*.md`，任何粘贴过 token/密钥的会话都会在归档里留明文，推送前需扫描。
