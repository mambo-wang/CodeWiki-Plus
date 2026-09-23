---
type: lesson
title: 模拟 SessionEnd 验证会触发真实采集副作用：telemetry 写入、自动 commit 与自动 push
tags:
- lesson
- sessionend
metadata:
  date: 2026-09-18
  confidence_level: weak
  source_session: 7245f28d19714f71bca1abdd87568f23
  related_modules:
  - team-memory-fusion
  - hooks
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me.md
  scene: hook 接线验证
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-18 01:00:04+00:00
stale_after: '2027-03-17'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-18T01:46:21Z'
source_conversations: ['conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区.md']

---

## 背景

用模拟 SessionEnd 事件（伪造 transcript_path 指向测试 JSON）验证采集 hook 时，走的是完整 capture 链路：写 `repowiki/.meta/telemetry/*.jsonl`、触发 `capture_conversation` 的自动 commit（如 `codewiki: auto-sync knowledge`），并**自动 push 到远端**——把仓库里原本未推送的其他提交（本次为 teammate 的 `5a385b8`）一并推了上去。

## 正确做法

在共享远端的仓库做模拟采集验证前，先知晓此副作用：
1. 验证前检查 `git status` / 未推送提交，评估是否可接受被顺带推送；
2. 验证后清理测试产物（删除测试 conv-*.md、复原 `repowiki/raw/.index.json`）；
3. 如需回退已推送的 auto-sync 提交，须用户显式授权（涉及 force-push），不要擅自改写 git 历史。

## 根因

capture 作为批边界自动 commit+push 是既定行为，模拟事件与真实事件走同一链路，无法只验证落盘而不触发同步。

## install-hooks 验证产物 conv-测试.md 需按 source_session 核对后再清理

> 合并自蒸馏候选：install-hooks 验证产物 conv-测试.md 需按 source_session 核对后再清理

## Background

用模拟事件验证 SessionEnd hook 时，落盘文件名是 `conv-测试.md`（取自 transcript 内容）而非 `conv-verify-1.md`，直接按文件名删测试产物有误删历史 raw 的风险。

## 正确做法

清理前先读文件 frontmatter，确认 `source_session: verify-1`（本次测试标识）再删除；同时核对 raw 目录中历史积压文件未受影响。

## Rationale

采集脚本的文件名来自对话内容而非 session_id，按名字猜测试产物不可靠，按 frontmatter 的 source_session 核对是确定性判据。
