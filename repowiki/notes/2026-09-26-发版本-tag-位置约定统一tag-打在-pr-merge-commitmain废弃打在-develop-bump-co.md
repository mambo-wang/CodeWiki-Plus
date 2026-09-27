---
type: decision
title: 发版本 tag 位置约定统一：tag 打在 PR merge commit（main），废弃打在 develop bump commit 的旧做法
tags:
- decision
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 4a12044311f84fd3a7ddcecc96abdd33
  related_modules:
  - release
  - git
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-7.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:40:24+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:04Z'
---

## 背景

此前发版本把 tag 打在 develop 分支的 bump commit 上（v5.12.0 = 34583d7），导致 tag 不在 main 主干、分支语义混乱。

## 决策

统一新约定：**tag 打在 PR merge commit（main 主干上）**。v5.13.0 的 tag（3e97d30）即打在 develop→main 的 merge commit 上；废弃「tag 打在 develop bump commit」的旧做法。

## 落实

约定已回写进 `windows-python-release` skill 的 revision 3，后续发版本照此执行：bump → 测试 → 构建 → 发布 PyPI → develop→main PR → 在 main 的 merge commit 上打 tag → 发 Release。
