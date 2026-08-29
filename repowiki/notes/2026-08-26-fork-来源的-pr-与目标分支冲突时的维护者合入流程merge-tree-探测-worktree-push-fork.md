---
type: lesson
title: fork 来源的 PR 与目标分支冲突时的维护者合入流程（merge-tree 探测 + worktree + push fork）
tags:
- '16'
- codewiki
- lesson
- liberifatali
metadata:
  date: 2026-08-26
  severity: medium
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 16:38:39+00:00
stale_after: 2027-02-22
---

## 背景

评审 PR #16（head 在 fork LiberiFatali/CodeWiki-Plus）后发现其与 develop 冲突：develop 在评审后又合入了新提交，`.gitignore` 与 PR 的删除重叠。PR head 分支不在主仓库，本地 `git fetch <pr-branch>` 报 404；`gh pr view --json mergeable,mergeStateStatus` 显示 `CONFLICTING`/`DIRTY`——注意此时 CI 两个检查均为 SUCCESS，**CI 通过不等于可合并**。

## 正确做法

1. 用 `git merge-tree --write-tree --name-only <base> <head>` 快速探测冲突文件清单，无需真实 checkout/merge。
2. 确认 PR 来源：`gh pr view --json isCrossRepository,headRepository`；fork PR 合入前查 `gh api repos/<owner>/<repo>/pulls/<n> --jq .maintainer_can_modify`，为 false 时只能请作者解决或换合并策略。
3. 工作区有未提交改动时，用 `git worktree add <tmp> <head> -b <branch>` 在独立目录解决冲突（不污染主工作区），完成后 `git worktree remove --force` 并 `git branch -D` 清理。
4. 冲突解决后 `git push https://github.com/<fork-owner>/<repo>.git <local-branch>:<pr-branch>` 更新 PR 分支（maintainer_can_modify=true 时 GitHub 允许维护者推 fork 的 PR head），再 `gh pr merge --merge`。

## 根因

fork PR 的 head 分支属于 fork 仓库，维护者无法直接 push 修复；主工作区常驻未提交改动时直接 checkout 会污染它们。合入前先用 API 字段确认可修改性，再选最小侵入路径。

## 适用范围

维护者合入外部（fork）PR 且发生冲突时；判断 mergeStateStatus=CONFLICTING 时不要先怪 CI。
