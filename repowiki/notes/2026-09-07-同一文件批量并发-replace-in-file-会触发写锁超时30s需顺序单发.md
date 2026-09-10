---
type: pitfall
title: 同一文件批量并发 replace_in_file 会触发写锁超时（30s），需顺序单发
tags:
- pitfall
metadata:
  date: 2026-09-07
  related_modules:
  - mcp
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-.codebuddy-plans-output_dir-收敛为repo_pat.md
  scene: 批量代码编辑
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 02:56:49+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:21Z'
---

## 背景

批量收敛 registry.py 时，一次并行发出多个针对同一文件的 replace_in_file，触发 `Acquire write lock timeout after 30000ms`，部分编辑丢失（3 处成功、2 处失败）。

## 正确做法

对同一文件的多次编辑必须顺序单发，等前一次返回后再发下一次；不同文件可以并行。失败后先核对实际落盘状态再重试，避免重复应用。

## 根因

宿主 IDE 对同一文件的写操作有互斥写锁，并发请求排队超时被丢弃；不同文件锁独立、可安全并行。
