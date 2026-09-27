---
type: pitfall
title: GitHub Actions 用 check-runs 而非 commit status，轮询 combined status 会永远 pending
tags:
- '34'
- github
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 0bf7597a49a6454d97c6523997109749
  severity: high
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5af19e.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:22:08+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:18Z'
---

## Background
发布 v5.11.0 时，PR #34 的 CI 已全绿（check-runs 显示 Lint ✓ Test ✓），但按 commit status 的 combined status API 轮询时一直是 pending，后台等待脚本永远不会触发合入。

## Root cause
该仓库的 CI 是 GitHub Actions，产生的是 check-runs，不产生 commit status。轮询 `repos/{owner}/{repo}/commits/{sha}/status` 这类 API 只反映 commit status，所以永远 pending。

## 正确做法
GitHub Actions 仓库判断 CI 是否通过必须轮询 check-runs API（`GET /repos/{owner}/{repo}/commits/{sha}/check-runs`），逐个 check-run 看 conclusion 为 success/failure；不要用 combined status 轮询。

## Rationale
后续任何用脚本等待 CI 绿后自动合入 PR 的场景都会踩这个坑，直接核对 check-runs 才能正确判断。
