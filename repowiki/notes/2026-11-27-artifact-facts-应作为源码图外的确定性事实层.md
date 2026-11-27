---
type: decision
title: artifact facts 应作为源码图外的确定性事实层
tags:
- decision
aliases:
- artifact facts
- artifact_changed_files
- 构建事实层
- C3
metadata:
  date: 2026-11-27
  confidence_level: strong
  related_modules:
  - mcp
  - analysis
  reason: C3 薄适配层实施后沉淀决策草稿，等待用户确认。
  verification:
    test_ref: tests/test_artifact_facts.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.8
  at: 2026-11-26 21:22:11+00:00
stale_after: '2027-11-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-11-27T00:41:13Z'
---

## 背景

Make、CI、Docker、manifest、schema 与脚本包含重要的构建和部署知识，但把它们全部塞入源码依赖图会污染 component ID、module tree 与影响分析。

## 决策

建立独立的 artifact facts 派生物：使用 artifact: 命名空间，按文件与行号记录确定性事实，不执行任何命令、不导出环境值或命令正文；通过 artifact_changed_files 支持纯 artifact 改动进入增量流程。

## 原因与边界

事实表可以安全重建，且失败、截断、遗漏必须可见。它不改变源码组件图，正文解释与页面改写仍由宿主 Agent 完成；不照搬上游整套 artifact analyzer，也不自动重聚类。解析只读有界前缀，指纹哈希完整文件，特殊文件不得阻塞采集。
