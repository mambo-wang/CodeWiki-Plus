---
name: git-commit-hygiene
description: 在共享 worktree 多会话并行或暂存区有残留时提交代码——用显式 pathspec 只提交自己的文件并排除临时目录，禁止 git add -A 或裸 commit 扫入并行会话的改动
type: Skill
status: draft
generated:
  by: codewiki/5.15.0
  at: "2026-10-21T10:33:59Z"
stale_after: 2027-01-19
metadata:
  summary: git 提交卫生：多会话共享 worktree 用显式 pathspec 隔离提交 + 单会话暂存区残留清理与临时目录排除
  source_refs: ["notes/2026-10-21-共享工作区多会话并行时提交必须用显式-pathspec禁止-git-add--a-扫入并行会话的改动.md", "notes/2026-09-20-提交前清理暂存区测试残留并排除-scratch-与-codebuddyteams-临时目录.md"]
  revisions:
    - at: "2026-10-21T10:33:59Z"
      reason: created from candidate materials
      source: skill_creator
---

## 工作场景

多个 agent 会话（或多人）共享同一 git worktree 并行干活，需要提交本会话的改动。典型信号：`git status` 里出现大量非本会话产生的改动（他人正在编辑的源码、笔记、任务记忆文件），其中一部分已被并行会话 `git add` 进暂存区。知识飞轮类工具（ingest_note/confirm_note/add_task_memory 等）会持续往 repowiki/ 写文件，多会话并行时工作区必然互相污染。

## 适用条件

- 工作区存在并行会话/并行 agent 的进行中改动，需要提交本会话的修复。
- 单会话场景下暂存区混入测试残留或临时目录产物，提交前需要清理。

## 核心 SOP

1. 提交前 `git status --short` + `git diff --cached --stat` 盘点：区分「本会话的文件」与「并行会话的文件」；暂存区里若有并行会话已暂存的内容，保持原样不动。
2. 多会话场景用显式 pathspec 提交，绕过被污染的 index：

   ```
   git commit -m "..." -- <自己的文件1> <自己的文件2>
   ```

   `git commit -- <paths>` 只提交指定路径的工作区内容，不动 index 里他人已暂存的文件（实测提交后并行会话的暂存内容原样保留）。
3. 提交前 `git diff -- <paths>` 核对 diff 确实只含自己的修复，量级与预期一致。
4. 提交后 `git status --short -- <自己的文件>` + `git log --oneline -1` 核验：自己的文件已 clean、提交内容正确。
5. 单会话残留场景：先 `git restore --staged <残留路径>` 取消暂存，再用排除模式 `git add -A -- . ':!.scratch' ':!<临时目录>'` 后提交，`git status --short` 复核暂存内容。

## 判断逻辑

- 多会话并行 → 显式 pathspec 提交（index 不可信，绕过它而不是清理它）。
- 单会话但有测试/临时产物残留 → 清理暂存 + 排除模式（index 可信，清理它）。
- 不确定某文件归属 → 先查（读文件内容/问用户），不猜着提交。

## 禁忌与反模式

- 严禁多会话场景下 `git add -A` 或裸 `git commit`——会把并行会话的半成品改动固化进历史，且难以回退。
- 不要 `git restore --staged` 并行会话已暂存的文件——那是别人的进行中工作。
- 不要依赖下游幂等当安全网。

依据: notes/2026-10-21-共享工作区多会话并行时提交必须用显式-pathspec禁止-git-add--a-扫入并行会话的改动.md（pathspec 提交实测后并行会话暂存内容原样保留，互不干扰）；notes/2026-09-20-提交前清理暂存区测试残留并排除-scratch-与-codebuddyteams-临时目录.md（单会话残留清理与 .scratch/teams 临时目录排除模式）。
