---
type: pitfall
title: _read_versioned_lines 对磁盘上已不存在的 untracked 文件返回空列表，产生只有 header 的空 body
tags:
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - review_changes
  source_ref: conversations/conv-user_command-commands-codewiki-变更评估与代码评审（修改后）-请对最近代码变更做影响范围评-2.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 17:03:03+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-08-25T17:03:49Z'
---

## 背景

review_changes._build_changed_sources 对 untracked 文件走 _read_versioned_lines 的 working-tree 分支（Path.read_text），若文件在磁盘上已不存在则返回 []，产出只有 (untracked new file) header 的空 body。

## 正确做法

出现概率极低，但建议加一行防护：`if not all_lines: continue` 跳过空文件，避免评审上下文出现空 body 噪音。

## 根因

untracked 文件无版本库历史，只能读工作区；工作区文件被删时读不到内容，且没有对空结果做短路。
