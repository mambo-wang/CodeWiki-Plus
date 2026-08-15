---
type: pitfall
title: module_tree.json 的 children 是字符串引用而非嵌套对象
tags:
- pitfall
metadata:
  date: 2026-08-15
  related_modules:
  - module_tree
  - analyze_repo
  source_ref: raw\conv-user_command-commands-codewiki-增量更新-Wiki-请增量更新代码仓库的-Wiki-文档。.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:14:28+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:12Z'
---

## 背景

增量更新 Wiki 遍历 `repowiki/.meta/module_tree.json` 时反复报错 `'str' object has no attribute 'get'`。

## 根因

`module_tree.json` 是 dict 结构，节点的 `children` 字段是**字符串引用**（指向其他模块 id），不是嵌套 dict。`tree['MCP_Server']['children']` 得到的是字符串列表，对每个字符串再调 `.get()` 就报错。

## 正确做法

遍历前先判断 children 元素类型：字符串需二次查顶层定义节点；「顶层 6 模块 + MCP_Server 下 8 个子模块」的层级关系要手动解析 id 引用，不能用嵌套 dict 假设。
