---
type: decision
title: 单次 commit 业务 review 工具选型：mattpocock code-review 走 Spec 轴，需求来源可绕 setup
tags:
- decision
- openspec
metadata:
  date: 2026-08-24
  related_modules:
  - 业务级 commit review 工具选型
  severity: medium
  source_ref: conversations/conv-哪些工具可以针对某次-commit-做业务-review-而不是编码规范的-review.md
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:32+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:16Z'
reject_reason: 聚合进场景：发布与依赖治理方法
---

## 背景

需要针对某次 commit 做业务 review（查需求是否实现），而非编码规范 review。

## 对比结论

mattpocock code-review 的 Spec 轴=diff 级、接受任意需求文档、查缺失/超范围/实现偏离；OpenSpec /opsx:verify=change 级验收（不看 git diff），要求 openspec init 结构化需求，查完整性/正确性/一致性，不查 scope creep。针对单次 commit 的业务 review 选前者；已用 OpenSpec 管需求的仓库选后者。

## 实操要点

code-review 与 mattpocock 生态唯一接触点是「找需求来源」，四来源按优先级：issue 引用（需 gh CLI/配置）→ 手动传路径 → 仓库 docs/specs/.scratch 匹配文件 → 问用户。不走第一条即可绕过 setup。实操：需求来源直接给路径最稳；只要业务 review 说「只跑 Spec 轴跳过 Standards」。
