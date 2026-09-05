---
type: decision
title: schema.yaml 模板双源收敛为包内单源：删根副本、守卫测试只验包内模板、清理 init_wiki/schema_generator fallback
tags:
- decision
metadata:
  date: 2026-09-05
  related_modules:
  - init_wiki
  - schema_generator
  severity: medium
  source_ref: conversations/conv-我们是如何保证生成的代码WIKI的准确性可信度.md
  scene: 配置分发
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:37:40+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:38Z'
---

## Decision

schema 模板「仓库根 schema.yaml + codewiki/templates/schema.yaml」双份机制废止，收敛为**包内模板单源**：

- 删除根 `schema.yaml`；`init_wiki.py` 移除 `_SCHEMA_TEMPLATE_ROOT`、`schema_generator.py` 移除 `_CONFIG_PATH_ROOT` fallback（包内模板存在时两条 fallback 永不生效）。
- 守卫测试 `test_config_from_repo_schema_files` → `test_config_from_bundle_schema`，只校验包内模板。
- 此前已把 `conventions.auto_evidence: true` 补进包内模板与 repowiki/schema.yaml。

## Rationale

本次分叉的直接事故：`auto_evidence` 开关只加进根 schema.yaml（L57-60），而 init_wiki 实际分发的是包内模板（另有 freshness/git_sync 反例）——**两份模板各自演进、现有守卫只查 promotion 两字段，漏检**。双份机制本身就是 bug 源：功能加了但分发模板没跟上 = 新工作区静默拿不到开关。

## 适用范围

凡「仓库内模板 + 包内模板」双份分发的配置/脚手架，优先收敛为打包内单源，并让测试守卫指向唯一权威副本。
