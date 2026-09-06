---
type: architecture
title: codewiki-plus 发布是手动流程：三处版本引用 + lightweight tag + CI 不发布
tags:
- architecture
- github
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-发布新的pypi版本，并发布git-release.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:30:08+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:33Z'
---

## 事实

codewiki-plus 的 PyPI/GitHub Release 发布是**手动流程**，仓库无发布脚本/文档，CI 仅做测试与 lint（PyPI 发布不自动）。

## 关键点

- 版本引用点共三处，需同步：`pyproject.toml`、`codewiki/__init__.py`、`uv.lock`（tests/ 与 repowiki/ 内为 fixture/历史数据，不动）。
- 版本 bump 提交模式：`chore: bump version to X`（历史约定，同时改 `__init__.py` + `pyproject.toml`）。
- tag 为 **lightweight**（历史保持一致），格式 `vX.Y.Z`。
- 语义化版本判定：vX.Y 之后含大量 `feat`/`refactor` → minor bump（实例：5.5.1→5.6.0，56 个提交）。
- 发布前验证闸门：全量 pytest 通过 + `uv build` 构建产物成功。

## 建议

发布前清理 `dist/` 或精确指定产物文件名，避免误传旧版本残留（见相关 pitfall）。发布后可用 PyPI JSON API 核对真实上传状态。
