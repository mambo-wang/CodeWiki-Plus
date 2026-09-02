---
type: pitfall
title: "resolve_session 恢复的 session.output_dir 会覆盖 repo_path 推断，导致 Note not found"
tags: ["pitfall"]
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

蒸馏后调用 reject_note/confirm_note 报 Note not found，但笔记文件确实存在于 repowiki/notes/。

## 根因

resolve_session 在只传 repo_path 时调用 store.find_or_restore(rp) 并返回一个 session 对象（非 None）。handle_reject_note/handle_confirm_note 的解析逻辑中 elif session: 分支优先级高于 repo_path 推断，于是用了 session 缓存的 output_dir（可能是 server 进程之前 analyze 缓存的过期目录），拼出的路径找不到笔记。repo_path 推断分支沦为死代码。

## 正确做法

output_dir 解析顺序应为：显式 output_dir → repo_path 推断（repo_path/repowiki）→ session 缓存 → 报错。该顺序已修复到 handle_confirm_note/handle_reject_note。
