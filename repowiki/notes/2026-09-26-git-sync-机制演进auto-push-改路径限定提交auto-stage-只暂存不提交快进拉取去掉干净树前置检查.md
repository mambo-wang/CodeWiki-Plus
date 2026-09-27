---
type: architecture
title: git_sync 机制演进：auto_push 改路径限定提交、auto_stage 只暂存不提交、快进拉取去掉干净树前置检查
tags:
- architecture
- codewiki
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 5c6a2dbd8f4c40609aee7afa8a4426ee
  related_modules:
  - git_sync
  - store
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5-9aa0b9.md
  scene: 文章代码核对（git 同步机制演进）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:30:24+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:57:56Z'
---

## 背景

2026-09-21 核对《CodeWiki-Plus系列10》文章第六节与当前代码时，发现 git_sync 自动同步机制自文章成稿后经历三处演进，文章描述已过时。

## 演进事实

1. **auto_push 改路径限定提交（2026-09-20，commit `d021891`）**：原「预暂存守卫」在暂存区有别人（非我方）内容时直接放弃推送；现改为 pathspec 只圈知识子树做路径限定提交，只提交本次知识变更，不再整体放弃推送。
2. **新增 auto_stage（2026-09-09，commit `f2aa34d`）**：默认开启，只暂存不提交；与 auto_push 配合形成「auto_stage 落暂存 + auto_push 按知识子树提交推送」的两段式自动同步。
3. **快进拉取去掉干净树前置检查（2026-09-08，commit `1f15389`）**：原先要求工作树干净才拉取；现改为直接依赖 git 自身的覆盖保护来裁决（脏工作树遇覆盖冲突由 git 拒绝），去掉了前置检查。

## Rationale

写文章/文档时若引用 git_sync 的自动同步行为，需以 git_sync.py 当前实现与上述 commit 为准，避免沿用旧的「整体放弃推送」「暂存即提交」等过时语义。
