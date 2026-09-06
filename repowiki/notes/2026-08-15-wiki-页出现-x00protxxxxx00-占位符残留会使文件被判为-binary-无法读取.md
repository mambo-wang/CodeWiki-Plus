---
type: pitfall
title: wiki 页出现 \x00PROTxxxx\x00 占位符残留会使文件被判为 binary 无法读取
tags:
- pitfall
- powershell
- readallbytes
metadata:
  date: 2026-08-15
  related_modules:
  - doc_writer
  - knowledge_loop
  source_ref: raw\conv-D-repos-go-my-harness-repowiki-wiki-modules-生成的wiki还是draft状态.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 08:58:01+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审未采纳
author: mambo-wang
---

## 背景

go-my-harness 生成的 7 个模块 wiki 文件被 read_file/search_content 判定为 binary 无法读取，但文件实际有 6-12KB 内容。

## 根因

文件中含成对出现的 NUL 字节（\x00），呈 `### \x00PROT0019\x00 — 接入契约` 模式。这是 _inject_symbol_links（doc_writer.py 1164-1178、1432-1449）的占位符 _PLACEHOLDER = "\x00PROT{:04d}\x00"（knowledge_loop.py 第210行）——保护标题/代码块区域时插入，恢复环节失败留下的残留。

## 判断方法

- 文件含 NUL 字节（\x00）→ 文本工具判定为 binary
- ripgrep 对含 NUL 的文件直接跳过（这是之前搜索 PROT 得到 0 匹配的原因）
- 用 PowerShell ReadAllBytes 统计 nulls 数量可确认

## 恢复

删除文件中的 \x00 字符即可恢复可读文本。当前 develop 分支代码已修复（提交 420acee），go-my-harness 用的是旧版 codewiki/5.2.0。
