---
type: lesson
title: main/develop 分叉且 tag 只打在 develop 上：用 git merge -X ours origin/main 以 develop
  为权威分支合并
tags:
- '32'
- lesson
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 0bf7597a49a6454d97c6523997109749
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5af19e.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:22:17+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:15Z'
---

## Background
发布 v5.11.0 创建 develop→main 的 PR 时报 405 merge conflicts，`git merge-tree` 显示几乎全部文件 add/add 冲突。

## Root cause
main 停在 v5.9.0（PR #32），v5.10.0/v5.10.1 的 tag 都只在 develop 上，develop 历史与 main 严重分叉；main 独有提交只是历史 release 的 bump/merge，内容均被 develop 演进版覆盖。develop 是权威分支。

## 正确做法
本地将 `origin/main` 合入 develop，冲突全部取 develop 侧：`git merge -X ours origin/main -m "merge: sync main into develop"`，验证（版本一致性 + 抽样测试）后推送 develop，PR 即可合入。

## Rationale
分支权威关系判断 + 定向冲突取舍的合并手法，遇到 main/develop 分叉的仓库发布场景可直接复用。
