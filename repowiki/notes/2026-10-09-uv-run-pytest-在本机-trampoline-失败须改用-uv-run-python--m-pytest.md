---
type: pitfall
title: "uv run pytest 在本机 trampoline 失败，须改用 uv run python -m pytest"
tags: ["codewiki", "pitfall", "powershell"]
metadata:
  date: 2026-10-09
  confidence_level: weak
  task_id: 发版本
  source_session: "cc4eb177319d48abbc0c2620e02ec83a"
  related_modules: ["release"]
  severity: medium
  source_ref: "conversations/conv-working_memory_content-The-following-is-the-existing-working-2-b37797.md"
  scene: "Python 包发布闸门"
status: draft
author: Administrator
generated: { by: codewiki/5.14.1, at: 2026-10-09T03:25:33Z }
stale_after: 2027-04-07
origin: conversation

---

## Background
CodeWiki-Plus 发版本（v5.14.0）执行 windows-python-release 技能的 pytest+ruff 闸门时，在 Windows PowerShell 环境下运行 uv run pytest -q，trampoline 失败（无法直接执行 pytest 入口），输出文件无有效测试结果。

## 正确做法
改用模块形式调用：uv run python -m pytest -q（输出用 Out-File -Encoding utf8 落盘后读取）。本次实测通过：1199 passed, 2 skipped。ruff 走 uv run ruff check / uv run ruff format 正常，无需变通。

## Rationale
发布闸门必须跑通全量测试，uv run pytest 直接失败会卡住发布流程；模块形式是经验证可用的稳定替代，避免每次发布重新排查。

## 归属
项目 CodeWiki-Plus（Windows 本机环境）；技能 windows-python-release 八步主干中 pytest+ruff 闸门步骤的执行细节补充。与既有笔记「本仓 Windows/PowerShell 开发环境坑」互补：那条讲 CLIXML 吞输出与 basetemp，本条讲 uv run 入口 trampoline 失败。
