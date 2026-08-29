---
type: pitfall
title: "生成的 .ps1 必须带 UTF-8 BOM，否则 PowerShell 5.1 按 GBK 误读"
tags: ["pitfall", "powershell"]
aliases: ["ps1 BOM", "utf-8-sig", "GBK 乱码", "PowerShell 编码", "bootstrap.ps1"]
metadata:
  date: 2026-08-29
  related_modules: ["mcp"]
  severity: high
  root_cause: "工具写入 .ps1 时使用无 BOM 的 UTF-8，而 Windows PowerShell 5.1 对无 BOM 的 .ps1 按系统 ANSI（zh-CN 为 GBK）解码。"
status: stable
generated: { by: codewiki/5.4.5, at: 2026-08-29T07:03:14Z }
stale_after: 2027-02-25
---

## 背景

`init_workspace` / `add_workspace_repo` 生成的 `bootstrap.ps1` 含中文，在中文 Windows 上用 PowerShell 5.1 执行时乱码并解析失败；用户手动转为 UTF-8 with BOM 后，工具下次改写登记表又把 BOM 抹掉，问题反复出现。

## 陷阱与根因

- Windows PowerShell 5.1 对**无 BOM** 的 `.ps1` 按系统 ANSI 解码（zh-CN 系统为 GBK），中文注释/字符串变乱码，特定字节还会破坏引号配对导致解析失败。
- 根因：`codewiki/mcp/tools/workspace_bootstrap.py` 的 `_write_text` 曾对所有文件统一用无 BOM 的 UTF-8 写入。
- PowerShell 7+ 默认 UTF-8，不受影响——该问题只在 5.1（Windows 自带）暴露。

## 正确做法（已于 2026-08 修复）

- 写入/改写 `.ps1` 一律用 `utf-8-sig`（带 BOM）；读取用 `utf-8-sig`（剥掉已有 BOM，防止重写时叠加双 BOM）。
- `init_workspace` 重跑时对存量无 BOM 文件做字节级自愈（`_ensure_ps1_bom`，只加 BOM、内容逐位不变）。
- 相反，`.sh` **必须无 BOM**——BOM 会破坏 shebang（`#!/usr/bin/env bash`）。

## 适用范围

任何为 Windows 用户生成含非 ASCII 内容的 `.ps1`/`.bat` 脚本的工具代码；评审此类写入逻辑时检查编码选择。
