---
type: decision
title: "confirm_note/reject_note 的 output_dir 解析顺序改为 output_dir → repo_path → session"
tags: ["decision"]
status: deprecated
generated: { by: codewiki/5.2.2, at: 2026-08-12T11:59:13Z }
stale_after: 2026-11-10

metadata:
  date: "2026-08-12"
  origin: "conversation"
  related_components: []
  related_modules: ["mcp", "\"\""]
  source_ref: "raw\\conv-user_command-commands-codewiki-蒸馏对话提取经验-把已采集的对话（repowiki-raw.md"
author: mambo-wang
---

## 背景

reject_note 首次调用因 session.output_dir 过期缓存导致路径错、笔记找不到。

## 决策

修改 handle_confirm_note 和 handle_reject_note（codewiki/mcp/tools/knowledge_loop.py）的 output_dir 解析顺序：
1. 显式 output_dir（最高优先）
2. repo_path 推断（repo_path/repowiki）
3. session 缓存（最低优先）
4. 报错

## Rationale

调用方只传 repo_path 即可正确推断 repowiki，无需绕过 session 缓存，符合「根据项目根目录自己推断」的预期。

## 效果

今后调用 reject/confirm_note 传 repo_path 即自动定位，不再受 find_or_restore 缓存影响。
