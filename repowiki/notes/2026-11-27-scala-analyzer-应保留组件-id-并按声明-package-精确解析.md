---
type: decision
title: "Scala analyzer 应保留组件 ID 并按声明 package 精确解析"
tags: ["decision"]
aliases: ["Scala package-aware", "Scala analyzer", "tree-sitter-scala", "companion object", "wildcard import"]
metadata:
  date: 2026-11-27
  confidence_level: strong
  related_modules: ["DependencyAnalyzer", "AnalysisPipeline"]
  verification: {"test_ref": "tests/test_scala_analyzer.py"}
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T05:40:46Z }
stale_after: 2027-11-27
---

## 背景

本地已有 Scala 文件发现，却缺少独立 analyzer。上游实现会吞掉 grammar 异常，且通用尾名解析容易把不同 package 的同名 class、object 或方法错绑。

## 核心内容

采用独立 tree-sitter-scala wheel 与薄适配：保留 `<relative_path>::<logical_name>` 组件 ID，以 `scala:<package>::<symbol>` 延迟解析跨文件引用；companion object 用 `$` 区分。wildcard 只接受唯一命中，未知接收者、重载 ID 冲突及无法证明的字段类型保守弃权。增量缓存从持久化身份还原嵌套类型与 companion，并重新裁决可能受新增符号影响的旧边。

## 原因

Scala package 是声明身份，不等于目录；组件 ID 又不含方法签名，不能靠后声明覆盖或尾名猜测。局部 receiver 必须遵循词法作用域，全限定基类与导入字段类型必须保留 package 身份。顶层函数只能作为继承成员未命中时的后备，不能与基类成员同时产边。

## 边界

不承诺完整类型推导、隐式/扩展方法、宏、动态派发、重载目标选择或多基类线性化；字段链仅限可唯一固化 package 身份的类构造参数。grammar 缺失在 preflight 与直接 analyzer 两条路径显式失败。
