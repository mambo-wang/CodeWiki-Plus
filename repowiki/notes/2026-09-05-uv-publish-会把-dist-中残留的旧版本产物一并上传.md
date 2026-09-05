---
type: pitfall
title: uv publish 会把 dist/ 中残留的旧版本产物一并上传
tags:
- pitfall
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-发布新的pypi版本，并发布git-release.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:30:35+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:45Z'
---

## Background

2026-09-04 发布 codewiki-plus 5.6.0 时，`dist/` 目录残留 5.4.5/5.5.0/5.5.1 共 6 个旧构建产物，`uv publish` 把它们全部尝试上传。

## 现象与结论

- PyPI 只增不改：同文件名已存在会**幂等跳过**（HTTP 层面拒绝/无副作用），经 PyPI JSON API 核实旧版本文件均为 8 月历史上传、5.6.0 是唯一新发布版本——未造成污染，但不可依赖此侥幸。
- 正确做法：发布前清理 `dist/`，或 `uv publish dist/codewiki_plus-<version>*` 精确指定文件。

## Root cause

`uv publish` 默认上传 `dist/` 下所有产物，无单版本过滤。
