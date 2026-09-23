---
type: pitfall
title: 每日工作记忆文件是 append-only，用 write_to_file 覆盖会丢当天早前记录
tags:
- pitfall
metadata:
  date: 2026-09-23
  confidence_level: shadow
  task_id: 产品维护
  source_session: bb80ce6d0e5b4cf8a6af19bcb6e6b54a
  related_modules:
  - agent-memory
  severity: medium
  source_ref: conversations\conv-working_memory_content-The-following-is-the-existing-working-4.md
  scene: 产品维护/记忆文件写入
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.12.0
  at: 2026-09-23 01:11:37+00:00
stale_after: 2027-03-22
origin: conversation
reject_reason: 用户拒绝：IDE 宿主工作记忆通道的通用纪律，不属于 CodeWiki 项目知识
---

## Background

在会话收尾向 `.codebuddy/memory/2026-09-21.md`（每日工作记忆文件）写入当日新进展时，直接用 `write_to_file` 覆盖了整个文件，导致当天早前的记录（init 接线修复、v5.12.0 发布等条目）被覆盖丢失。直到下一轮 `git status` 看到该文件显示大量删除才发现。

## Root cause

每日记忆文件（`.codebuddy/memory/YYYY-MM-DD.md`）是 append-only 语义：一天内多个会话都会向同一文件追加条目。`write_to_file` 是整文件覆盖，写入时若未先读取并包含原有全部内容，就会静默丢弃早前会话的记录。

## 正确做法

- 向已存在的每日记忆文件写入时，必须先 `read_file` 读取现有内容，再用 `replace_in_file` 在末尾追加新条目；或用 `write_to_file` 但正文必须包含读取到的原有全部内容。
- 提交前用 `git diff` 检查记忆文件是否出现异常的大量删除行——每日文件正常变更只应是追加。

## Recovery

发现覆盖丢失后，用 `git checkout HEAD -- .codebuddy/memory/<date>.md` 恢复仓库版本，再把新条目合并追加回去，然后才继续提交推送。

## Rationale

值得沉淀是因为该错误静默发生（写入本身成功、无报错），只有 git diff 才能暴露，且直接造成跨会话上下文丢失；任何向 append-only 文件写入的场景都适用同样的纪律。
