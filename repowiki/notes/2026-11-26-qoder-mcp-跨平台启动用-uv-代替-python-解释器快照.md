---
type: decision
title: "Qoder MCP 跨平台启动用 uv 代替 Python 解释器快照"
tags: ["decision"]
aliases: ["uv MCP", "跨平台 MCP", "Windows macOS MCP"]
metadata:
  date: 2026-11-26
  confidence_level: weak
  related_modules: ["cli", "mcp"]
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.7, at: 2026-11-25T20:22:58Z }
stale_after: 2027-11-26
---

## 背景

项目级 MCP JSON 无法表达 python3 || python 条件回退；写死 python 或 python3 会让 Windows/macOS 之一启动失败，写绝对解释器路径又无法随仓库迁移。

## 决策

本仓 Qoder 的 codewiki MCP 使用 command=uv，args 为 run --no-sync --no-config --project . python -m codewiki.mcp.server，cwd 使用 workspaceRoot。由 uv 在各平台定位项目 .venv，启动时不同步依赖，也不读取机器级 uv 配置。

## 原因与边界

uv 已在本仓开发流程和 uv.lock 中使用，能消除平台解释器差异并避免误用全局 Python。前提是两端安装 uv、Qoder PATH 可见 uv，且已执行 uv sync --frozen 创建 .venv；未安装 uv 的普通 pip 用户仍应保留按平台生成 python/python3 的默认方案。
