---
type: lesson
title: "git reset --soft 后暂存区残留会混入 commit——git add 只增不减，拆 commit 前必须 restore --staged 并用 show --stat 核对"
tags: ["lesson"]
metadata:
  date: 2026-10-29
  confidence_level: weak
  task_id: 产品维护
  source_session: "23bfb17d128a4fecb57c58b6e7d89639"
  related_modules: ["release-workflow"]
  severity: medium
  source_ref: "conversations/conv-我先查一下-CodeBuddy-hooks-官方文档确认-`SessionEnd`-的-`matcher`-正确取值，同.md"
  scene: "发版流程 / git 提交拆分"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.4, at: 2026-10-29T09:09:22Z }
stale_after: 2027-04-27
origin: conversation
source_conversations: ['conversations/conv-@command-windows-python-release-发布版本5.16.3.md']

---

## Background

v5.16.5 发版拆 fix / bump 两个 commit 时，fix commit 两次混入暂存区里已有的 repowiki 产物（显示 5 files changed 而非预期的 2），需要本地反复 reset 重做。

## 正确做法

- `git reset --soft HEAD~n` 后暂存区保留全部原暂存内容，`git add <files>` 只增不减——不会移除其他已暂存项。
- 拆 commit 前先 `git restore --staged <不相关文件>` 显式移除暂存区残留，再 `git add` 目标文件提交。
- 每次 commit 后立即 `git show --stat --format=` 核对文件清单；推送前发现混入可本地 reset 重做，推送后则需 force-with-lease（又会触发 CI 的 force-push 脆弱性，代价更高）。

## Rationale

暂存区残留是「修复 commit 混入知识库产物」这类脏提交的高频根因；本会话两次踩中并实证「restore --staged + show --stat 核对」的可靠拆分口径，先核对再推送能避免连锁代价。与既有笔记《提交前清理暂存区测试残留并排除 .scratch 与 .codebuddy/teams 临时目录》互补：那条讲 pathspec 排除临时目录，本条讲 soft-reset 后的暂存区继承机制。

## git add -A 会把 .scratch/、docs/whitepaper 等未跟踪目录全部暂存：bump 提交前必须核对暂存区，改用 git add -u + 显式路径

> 合并自蒸馏候选：git add -A 会把 .scratch/、docs/whitepaper 等未跟踪目录全部暂存：bump 提交前必须核对暂存区，改用 git add -u + 显式路径

## 新实例：git add -A 扫入未跟踪目录（2026-10-26 发版 bump 提交）

发版 bump 提交前执行 `git add -A`，一次性暂存 157 个文件、8 万+行——混入 `.scratch/`（按约定不进公开仓库的会话内部工单目录）和 `docs/whitepaper/` 等与本次发布无关的未跟踪文件。

### 正确做法

- `git add -A` 后立即 `git diff --cached --stat` 与 `git diff --cached --name-only` 核对暂存区规模与文件清单
- 发现混入后 `git reset`，改用 `git add -u`（只加已跟踪文件的修改）+ 显式路径补充需要的未跟踪产物（如 `git add repowiki/conversations/`），本次收敛到 52 个文件
- 同主题既有笔记：`notes/2026-10-21-共享工作区多会话并行时提交必须用显式-pathspec禁止-git-add--a-扫入并行会话的改动.md`（多会话 index 污染隔离）、`notes/2026-09-20-提交前清理暂存区测试残留并排除-scratch-与-codebuddyteams-临时目录.md`（单会话临时目录排除）

### Rationale

发版提交要求内容精确可审计；`.scratch/` 误进公开仓库需回滚，且 8 万行 diff 会污染 PR 审查。
