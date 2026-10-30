---
type: lesson
title: CI 只做增量 lint（本次变更的 py 文件），本地 ruff 全量跑出的历史遗留错误不算回归
tags:
- lesson
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 184920b147de4d1f9e2ce9a39d25a453
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-2.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:25:55+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:16Z'
source_conversations: ['conversations/conv-@command-windows-python-release-发布版本5.16.3.md']

---

## Background
发布 v5.12.0 前本地 `ruff check .` 全量跑报 33 错 + 58 文件待重排，数量异常，一度以为有严重问题。

## Root cause
CI（`.github/workflows/ci.yml`）只检查本次变更的 py 文件（增量 lint），历史遗留的 F841/格式问题不在范围内；本地全量跑范围更严，混入了历史债。

## 正确做法
本地 lint 数量异常时先核对 CI 的实际检查范围，区分「本次改动引入」与「历史遗留」。只修本次改动造成的错误（本会话：prompts.py 三处 F841），历史遗留留待专门清理，不要被全量结果带偏。

## Rationale
增量 lint 是常见 CI 配置，全量本地 lint 结果不能直接等同于回归判定。

## ruff format --check 全仓跑会因 repowiki/conversations/*.md 内嵌代码块失败：本地发布闸门按 CI 同口径只查变更 py 文件

> 合并自蒸馏候选：ruff format --check 全仓跑会因 repowiki/conversations/*.md 内嵌代码块失败：本地发布闸门按 CI 同口径只查变更 py 文件

## 新实例：ruff format --check 全仓跑命中 md 采集产物（2026-10-26 v5.16.3 发版闸门）

发版闸门跑 `uv run python -m ruff format --check .` 失败，失败文件全部是 `repowiki/conversations/*.md`（对话采集产物内嵌代码块被 ruff 识别为待格式化内容），并非 Python 源码问题。

### 正确做法（本地发布闸门按 CI 同口径）

1. `git diff --name-only <上一tag>..HEAD -- "*.py"` 列出本次变更的 py 文件
2. 对这些文件跑 `ruff format --check <files>`
3. 全仓 format --check 的 md 失败不阻塞发布

### Rationale

本地闸门口径与 CI 不一致会导致两种错误：误判阻塞发布（md 误报），或漏放行（CI 范围内的问题本地没查）。以 CI 实际检查范围为准是唯一可靠口径。
