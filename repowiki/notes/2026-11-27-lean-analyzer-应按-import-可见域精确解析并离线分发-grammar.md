---
type: decision
title: "Lean analyzer 应按 import 可见域精确解析并离线分发 grammar"
tags: ["callgraph", "codewiki", "decision", "leannameresolver"]
aliases: ["Lean 4", "lean analyzer", "import", "open", "export", "离线 grammar", "增量重解析"]
metadata:
  date: 2026-11-27
  confidence_level: strong
  task_id: 他山之石
  related_modules: ["dependency_analyzer", "mcp"]
  related_components: ["src/Geo/Point.lean::Geo.Point.origin"]
  verification: {"test_ref": "tests/test_lean_analyzer.py"}
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T10:28:36Z }
stale_after: 2027-11-27
---

## 背景

CodeWiki-Plus 需要分析 Lean 4 仓库，但必须保留本地组件 ID、CallGraph 与 SQLite 增量契约。上游 header scanner + Tree-sitter + 精确名称解析值得借鉴；PyPI 没有独立 Lean grammar wheel，language-pack 首次使用又会联网下载，不能直接复制。

## 核心内容

保留 `<relative_path>::<logical_name>` 组件 ID，以 header scanner 提取声明结构、Tree-sitter 提取引用、LeanNameResolver 处理 import/open/export/private/protected 可见域。模块 import 优先仓库根路径，source-root 后缀只允许唯一回退，歧义整体弃权。随包分发六平台 ABI 15 parser，记录 revision/release/SHA-256 与 MIT 许可证；Tree-sitter 下限为 0.25.0，grammar/parser 故障显式失败。

任一 Lean 文件变化时重解析全部现存 Lean；非 Lean 增量只合并仍存活的缓存节点与目标边。import-only 文件纳入指纹，watch 扩展变更集，删除文件清除旧指纹。`.lake/` 与 `lake-packages/` 不进入分析；Lake 项目文件接入服务识别与 artifact facts。

## 原因

Lean 的 import/open/export 会改变跨文件可见域，仅重解析变更文件会留下错误旧边。离线 native 资产避免首用下载失败被吞成零组件；完整组件 ID 与精确解析避免同尾名误绑。

## 边界

不执行 Lean、Lake 或构建脚本；不承诺完整类型推导、notation/macro 展开、generalized field notation、动态派发或外部依赖语义。决策草稿待用户逐篇确认。
