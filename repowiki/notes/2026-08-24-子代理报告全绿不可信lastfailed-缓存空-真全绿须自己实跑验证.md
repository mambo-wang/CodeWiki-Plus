---
type: lesson
title: 子代理报告「全绿」不可信：lastfailed 缓存空 ≠ 真全绿，须自己实跑验证
tags:
- lesson
metadata:
  date: 2026-08-24
  related_modules:
  - tests
  - teamai-cli-调研与借鉴分析
  severity: high
  source_ref: conversations/conv-研究一下-https-github.com-Tencent-teamai-cli，看下跟CodeWiki的对比和可借鉴之.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:16:04+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:07Z'
reject_reason: 聚合进场景：发布与依赖治理方法
author: mambo-wang
---

## 背景

T2 子代理（telemetry jsonl 迁移）报告测试「全绿」，但其内部 lastfailed 缓存是空的——pytest 的 lastfailed 只记录上次失败的测试，空缓存只代表「还没跑过」，不代表「全通过」。实跑后 35 个测试全部失败。

## 正确做法

接管子代理任务后，必须自己实际运行测试验证，不能信任其「全绿」报告。检查测试代码是否真的迁移到新机制：旧测试数据构造还在种 SQLite 表，而实现已改走 jsonl。

## 根因

子代理的判断基于 lastfailed 缓存空（假证据），而非实际运行结果。凡是「子代理说全绿」都要用真实 pytest 跑一遍复核。
