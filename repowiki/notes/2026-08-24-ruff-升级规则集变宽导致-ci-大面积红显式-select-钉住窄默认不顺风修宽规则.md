---
type: decision
title: ruff 升级规则集变宽导致 CI 大面积红：显式 select 钉住窄默认，不顺风修宽规则
tags:
- decision
metadata:
  date: 2026-08-24
  related_modules:
  - pyproject
  - OpenViking借鉴全景路线图
  severity: high
  source_ref: conversations/conv-合并分支到-develop.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:26+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:16Z'
reject_reason: 聚合进场景：发布与依赖治理方法
author: mambo-wang
---

## 背景

合并分支发版时 CI ruff 事故：uv.lock 锁的 ruff 0.16 默认规则集已扩宽到 UP/BLE/S，存量代码大面积不满足谁碰谁红（doc_writer.py 250+ 告警）。

## 决策

pyproject 显式 select ['E4','E7','E9','F'] 钉住经典窄默认（只抓真错误），不顺风修宽规则——大规模机械化重构会污染 blame 且与并行开发冲突，宽规则将来专门开「lint 收紧」提交一次做完。'Widen deliberately, not by upgrade accident' 写进注释留决策记录。

## 根因

依赖升级悄悄改变工具默认行为，CI 在升级边界爆炸。显式声明规则集把「升级事故」变成「刻意决策」。另注意 bump 提交前须过 ruff format --check（__init__.py 尾空行曾致 CI 红）。
