---
type: pitfall
title: uv sync --frozen 会剪掉手工 uv pip install 的包
tags:
- pitfall
metadata:
  date: 2026-10-30
  confidence_level: weak
  source_session: 164a77b4-96c0-4d21-aab3-fe43fc1f2401
  severity: medium
  source_ref: conversations/conv-system-reminder-The-user-selected-the-following-plugins-that-acc1a2.md
  scene: Windows/uv 环境维护
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.6
  at: 2026-10-30 09:33:49+00:00
stale_after: '2027-04-29'
origin: conversation
verified:
- by: codewiki/5.16.6
  at: '2026-10-31T01:16:54Z'
---

## 症状

本机 venv 里手工 `uv pip install` 装过的开发期工具（twine、readme-renderer、requests-toolbelt、rfc3986 等）在某次 `uv sync --frozen` 之后全部消失，发版时 twine 找不到。

## 机制

`uv sync --frozen` 按**锁文件**收敛环境：锁文件里没有的包一律剔除，不区分「手工装的」还是「残留的」。它不是增量安装，是全量对齐。

## 正确做法

- 开发期工具要么进 `pyproject.toml` 的 `dependency-groups`（dev 组），要么接受「每次 frozen 后重装」的现实。
- 排查这类「工具莫名消失」问题时，先想最近是否跑过 `uv sync --frozen`。
- 本仓实例：发 PyPI 版本时手工装的 twine 被 frozen 剪掉，需 `uv pip install twine` 恢复。
