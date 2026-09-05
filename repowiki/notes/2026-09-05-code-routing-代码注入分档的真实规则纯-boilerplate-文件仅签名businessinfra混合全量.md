---
type: pitfall
title: code_routing 代码注入分档的真实规则：纯 boilerplate 文件仅签名，business/infra/混合全量，1-hop 依赖仅签名
tags:
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - be
  severity: medium
  source_ref: conversations/conv-基于本仓库代码逐层说明「准确性-可信度」是怎么保证的。-##-核心立场-工具做确定性簿记，推理决策永远在调用方与用户手里.md
  scene: 知识可信度
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:32:14+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:32Z'
---

## Background

流传的说法是 code_routing 按「business 全量源码 / boilerplate 仅签名 / infra 摘要」三档注入，实际与源码不符。2026-09-04 源码核验（`codewiki/src/be/prompt_template.py:596-659`）确认判定是**按文件粒度**的两档而非三档。

## 正确做法/真实规则

- 纯 boilerplate 文件（`file_categories == {"boilerplate"}`）→ 仅签名（参数表 ≤15 参数）。
- business / infra / 混合文件 → 整文件全量源码。
- BFS 1-hop 依赖组件 → 仅签名（≤15 条，`prompt_template.py:625-659`），提示语注明「需全文用 read_code_components」。
- **不存在单独的「infra 摘要」档**。

## Root cause

以想当然的三档描述代替对实际实现的分支阅读；涉及注入完整度的行为描述必须以 `prompt_template.py` 的分支为准。
