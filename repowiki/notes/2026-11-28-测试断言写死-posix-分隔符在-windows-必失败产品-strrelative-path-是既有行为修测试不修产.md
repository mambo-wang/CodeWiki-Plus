---
type: pitfall
title: "测试断言写死 POSIX 分隔符在 Windows 必失败：产品 str(relative_path) 是既有行为，修测试不修产品"
tags: ["pitfall"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  scene: "跨平台测试兼容"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-28T00:09:22Z }
stale_after: 2027-05-27
---

## Background
新增测试 test_repository_tree_keeps_only_declared_nested_checkouts（tests/test_runtime_boundaries.py）在 Windows 上必失败：断言 paths == {"app.py", "vendor/declared/sentinel.py"}，但产品 file_tree.path 用 str(relative_path) 生成（repo_analyzer.py，提交前就如此），Windows 下产出 vendor\declared\sentinel.py。实测 23 通过 / 1 失败，差异仅分隔符。

## 正确做法
- 测试侧归一化：paths.add(node["path"].replace("\\", "/"))，保持产品原有路径格式不变；
- 不要顺手改产品：file_tree.path 的原生分隔符行为早于本提交存在，下游消费方未枚举，改产品路径格式风险不可控；
- 判定依据：这是测试的平台兼容缺陷而非产品回归——CI（ubuntu）绿但 Windows 全量测试变红，而 AGENTS.md 的交付门槛要求本机 Windows 全量绿。

## Rationale
「断言写死 POSIX 分隔符 vs 产品输出原生分隔符」是 Windows 开发环境的反复踩坑点；修复方向（改测试不改产品）依赖「行为先于提交存在」的考古判断，记录下来避免下次同类失败时误判为产品回归去改产品。

## Root cause
str(Path) 在 Windows 返回反斜杠；测试作者在 POSIX 心智下写死了正斜杠期望值。
