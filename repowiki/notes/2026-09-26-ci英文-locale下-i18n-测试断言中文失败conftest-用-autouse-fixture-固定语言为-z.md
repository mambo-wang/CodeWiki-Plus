---
type: pitfall
title: CI（英文 locale）下 i18n 测试断言中文失败：conftest 用 autouse fixture 固定语言为 zh
tags:
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 0bf7597a49a6454d97c6523997109749
  related_modules:
  - MCP_Server
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5af19e.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:21:06+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:17Z'
---

## Background
发布 v5.11.0 时 CI 上 2 个测试失败：`test_team_layout.py` 与 `test_openviking_borrowings.py`，均为 i18n locale 问题。

## Root cause
i18n 按 OS locale 回退（`zh*`→zh，其他→en）。本地 Windows 是中文 locale 全绿，CI 是英文 locale，代码输出英文文案、测试断言中文，导致失败。

## 正确做法
在 `tests/conftest.py` 加 autouse fixture（如 `_pin_language_zk`）固定为 `zh`，并本地双向验证（`CODEWIKI_LANG=en` / `LANG=en_US.UTF-8` / `LC_ALL=en_US.UTF-8` 下也通过）。

## Rationale
任何依赖 OS locale 的 i18n 测试都必须显式固定语言，否则 CI/本地环境差异必然翻车。
