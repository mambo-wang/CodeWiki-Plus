---
type: pitfall
title: wiki_lint 需豁免 raw/ 根暂存层但保留 raw/sources/，RAW_DIR 须单独处理不可塞进 _scratch_dirs
tags:
- pitfall
metadata:
  date: 2026-08-15
  related_modules:
  - codewiki/mcp/tools/wiki_lint.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:37+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
author: mambo-wang
---

## 背景

_check_okf_conformance 扫描 repowiki 时，raw/ 根目录下的 conv-*.md（capture_conversation 的采集暂存文件，带 captured_at/content_hash/keep_raw/status: pending 专有 schema）被 OKF lint 报了 8 个 warning。这些文件设计上不该走 OKF（raw/ 是暂存区，不进 query_wiki 检索）。

## 正确做法

- raw/ 根目录下的采集暂存层应被 lint 跳过，但 raw/sources/（真实源文档层）仍需审计。
- 实现上不能简单把 RAW_DIR 塞进 _scratch_dirs 集合：_check_okf_conformance 用 `any(_part in _scratch_dirs ...)` 判断目录内任意层级命中即跳过，把 raw 塞进去会让 raw/sources/ 也被第二个 any() 误拦。
- 正确做法是单独处理：`if RAW_DIR in parts and "sources" not in parts: continue`，并保持 RAW_DIR 不在 _scratch_dirs 中。

## 根因

跳过逻辑只按『路径任意片段命中』判断，没有区分 raw/ 根层与 raw/sources/ 子层，把整个 raw 当作 scratch 会误伤需要审计的 sources。
