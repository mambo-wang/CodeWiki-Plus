---
type: pitfall
title: 'unsupported_claims 只扫带 (confidence: x.xx) 的规则行且只做格式邻近性检查，不校验语义支撑'
tags:
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - wiki_lint
  severity: medium
  source_ref: conversations/conv-基于本仓库代码逐层说明「准确性-可信度」是怎么保证的。-##-核心立场-工具做确定性簿记，推理决策永远在调用方与用户手里.md
  scene: 知识可信度
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:32:17+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:43Z'
---

## Background

文档常把 `unsupported_claims` 描述成「无代码证据断言占比告警」，实际能力边界更窄。源码核验（`codewiki/mcp/tools/wiki_lint.py:925-1001`）：

## 实际行为（2026-09 核验）

- `_CONFIDENCE_RE`（wiki_lint.py:925）只匹配带 `(confidence: x.xx)` 的行；**没标置信度的断言完全不被检查**，等于可绕过。
- 对命中的行只检查「后续 2 行内有 `> Evidence:` 行」的**格式邻近性**，并不校验所引代码是否真实支撑断言。
- 阈值：无代码证据断言占比 >30%（0.3）告警。

## 结论

「有 Evidence 行」≠「引用真实支撑断言」。断言语义真假由证据协议约束（防线 2）+ 人工确认闸门把关（防线 5），机器不做语义裁判。引用此检查作为质量保证时需说明其能力边界。
