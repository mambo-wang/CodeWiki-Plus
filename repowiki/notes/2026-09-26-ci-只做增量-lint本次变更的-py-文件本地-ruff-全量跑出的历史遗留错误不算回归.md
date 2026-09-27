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
---

## Background
发布 v5.12.0 前本地 `ruff check .` 全量跑报 33 错 + 58 文件待重排，数量异常，一度以为有严重问题。

## Root cause
CI（`.github/workflows/ci.yml`）只检查本次变更的 py 文件（增量 lint），历史遗留的 F841/格式问题不在范围内；本地全量跑范围更严，混入了历史债。

## 正确做法
本地 lint 数量异常时先核对 CI 的实际检查范围，区分「本次改动引入」与「历史遗留」。只修本次改动造成的错误（本会话：prompts.py 三处 F841），历史遗留留待专门清理，不要被全量结果带偏。

## Rationale
增量 lint 是常见 CI 配置，全量本地 lint 结果不能直接等同于回归判定。
