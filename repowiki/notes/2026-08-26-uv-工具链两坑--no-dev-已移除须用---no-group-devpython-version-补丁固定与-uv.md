---
type: pitfall
title: uv 工具链两坑：--no-dev 已移除须用 --no-group dev；.python-version 补丁固定与 uv Docker 镜像内置
  Python 漂移
tags:
- '16'
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - docker
  severity: medium
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 16:38:46+00:00
stale_after: 2027-02-22
---

## 背景

PR #16 中 `docker/DOCKER_README.md` 仍写 `uv sync --frozen --no-dev`，而 Dockerfile 实际使用 `uv sync --frozen --no-group dev`；`.python-version` 钉死 `3.12.13`，Docker 基础镜像 `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` 内置的 Python 补丁版本随上游更新。

## 正确做法

- uv ≥ 0.30 须用 `--no-group dev`（`--no-dev` 已于 0.30 改名、此后移除，照抄旧文档会直接报错失败）；文档中的 uv 命令应与代码一致，评审时逐条核对。
- Docker 构建使用 `.python-version` 补丁固定时，需确认基础镜像内置 Python 与之一致；不一致时 `uv sync` 会额外下载一份 Python——构建变慢、镜像变大，且固定补丁版本后 3.12 的安全补丁不会自动跟进，需人工维护升级（可复现性与安全性/构建体积的权衡）。

## 根因

文档未跟上 uv CLI 改名节奏；"固定补丁版本"与"依赖镜像内置 Python"是两种天然冲突的策略，混用时 uv 会静默多下载一个解释器。

## 适用范围

任何使用 uv 的 Docker 构建或 uv CLI 文档；README/DOCKER_README 与 CI/Dockerfile 的 uv 命令一致性检查。
