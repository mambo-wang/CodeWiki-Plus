---
type: pitfall
title: MCP 工具参数长度限制导致 review_changes submit 大报告反复失败：精简 evidence 或用文件侧通道
tags:
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 2364d2066b2946459fd01a6779ff9159
  related_modules:
  - review_changes
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-3-e09bcd.md
  scene: ADR-0016 实施后自评审提交报告
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:35:51+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:02Z'
---

## 背景

用 `review_changes(mode="submit")` 提交完整评审报告时，MCP 参数传递持续失败。先怀疑特殊字符/JSON 转义，逐条排查后确认是参数长度限制。

## 正确做法

1. 先以最小参数验证工具可用性，区分「工具坏了」与「参数超限」。
2. 精简 evidence 文本（缩短摘要）后重提。
3. 大载荷走文件侧通道：把报告写成 JSON 文件（如 review_report_draft.json），用 node 脚本读文件构造 submit 参数，避免命令行/MCP 参数转义与长度问题。
4. 失败时逐条排查：JSON 本身没问题不等于缺字段——曾因缺 `title` 字段持续失败，补上即成功。

## Rationale

MCP 参数有长度上限，且错误表象可能混淆（长度超限 vs 缺字段 vs 特殊字符）；最小验证 + 文件侧通道 + 逐字段排查是确定性解法。
