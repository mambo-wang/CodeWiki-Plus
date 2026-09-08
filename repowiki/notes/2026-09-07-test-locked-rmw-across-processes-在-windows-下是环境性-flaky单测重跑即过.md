---
type: pitfall
title: test_locked_rmw_across_processes 在 Windows 下是环境性 flaky：单测重跑即过，勿当回归处理
tags:
- permissionerror
- pitfall
metadata:
  date: 2026-09-07
  task_id: 发版本
  related_modules:
  - store
  - tests
  severity: medium
  source_ref: conversations/conv-发布新版本.md
  scene: v5.7.0 发布闸门
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 02:59:50+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:19Z'
---

## 背景

v5.7.0 发布闸门跑全量 pytest 时，`tests/test_phase2_concurrency.py::test_locked_rmw_across_processes` 失败：两个真实子进程并发写同一文件时子进程创建 `counter.txt.lck` 报 PermissionError + GBK 解码噪音。

## 判定与处理

单独重跑即通过；`codewiki/src/store.py` / `locks.py` 在本次发布范围（v5.6.1..v5.7.0 的 21 个提交）内无改动 → 环境性 flaky（Windows 多进程文件锁时序），非回归。

## 适用范围

发布/回归闸门遇此测试失败时：先单独重跑 + `git log <范围> -- codewiki/src/store.py` 确认锁模块是否被改动，再下结论。
