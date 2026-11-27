---
type: decision
title: Ruby analyzer 应保留命名空间与调用身份，并保守推断接收者
tags:
- codewiki
- decision
aliases:
- Ruby analyzer
- tree-sitter-ruby
- 命名空间
- 接收者推断
- 实例方法
- 单例方法
metadata:
  date: 2026-11-27
  confidence_level: strong
  related_modules:
  - dependency_analyzer
  - mcp
  verification:
    test_ref: tests/test_ruby_analyzer.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.8
  at: 2026-11-26 22:57:15+00:00
stale_after: '2027-11-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-11-27T00:41:14Z'
---

## 背景

CodeWiki-Plus 需要为 Ruby 仓库补充源码组件与调用边，但上游实现与本地 dependency_analyzer、增量缓存和 MCP 组件 ID 契约并不一致，不能整包覆盖。

## 核心内容

采用独立 tree-sitter-ruby grammar 与一次性 preflight，缺失时显式失败。类与模块保留完整词法命名空间；实例方法、单例方法和顶层方法分别使用 #、. 身份，重开类复用同一组件。常量引用找到词法命名空间后保留剩余路径，superclass 在 enclosing scope 求值。接收者只采用调用点之前、同一词法执行路径上可确定的构造器赋值；条件赋值、未知重赋值、参数与 block 遮蔽都保守处理。仓库分析模式延迟解析裸方法，并跨文件保留 #/. 身份；限定调用只做精确匹配，不按尾名猜测。

## 原因

Ruby 的动态派发与重开类会使同名方法大量并存。错误绑定会污染依赖图和增量影响范围，比明确缺失一条边更有害；grammar 失败也不能伪装成零组件。

## 边界

不执行 Ruby，不把 send、public_send、define_method 或属性宏凭空转成方法与调用边；不承诺默认参数类型推断、完整 Ruby 类型推导或所有动态元编程语义。SQLite 指纹扫描必须同步识别 .rb/.rs，否则新增语言会在无改动时反复全量标记变更。
