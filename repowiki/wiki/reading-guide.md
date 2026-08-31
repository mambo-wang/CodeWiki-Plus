---
type: Concept
title: 阅读指南
generated:
  by: codewiki/reading_guide.py
  at: 2026-08-29 23:41:34+00:00
stale_after: '2027-02-26'
description: '> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。'
status: stable
verified:
- by: human:wangbao
  at: '2026-08-29T23:42:57Z'
---
# 阅读指南

> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。
> 排序依据为 PageRank 得分（综合考虑被依赖数量及依赖方自身的重要性），
> 表中「直接被依赖数」列为原始入度，仅供参考。

## 推荐阅读顺序

| # | 组件 | 类型 | 所属模块 | 直接被依赖数 | PageRank | 文件 |
|---|------|------|----------|--------------|----------|------|
| 1 | `CLILogger.debug` | method | - | 92 | 0.0165 | codewiki\cli\utils\logging.py |
| 2 | `LazyComponentStore.items` | method | - | 115 | 0.0123 | codewiki\mcp\cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0088 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 4 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0064 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 5 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0055 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 6 | `NamespaceResolver.resolve` | method | - | 100 | 0.0055 | ...iki\src\be\dependency_analyzer\analyzers\php.py |
| 7 | `SessionWorkspace.write_text` | method | - | 61 | 0.0048 | codewiki\mcp\workspace.py |
| 8 | `CLILogger.error` | method | - | 32 | 0.0048 | codewiki\cli\utils\logging.py |
| 9 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0038 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 10 | `LazyComponentStore.values` | method | - | 38 | 0.0037 | codewiki\mcp\cache.py |
| 11 | `CallRelationship` | class | - | 19 | 0.0035 | codewiki\src\be\dependency_analyzer\models\core.py |
| 12 | `Node` | class | - | 19 | 0.0035 | codewiki\src\be\dependency_analyzer\models\core.py |
| 13 | `CrossServiceMatcher.match` | method | - | 29 | 0.0034 | ...ency_analyzer\analysis\cross_service_matcher.py |
| 14 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0031 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 15 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0029 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 16 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0028 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 17 | `LazyComponentStore.keys` | method | - | 30 | 0.0028 | codewiki\mcp\cache.py |
| 18 | `meta_resolve` | function | - | 21 | 0.0022 | codewiki\src\config.py |
| 19 | `is_cbm_enabled` | function | - | 6 | 0.0022 | codewiki\mcp\cbm_client.py |
| 20 | `ModuleProgressBar.update` | method | - | 19 | 0.0020 | codewiki\cli\utils\progress.py |

---
*基于 1649 个组件、3116 条依赖边计算。*