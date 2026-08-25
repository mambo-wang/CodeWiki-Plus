---
type: Concept
title: 阅读指南
generated:
  by: codewiki/reading_guide.py
  at: 2026-08-25 16:47:27+00:00
stale_after: '2027-02-22'
description: '> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。'
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:20Z'
---
# 阅读指南

> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。
> 排序依据为 PageRank 得分（综合考虑被依赖数量及依赖方自身的重要性），
> 表中「直接被依赖数」列为原始入度，仅供参考。

## 推荐阅读顺序

| # | 组件 | 类型 | 所属模块 | 直接被依赖数 | PageRank | 文件 |
|---|------|------|----------|--------------|----------|------|
| 1 | `CLILogger.debug` | method | - | 90 | 0.0174 | codewiki\cli\utils\logging.py |
| 2 | `LazyComponentStore.items` | method | - | 111 | 0.0129 | codewiki\mcp\cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0093 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 4 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0068 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 5 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0058 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 6 | `NamespaceResolver.resolve` | method | - | 87 | 0.0051 | ...iki\src\be\dependency_analyzer\analyzers\php.py |
| 7 | `CLILogger.error` | method | - | 32 | 0.0050 | codewiki\cli\utils\logging.py |
| 8 | `SessionWorkspace.write_text` | method | - | 57 | 0.0050 | codewiki\mcp\workspace.py |
| 9 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0040 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 10 | `LazyComponentStore.values` | method | - | 36 | 0.0038 | codewiki\mcp\cache.py |
| 11 | `CallRelationship` | class | - | 19 | 0.0037 | codewiki\src\be\dependency_analyzer\models\core.py |
| 12 | `Node` | class | - | 19 | 0.0037 | codewiki\src\be\dependency_analyzer\models\core.py |
| 13 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0033 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 14 | `LazyComponentStore.keys` | method | - | 30 | 0.0031 | codewiki\mcp\cache.py |
| 15 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0031 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 16 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0030 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 17 | `CrossServiceMatcher.match` | method | - | 22 | 0.0030 | ...ency_analyzer\analysis\cross_service_matcher.py |
| 18 | `meta_resolve` | function | - | 24 | 0.0027 | codewiki\src\config.py |
| 19 | `is_cbm_enabled` | function | - | 6 | 0.0023 | codewiki\mcp\cbm_client.py |
| 20 | `RouteNode` | class | - | 15 | 0.0021 | ...\be\dependency_analyzer\models\cross_service.py |

---
*基于 1562 个组件、2918 条依赖边计算。*