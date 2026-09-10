---
type: pitfall
title: PowerShell Remove-Item 被包装器代理：-Exclude 与管道输入均报错，改用 delete_file 或 ForEach-Object
tags:
- childitem
- fileinfo
- foreach
- fullname
- parameterbindingexception
- pitfall
- powershell
metadata:
  date: 2026-09-10
  task_id: 发版本
  related_modules:
  - release
  - env
  severity: medium
  source_ref: conversations/conv-发布版本.md
  scene: 发版本 / 发布前清理
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:44:51+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:10Z'
---

## Background
发布前清 `dist/` 旧产物（5.7.0/5.8.0）时，`Remove-Item dist/* -Exclude .gitignore -Force` 与 `Get-ChildItem dist | Remove-Item -Force` 两种方式都失败，导致清理步骤卡住。

## 正确做法
本机 PowerShell 的 `Remove-Item` 被一层包装器代理，正确做法二选一：
- 用 `delete_file` 工具逐个删除（最稳）；
- 或 `Get-ChildItem dist -File | ForEach-Object { Remove-Item $_.FullName -Force }`（显式传 FullName，不走管道绑定）。

## Root cause
包装器对 `Remove-Item` 做了代理拦截：① `-Exclude` 直接抛 `unsupported option`；② 管道传入 `FileInfo` 对象抛 `ParameterBindingException`（「无法将输入对象绑定到命令的任何参数」）。即管道输入 + `-Exclude` 两种写法都被包装器拒绝，并非 PowerShell 原生行为。

## 适用范围
任何需要在本仓库环境清理/删除文件的脚本。属环境级坑，与具体业务逻辑无关；`wiki/scenarios/发布与依赖治理方法.md` 的 SOP 清理前置步骤会踩到。
