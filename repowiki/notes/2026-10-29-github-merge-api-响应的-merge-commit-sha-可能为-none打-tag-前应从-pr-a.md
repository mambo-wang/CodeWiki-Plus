---
type: lesson
title: "GitHub merge API 响应的 merge_commit_sha 可能为 None——打 tag 前应从 PR API 取真实 merge commit"
tags: ["45", "github", "lesson"]
metadata:
  date: 2026-10-29
  confidence_level: weak
  task_id: 产品维护
  source_session: "23bfb17d128a4fecb57c58b6e7d89639"
  related_modules: ["release-workflow"]
  severity: medium
  source_ref: "conversations/conv-我先查一下-CodeBuddy-hooks-官方文档确认-`SessionEnd`-的-`matcher`-正确取值，同.md"
  scene: "发版流程 / GitHub API"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.4, at: 2026-10-29T09:09:30Z }
stale_after: 2027-04-27
origin: conversation

---

## Background

v5.16.5 发版中合并 PR #45 后，merge API（PUT /repos/{owner}/{repo}/pulls/{number}/merge）响应里 `merge_commit_sha: None`，无法直接用于打 tag。

## 正确做法

- 合并后改用 `GET /repos/{owner}/{repo}/pulls/{number}` 从 PR 对象取 `merge_commit_sha`（本次实证为 9e53173），再以此作为 Release API 的 `target_commitish` 让远端自动打 tag——避免依赖本地 main 是否同步。
- 本仓环境无 gh CLI，GitHub REST 调用统一用 Python 脚本 + `git credential fill` 取凭据（token 不落盘不打印）。

## Rationale

发版 SOP 中「合并 PR 后打 tag」一步依赖 merge commit sha；merge API 响应字段不可靠时需换 PR API 口径，否则 tag 可能打错 commit。该口径已在 v5.16.5 发版中实证，与《发版本 tag 位置约定统一：tag 打在 PR merge commit》决策笔记配套（那条定位置，本条定取 sha 的可靠口径）。
