---
type: lesson
title: 文件名相似度判据在 raw 上 100% 误报：同会话 supersede 重复捕获与模板前缀是两大污染源
tags:
- lesson
metadata:
  date: 2026-09-07
  related_modules:
  - skill-creator
  - capture
  severity: medium
  source_ref: conversations/conv-SKILL-CREATOR需求的PHASE-2是不是还没启动.md
  scene: skill_candidate hint 判据验证
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:01:23+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:22Z'
---

## 背景

为验证「重复任务可感知→提示编译技能」的判据（A 层：用户指令文本相似度），2026-09-06 对 `repowiki/raw/` 21 个文件名（即首条指令 slug）做只读扫描：相似度 ≥0.55 共 3 对，**全部是误报，有效信号 0**。

| 相似度 | 对 | 判定 |
|---|---|---|
| 0.98 | `...Initial-task-as` ↔ `...Initial-task-as-2` | 同一会话被 supersede 重复捕获 |
| 0.98 | `...收敛为repo_pat` ↔ `...收敛为repo_pat-2` | 同上 |
| 0.66 | `user_command-...外部文档知识抽取` ↔ `user_command-...知识库搜索` | 仅共享模板前缀 `conv-user_command-commands-codewiki-`，语义不相干 |

## 两条必备清洗规则

1. **同会话去重**：按 `source_session_id` 归并，同一会话多次捕获只算一次（`-2` 后缀即 supersede 证据）。
2. **去模板前缀**：比对前剥掉 `conv-` / `user_command-commands-codewiki-` / 路径片段等公共模板，否则同类命令被前缀绑架成「相似」。

## 方法论

判据上线前先用只读离线扫描在真实语料上验证（Q18 先验证后接线），本例中判据零代码即被证伪出两个致命缺陷——这一步最多一小时，却能在写代码前回答「判据到底准不准」。
