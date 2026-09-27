---
type: pitfall
title: Windows 无控制台宿主启动控制台程序会闪窗：MCP server 内 git 子进程用 CREATE_NO_WINDOW 抑制
tags:
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 产品维护
  source_session: 3c66cef70fe44efb83b144ff46966a98
  related_modules:
  - git_sync
  - config
  - doc_writer
  - note_query
  - workspace_bootstrap
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-4.md
  scene: 产品维护
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:41:37+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:07Z'
---

## 现象

MCP server 自动提交（auto_push）repowiki 文件时，每次 git 命令都闪一个 cmd 弹窗后快速关闭；auto_push 一次跑 add→commit→push（失败还有 fetch+rebase 重试）多条命令，弹多次，严重影响体验。

## 根因

MCP server 由 IDE 拉起时**本身没有控制台**。Windows 上无控制台父进程启动控制台程序（如 `git.exe`）时，系统会为新进程分配一个全新控制台窗口——每跑一条 git 命令就闪一个 cmd 窗口。`run_git_bounded` 只设了 `CREATE_NEW_PROCESS_GROUP`（用于超时杀进程树），漏了 `CREATE_NO_WINDOW`。

## 修复

1. 新增共享 helper `windows_creationflags()`：Windows 返回 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`，非 Windows 返回 0。
2. `git_sync.py` 的 `run_git_bounded` 改用它——auto_push/auto_stage/sync_check 全链路收口。
3. 同款修复 MCP server 内另外 4 处直接 subprocess 调用：`config.py` `_git_config_value`、`doc_writer.py` `git rev-parse`、`note_query.py` `_last_commit_time`、`workspace_bootstrap.py` `git clone`。
4. 补守门测试 `test_windows_creationflags_suppresses_console` 防回归。

## 注意

- 需要重启 MCP server（或 IDE）才生效——运行中的 server 还是旧代码。
- `capture_session_end.py` 的 `DETACHED_PROCESS` 本身不弹窗，无需改动。
- CLI/分析器进程有控制台宿主，不在闪窗路径上，无需处理。
