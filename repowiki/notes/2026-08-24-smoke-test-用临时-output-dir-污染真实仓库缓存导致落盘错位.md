---
type: pitfall
title: smoke test 用临时 output_dir 污染真实仓库缓存导致落盘错位
tags:
- pitfall
aliases:
- smoke test
- 缓存污染
- analysis_cache
- output_dir 落错
metadata:
  date: 2026-08-24
  related_modules:
  - mcp
  severity: medium
  root_cause: AnalysisCache 按 repo_path 持久化 output_dir，smoke test 复用真实仓库路径 + 临时 output_dir
    运行 analyze_repo，把临时路径写进仓库缓存；find_or_restore 恢复 session 时优先采用该缓存值。
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 13:55:48+00:00
stale_after: '2027-02-20'
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T13:55:52Z'
reject_reason: 聚合进场景：MCP-Server薄壳架构与参数约定
---

## 背景

`tests/smoke_test_mcp.py` 用**真实仓库路径**（`REPO_PATH`）+ `tempfile.mkdtemp` 的**临时 output_dir** 调用 `handle_analyze_repo`。`analyze_repo` 会把 output_dir 持久化到仓库的 `.codewiki/analysis_cache.db` 的 `repo_meta.output_dir`。

## 现象

smoke test 运行后，仓库缓存残留临时目录路径。此后所有经 `find_or_restore` 从缓存恢复 session 的 MCP 工具（`ingest_note`、`query_wiki` 等）都把知识库操作落盘到 `Temp\codewiki_smoke_*` 而非仓库的 `repowiki/`——2026-08-24 实际踩中：`ingest_note` 返回的 `note_path` 指向临时目录。

## 正确做法

1. **smoke test 隔离**：analyze 用隔离的仓库副本（临时 clone / git worktree），避免写真实仓库缓存。
2. **已污染时修复**：更新 `repo_meta.output_dir` 为正确路径（SQLite 直接 UPDATE），再 `close_session(force=true)` 重置内存 session；或调用工具时**显式传 `output_dir`** 绕过 session 解析（`handle_ingest_note` 优先用参数中的 output_dir）。

## 根因

`AnalysisCache` 按 repo_path 键控缓存 output_dir，不区分调用方（smoke test vs 真实使用）；`find_or_restore` 恢复 session 时优先采用缓存记录的 output_dir（设计上 honor 自定义 output_dir），缓存被污染后所有落盘随之错位。
