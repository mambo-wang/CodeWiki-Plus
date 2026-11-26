---
type: procedure
title: "本机无 gh CLI 时用 Python + git credential fill 调 GitHub REST API 完成 PR/合并/Release 全流程"
tags: ["github", "procedure"]
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
generated: { by: codewiki/5.16.7, at: 2026-11-26T03:21:29Z }
stale_after: 2027-05-25
origin: conversation

---

## Background

v5.16.7 发布时本机没有 gh CLI，需要完成：建 PR develop→main、修 PR 正文、轮询 CI check-runs、等绿后合并、创建 GitHub Release。

## 做法（v5.16.7 实测跑通）

1. 用 Python 脚本调 `git credential fill` 取 GitHub 凭据（不落盘、不打印），用 Basic Auth 调 GitHub REST API。
2. POST `/repos/<owner>/<repo>/pulls` 创建 PR；正文含中文时源码用 `\u` 转义纯 ASCII（见同场景 pitfall 笔记）。
3. 轮询 PR 的 check-runs，Test + Lint 全绿后 PUT 合并。
4. 创建 Release 时传 `target_commitish` 指向 merge commit，tag 由远端自动打在该 merge commit 上（本地无需先打 tag，事后同步本地 tag 即可）。

## Rationale

无 gh CLI 的环境下这条链路可完整替代 gh pr create/merge/release；凭据经 git credential fill 取用与既有 keyring/凭据管理约定一致，token 不落盘。与既有笔记《GitHub merge API 响应的 merge_commit_sha 可能为 None》互补：那条定单点坑（从 PR API 取真实 sha），本条定端到端流程顺序与各步 API。
