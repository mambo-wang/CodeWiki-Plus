---
type: procedure
title: "提交前清理暂存区测试残留并排除 .scratch 与 .codebuddy/teams 临时目录"
tags: ["codewiki", "procedure"]
metadata:
  date: 2026-09-20
  confidence_level: weak
  source_session: "3eec7b47a2b64730b08dba9d8edd43b8"
  severity: medium
  source_ref: "conversations/conv-working_memory_content-The-following-is-the-existing-working-5.md"
  scene: "git 提交卫生"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.10.1, at: 2026-09-20T15:44:25Z }
stale_after: 2027-03-19
origin: conversation

---

## Background

在 CodeWiki-Plus 仓库执行「提交推送代码」时，暂存区里混入了 3 个 `.scratch/mcp-test` 测试残留文件（工作区已删除但仍在暂存区），直接 `git add -A` 会把已删除文件的残留暂存一并提交。

## 正确做法

1. 先 `git status` + `git diff --cached --stat` 检查暂存区，发现 `.scratch/mcp-test` 残留后用 `git restore --staged .scratch/mcp-test` 取消暂存；
2. 提交时用 pathspec 排除临时目录：`git add -A -- . ':!.scratch' ':!.codebuddy/teams'`；
3. `git status --short` 复核暂存内容后再 commit + push；
4. 提交信息按仓库惯例使用中文 conventional commit 格式（如 `feat: ADR-0014 蒸馏固定只产经验笔记，任务记忆通道归主动沉淀独占`）。

## Rationale

`.scratch/`（pytest/lint 输出）与 `.codebuddy/teams/`（多智能体临时目录）是本仓库两类高频临时产物，提交前显式排除可避免测试残留污染提交历史。
