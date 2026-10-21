---
type: lesson
title: setup 生成的 .mcp.json 口径：解释器只能按平台快照（JSON 配置无法表达 || 回退），新增静态技能后必须重跑 sync-skills
  补齐入库快照
tags:
- lesson
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: c7be4d61-c767-47c8-aea8-e3d0fffba546
  related_modules:
  - cli
  severity: medium
  source_ref: conversations/conv-command-message-open-code-review-delegate-command-message-co.md
  scene: 产品维护：setup/sync-skills 命令维护
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:23:27+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:10Z'
---

## Background

2026-10-21 代码评审（open-code-review-delegate）发现并修复了 setup/sync-skills 的 5 个问题（commit 584f38a）。其中两点是可复用的设计约束：

## 约束一：MCP 配置的解释器只能按平台快照

hook 命令可以写 `python3 ... || python ...` 跨平台回退（bash 语义宿主），但 `.mcp.json` 是 JSON 配置，**无法表达 `||` 回退**——所以 setup 生成的 server 配置只能按安装机平台快照：Windows 写 `python`、mac/Linux 写 `python3`（`codewiki/cli/commands/setup.py` 的 `_build_server_config`，与 TRAE hook 命令同口径）。代价是项目级 `.mcp.json` 若被提交，跨平台队友拿到的解释器名可能不匹配——这是 JSON 配置表达力的固有限制，不是 bug。

## 约束二：新增静态技能后必须重跑 sync-skills

`codewiki/assets/skills/` 下的静态技能（如 `codewiki-setup`）通过 sync-skills 编译分发到 `.qoder/.codebuddy/.trae` 三套宿主目录，且这些快照**入库跟踪**。往 assets 加新技能后若不重跑 `codewiki sync-skills`，入库快照就缺项（本次评审发现快照 23 项 vs 实际 24 项）。验证口径：`sync-skills --dry-run` 输出的 Skills 数与入库目录数对照。

## 附带修复事实（commit 584f38a）

- setup 的 timeout 必须与 README 手工配置口径一致（36000000，防长任务被宿主掐断）；
- setup/sync-skills 入口统一校验 `repo.is_dir()`，拼错路径不再凭空建树（UsageError exit 2）；
- prune 跳过符号链接目录（`not entry.is_symlink()`），避免 POSIX 上 rmtree 抛错中断同步；Windows 无 symlink 权限时相关测试 skip 属预期。
