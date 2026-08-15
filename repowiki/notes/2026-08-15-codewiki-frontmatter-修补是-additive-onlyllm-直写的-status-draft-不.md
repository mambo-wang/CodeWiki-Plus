---
type: architecture
title: 'CodeWiki frontmatter 修补是 additive-only：LLM 直写的 status: draft 不会被默认 stable
  覆盖'
tags:
- architecture
- codewiki
metadata:
  date: 2026-08-15
  related_modules:
  - doc_writer
  - frontmatter
  source_ref: raw\conv-D-repos-go-my-harness-repowiki-wiki-modules-生成的wiki还是draft状态.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 08:57:59+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审未采纳
---

## 背景

go-my-harness 生成的 wiki overview 显示 status: draft，与 doc_writer 代码默认 status: stable 矛盾。

## 根因

1. LLM 生成正文时直接照抄了 prompt 模板（prompt_overview_repo.txt）里的示例 frontmatter `status: draft`
2. CodeWiki 的修补机制 _patch_existing_frontmatter 是 additive-only：已有键绝不覆盖或重排（doc_writer.py 334-359），所以默认 stable 只在键缺失时生效

## 关键事实

- doc_writer.py 三处默认 status 均为 'stable'（_okf_patch_defaults 第315行、_build_okf_frontmatter 第562行、_inject_lightweight_frontmatter 第988行）
- frontmatter.py::inject_okf_frontmatter 默认 status="draft"（第104行），用于 notes/distill 路径
- 要改已有页面的 status：用 edit_doc_file + str_replace 直接编辑原始文本可绕过 patch 逻辑（替换后 status 已是 stable，后续 patch 不会有动作）
