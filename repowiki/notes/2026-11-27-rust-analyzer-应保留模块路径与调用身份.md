---
type: decision
title: Rust analyzer 应保留模块路径与调用身份
tags:
- decision
aliases:
- Rust analyzer
- grammar preflight
- tree-sitter-rust
- 模块路径
- C2
metadata:
  date: 2026-11-27
  confidence_level: strong
  related_modules:
  - dependency_analyzer
  - LanguageAnalyzers
  - AnalysisPipeline
  reason: C2 Rust 薄适配实施后沉淀决策草稿，等待用户确认。
  verification:
    test_ref: tests/test_rust_analyzer.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.8
  at: 2026-11-26 21:48:10+00:00
stale_after: '2027-11-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-11-27T00:41:14Z'
---

## 背景

.rs 文件已被收集并通过语言白名单，但缺少 analyzer 分派，曾导致 Rust 仓库产出零源码组件。直接按尾名解析又会把 tokio::spawn、未知接收者方法和跨文件同名函数误绑到本地符号。

## 决策

使用独立 tree-sitter-rust wheel，并在解析任何文件前做一次性 grammar preflight；缺失或 ABI 不兼容时显式失败，不降级为空节点。组件保留 src 文件模块、crate/self/super、import/alias 与 trait impl 身份，调用边保留 :: 路径和接收者类型。

## 原因与边界

离线首用不能依赖 grammar 下载，路径与类型是 Rust 符号身份的一部分。未知接收者不猜目标，trait impl 同名方法使用 Type.Trait.method 唯一 ID；内联模块按外→内拼接，import 按模块隔离，嵌套自由函数保留外层函数身份且不归为 impl 方法。macro token tree 内部调用、glob import、函数块内 import 的完整词法作用域与完整类型推导不在本切片内；既有增量链路只解析变更文件，“仅变更 impl 文件、类型与 trait 留在未变更文件”时的跨文件 trait 回填尚未覆盖，需后续增量索引切片验证。不整包替换 dependency_analyzer。
