---
type: decision
title: "Dart analyzer 应按 library visible scope 精确解析并持久化原始引用"
tags: ["decision"]
metadata:
  date: 2026-11-27
  confidence_level: strong
  task_id: 他山之石
  verification: {"test_ref": "tests/test_dart_analyzer.py"}
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T07:32:33Z }
stale_after: 2027-11-27
---

## 决策

Dart/Flutter 采用独立 `tree-sitter-dart` wheel 与薄适配层，保留 `<relative_path>::<logical_name>` 组件 ID，不整包替换本地 `dependency_analyzer`。跨文件绑定由全部 Dart 文件的 directives 构建 library visible scope 后裁决；caller 解析失败不得进入通用裸名或尾名回退。

## 机制

- import 支持相对 URI、仓库内 `package:<pubspec name>/...`、prefix、`show`/`hide`；export 沿路径累积过滤，多路径保持并集，cycle 必须终止。
- `part` 是 library 成员关系的权威边，`part of` 只作 fallback；同 library 的 root 与 parts 共享 visible scope，`_` 私有名不跨 library。
- 局部参数、变量与函数按词法作用域遮蔽外层名字；prefix 是命名空间的一部分，不能只做字符串剥离。类型化 receiver 的字段链逐跳解析，未知类型弃权。
- 同文件或可证明的继承成员沿基类链查找，override 优先并用 seen set 终止循环；多个 visible 同名候选整体弃权。
- Flutter 仅做轻量确定性分类：widget/state、ChangeNotifier/Bloc/Cubit、Riverpod、Provider/GoRouter，以及 build/createState 实例化提升；不执行生成代码。

## 增量缓存

`Node.metadata.dart_raw_dependencies` 保存每个已解析目标对应的原始引用，SQLite 通过 `components.metadata_json` 持久化。增量时读取全部 Dart 文件 directives 重建 scope，缓存旧边只有原始引用当前仍解析到同一目标才保留。旧缓存缺少 metadata 时首次升级重解析对应 Dart 文件，避免凭目标名复活旧边或丢失全部边。

`pubspec.yaml` 是 package 解析的语义依赖：directive-only Dart 文件与 pubspec 都纳入指纹；package 名变化重解析全部 Dart caller。旧 SQLite 需要自动补 `metadata_json` 列，insert 使用显式列名，避免迁移后列顺序变化把 content hash 写进 metadata。

## 边界

不执行 Dart analyzer，不承诺完整类型推导、泛型实例化、隐式转换或动态派发；不识别生成 provider 的完整 Riverpod 语义。`extension type`、unnamed `library;`、null-aware collection 等新语法可能仍为 ERROR。跨 library 继承成员查找保持保守；重载或同名 component ID 冲突尚未像 Scala 那样显式弃权。

## 验证

Dart 专项 36 项通过，覆盖 prefix/show/hide/part/export/private、局部遮蔽、继承、Flutter、增量缓存、旧 SQLite 迁移、pubspec 语义依赖与正式 MCP 无变更路径。独立审查发现的两项缺陷均有先红后绿回归。
