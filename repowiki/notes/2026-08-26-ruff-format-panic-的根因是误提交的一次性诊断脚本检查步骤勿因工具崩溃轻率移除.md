---
type: pitfall
title: ruff format panic 的根因是误提交的一次性诊断脚本，检查步骤勿因工具崩溃轻率移除
tags:
- '17'
- '18'
- pitfall
aliases:
- ruff format check 移除
- formatter crash
- 一次性诊断脚本勿提交
- scripts/_tmp2.py
metadata:
  date: 2026-08-26
  related_modules:
  - MCP_Core
  severity: medium
  root_cause: 'ruff 0.16.3 formatter 对特定文件 scripts/_tmp2.py（99e4c44 误提交的一次性诊断脚本）panic；叠加全仓
    206 文件 format 存量漂移，迫使 PR #17 移除 CI format 检查步骤'
status: stable
generated:
  by: codewiki/5.4.4
  at: 2026-08-26 13:57:29+00:00
stale_after: '2027-02-22'
verified:
- by: human:mambo-wang
  at: '2026-08-26T13:58:01Z'
---

## 背景

2026-08-25 起 develop 连续 9 次 CI 失败，Lint job 挂在 `ruff format --check`（changed files 步骤）。本地复现发现两层原因：① ruff 0.16.3 的 formatter 在全仓运行时直接 panic：`Annotation range 0..601 is beyond the end of buffer 599`（ruff_annotate_snippets source_map.rs:185）；② 全仓 206/456 个 Python 文件存在 format 漂移。PR #17（外部贡献者）为恢复 CI 绿，删除了 ci.yml 中的 `Ruff format check changed files` 步骤。

## 根因

panic 的元凶是 `scripts/_tmp2.py`——99e4c44 误提交进仓库的一次性诊断脚本（检查已删 notes 是否有归档）。删除该文件后 formatter 立即恢复正常（已在 5dee7f5 前的 7f55271 修复并实测验证）。format 漂移则是长期存量，与 panic 无关。

## 教训

- 格式器/工具链崩溃时，先按文件二分定位元凶文件，不要急着移除检查步骤——panic 往往只是某个特定文件触发。
- 一次性诊断脚本勿提交进仓库；`scripts/` 目录也不该成为临时脚本的藏身处。
- 移除 CI 检查步骤应是最后手段，且必须有恢复记账。

## 遗留 TODO（恢复 format 检查的前置条件）

本仓库 GitHub Issues 功能已关闭（API 410），TODO 记于此：
1. 全仓一次性 `uv run ruff format .`（单独一笔机械提交，勿混语义改动）
2. 把 ci.yml 中被 #17 删除的 format 检查步骤加回（代码见 #17 diff）
3. 可选：dev 依赖里钉住 ruff 版本，避免 formatter 行为跨小版本漂移

相关：PR #17（放宽 lint + 修 CI flakes）、PR #18（收窄 E741/E731 + 清 F401）。
