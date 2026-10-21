---
type: lesson
title: 共享工作区多会话并行时提交必须用显式 pathspec，禁止 git add -A 扫入并行会话的改动
tags:
- codewiki
- lesson
- sessionend
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 日常维护
  source_session: ed14a297-e047-4eba-a36e-a07ac3b1ff1c
  related_modules:
  - git-workflow
  - mcp-tools
  severity: medium
  source_ref: conversations/conv-为什么最近的对话没有抓取保存到-repowiki-raw目录下-，sessionEnd-Hook没生效吗-21e3c8.md
  scene: 日常维护：多 agent 共享同一 worktree 时的提交隔离
  compiled_into:
  - skills/git-commit-hygiene/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 09:03:10+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: codewiki/5.15.0
  at: '2026-10-21T10:30:28Z'
---

## Background

2026-10-21 在 CodeWiki-Plus 仓库修复 Qoder SessionEnd 采集 bug 时，工作区里同时有另一个并行会话在干活：`git status` 显示大量非本会话的改动（`capture_conversation.py`、`test_strip_system_injection.py`、多条他人创建的笔记、任务记忆文件），且其中一部分已被并行会话 `git add` 进暂存区。

## 正确做法

多会话共享同一 worktree 时，提交自己的修复必须用显式 pathspec 绕过被污染的 index：

```
git commit -m "..." -- codewiki/mcp/_ide_hook.py tests/test_ide_hook_capture.py
```

- `git commit -- <paths>` 只提交指定路径的工作区内容，**不动 index 里他人已暂存的文件**（它们保持 staged、不被扫入本次提交）。
- 严禁 `git add -A` 或裸 `git commit`——会把并行会话的半成品改动一起提交。
- 提交前用 `git diff -- <paths>` 核对 diff 确实只含自己的修复（本次核对为 104 insertions/2 deletions，与预期一致）。
- 提交后用 `git status --short -- <自己的文件>` + `git log --oneline -1 origin/develop` 核验：自己的文件已 clean、远端 head 等于本地提交。

## Rationale

CodeWiki 的 MCP 工具（ingest_note/confirm_note/add_task_memory）会持续往 repowiki/ 写文件，多个 agent 会话并行时工作区必然互相污染；不隔离 pathspec 的提交会把别人的进行中工作固化进历史，且难以回退。本次实测 pathspec 提交后并行会话的暂存内容原样保留，互不干扰。

## 关联

- 与 `notes/2026-09-20-提交前清理暂存区测试残留并排除-scratch-与-codebuddyteams-临时目录.md` 同属 git 提交卫生但场景不同：那条讲单会话清理临时目录残留，本条讲多会话并行时的 index 污染隔离。
- 本会话的采集 bug 修复本身见 `notes/2026-10-21-qoder-sessionend-采集静默失败transcript-的-role-嵌在-message-下导致-0-tu.md`，回填方法论见 `notes/2026-10-21-历史会话回填方法论走-handle-capture-conversation-正典路径先核-git-sync-模式与-t.md`，此处不重复。
