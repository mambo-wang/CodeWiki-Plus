---
type: lesson
title: 生成的 wiki 页面 status 为 draft 的根因排查：prompt 模板示例会误导 LLM
tags:
- codewiki
- lesson
metadata:
  date: 2026-08-15
  related_modules:
  - doc_writer
  source_ref: raw\conv-D-repos-go-my-harness-repowiki-wiki-modules-生成的wiki还是draft状态.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 08:58:00+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审未采纳
---

## 背景

用户询问 go-my-harness 生成的 wiki 为何还是 draft 状态。

## 排查思路

1. 先确认文件实际 frontmatter（overview.md 第10行 status: draft）
2. 梳理 CodeWiki 三条 status 写入路径：doc_writer 默认 stable；frontmatter.py / ingest_note 默认 draft；prompt 模板示例 draft
3. 对比发现生成走的是 LLM 依据 prompt 模板写 frontmatter 的路径，而非 doc_writer 的默认注入

## 正确做法

- 治本：改 prompt_overview_repo.txt 第64行示例为 status: stable（或第46行说明强调 code-generated pages must be stable），重新生成
- draft 是合法词汇，lint 不会报错；改 stable 后与"代码生成页应为 stable"的约定才一致

## 坑点

read 工具对含 NUL 字节（\x00）的文件判定为 binary 无法读取，但文件实际有内容——这可能是 _inject_symbol_links 占位符残留导致，与 status 无关。
