---
type: pitfall
title: CodeBuddy hook 有源/项目双副本，改 task_session_start.py 需同步源副本才随包分发
tags:
- codebuddy
- pitfall
metadata:
  date: 2026-08-15
  task_id: 产品维护
  related_modules:
  - task-memory
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-.meta-task_bindings-这里文件的作用是什么.md
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 15:07:52+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T15:08:29Z'
reject_reason: consolidated into IDE-Hook采集链路方法
---

## 背景

团队想把「会话开始先关联任务」的引导规则固化到 CodeBuddy hook，让使用这个 MCP 的每个人都生效。修改时发现存在两个同名文件，容易改错地方。

## 正确做法

`task_session_start.py` 存在「源副本 / 项目副本」双副本：

| 文件 | 角色 |
|---|---|
| `codewiki/hooks/task_session_start.py` | 源副本，随 `codewiki` 包分发，不直接运行 |
| `.codebuddy/hooks/task_session_start.py` | 项目副本，CodeBuddy 实际运行它 |

改 hook 要**改源副本**（随包分发到所有用户），并同步项目副本（本仓库立即生效）。项目副本由 `team-memory-hook` prompt 在启用时从源副本 `Copy-Item` 强制复制而来，`prompts.py` 强调「务必复制，不要凭记忆重写，以免与 codewiki 包行为不一致」。

## 根因

只改项目副本仅对本仓库生效；下次其他用户启用 hook 时会从源副本重新复制，覆盖本地改动，且改动不随 `codewiki` 包分发。
