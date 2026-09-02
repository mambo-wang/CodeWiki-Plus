---
type: lesson
title: 修复顺序类 bug 先看数据流时序：fix 块后置导致 broken_links 基于旧索引计算
tags:
- lesson
metadata:
  date: 2026-08-24
  related_modules:
  - wiki_lint
  - wiki_lint fix=true 修复
  severity: medium
  source_ref: conversations/conv-修复-fix=true-后-broken_links-残留的问题.md
  consolidated_into:
  - wiki/scenarios/Wiki页面生成约定与数据结构.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:16+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:15Z'
reject_reason: 聚合进场景：Wiki页面生成约定与数据结构
author: mambo-wang
---

## 背景

lint_wiki fix=true 自愈上线后，broken_links 仍残留。根因：自愈逻辑在所有检查跑完之后才执行——broken_links 早已基于旧 index 计算完；更微妙的是 dedup 本会把同行号 broken_links 当 stale_refs 重复吞掉，但 fix 先清空 stale_refs 等于解除 dedup 武装，让旧 index 死链以 error 级暴露。

## 正确做法

自愈块移到检查执行之前：fix=true 先预扫 stale_refs → 符合条件先 rebuild_index → 全部检查跑在重建后的索引上，后置 fix 块删除，代码反而更短。

## 根因

修复顺序类 bug 时先看数据流时序（谁先算谁后改），而非只看逻辑正确性；测试断言要先验证「修复前症状可见」再验证「修复后归零」——本例 dedup 掩盖症状导致第一版测试断言不成立。
