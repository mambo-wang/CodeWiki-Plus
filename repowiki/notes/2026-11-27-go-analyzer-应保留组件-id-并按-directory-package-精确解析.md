---
type: decision
title: "Go analyzer 应保留组件 ID 并按 directory package 精确解析"
tags: ["codewiki", "decision"]
aliases: ["Go package-aware", "directory package", "go.mod local replace", "隐式 interface"]
metadata:
  date: 2026-11-27
  confidence_level: strong
  task_id: 他山之石
  related_modules: ["dependency_analyzer"]
  verification: {"test_ref": "tests/test_go_analyzer.py"}
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T02:44:03Z }
stale_after: 2027-11-27
---

## 背景

CodeWiki-Plus 已有基础 Tree-sitter Go analyzer 与本地 route extractor，但缺少上游的 directory/package 身份、仓库 import 解析与隐式 interface implementation 链接。直接替换整套 dependency_analyzer 会破坏本地组件 ID、增量缓存、跨服务路由与影响分析。

## 决策

保留本地 `<relative_path>::<logical_name>` 组件 ID 和 `go_routes.py`，新增独立 `go_package.py` 薄层承载 package 簿记与精确解析。package reference 使用 `<dir>/*.go::<Name>`，根 package 使用 `*.go::<Name>`；组件 `qualified_name` 记录 `<package>.<name>`，不改变既有 ID。

## 实现

- 向上查找最近 `go.mod`，解析 module path 与 local `replace`；无 `go.mod` 时只接受能映射到仓库现有目录的 GOPATH 风格后缀。
- `GoPackageIndex` 按 `(directory, name)` 解析；包级函数与同名方法分开索引，未知接收者裸方法仅在可见 package 中唯一时解析。
- 外部包、标准库与 builtin 不产生项目边；dot/blank import 保守。限定字段类型区分仓库 import 与外部包，避免 `context.Context` 误绑项目同名类型。
- 全部文件解析后按同 package method name set 链接隐式 interface implementation，并回填类型 `base_classes`；`_test.go` 与 `vendor/` 不产出组件。
- grammar 在 pipeline preflight 与直接 analyzer 两条路径都显式失败。
- MCP 与 watch 增量把未变更 Go components 合并进 package index；隐式 interface 边重新计算，避免接口收紧后保留旧实现边。

## 边界

interface implementation 当前只按方法名集合近似，不校验完整签名、指针接收者方法集或嵌入接口；不展开 dot/blank import、vendored 依赖与外部包源码；不承诺完整 Go 类型推导、泛型实例化或动态派发。

## 验证

Go 专项 25 项通过；Go/Ruby/Rust/Vue/analyzer correctness/latest compat 联合 131 项通过；最终全量回归 1694 passed, 2 skipped, 1 warning（全量收集发生在第 25 项 Go 反例新增前，该项已由专项覆盖）；ruff、`go_package.py` mypy 与 `git diff --check` 通过。正式 stdio MCP 验证首次分析、无变更复用和单文件增量，变更后的调用成功解析到缓存 package 的 `lib/lib.go::Stop`。未运行会写真实 `repowiki/` 的 smoke 测试。
