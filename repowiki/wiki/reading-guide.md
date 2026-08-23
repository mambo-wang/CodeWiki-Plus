---
type: Concept
title: "阅读指南"
generated: { by: codewiki/reading_guide.py, at: 2026-08-23T00:00:00Z }
stale_after: 2099-12-31
description: "> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。"
---
# 阅读指南

> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。
> 排序依据为 PageRank 得分（综合考虑被依赖数量及依赖方自身的重要性），
> 表中「直接被依赖数」列为原始入度，仅供参考。

## 推荐阅读顺序

| # | 组件 | 类型 | 所属模块 | 直接被依赖数 | PageRank | 文件 |
|---|------|------|----------|--------------|----------|------|
| 1 | `CLILogger.debug` | method | - | 90 | 0.0180 | codewiki\cli\utils\logging.py |
| 2 | `LazyComponentStore.items` | method | - | 102 | 0.0124 | codewiki\mcp\cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0098 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 4 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0071 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 5 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0061 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 6 | `CLILogger.error` | method | - | 32 | 0.0053 | codewiki\cli\utils\logging.py |
| 7 | `SessionWorkspace.write_text` | method | - | 57 | 0.0052 | codewiki\mcp\workspace.py |
| 8 | `NamespaceResolver.resolve` | method | - | 81 | 0.0049 | ...iki\src\be\dependency_analyzer\analyzers\php.py |
| 9 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0042 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 10 | `CallRelationship` | class | - | 19 | 0.0039 | codewiki\src\be\dependency_analyzer\models\core.py |
| 11 | `Node` | class | - | 19 | 0.0039 | codewiki\src\be\dependency_analyzer\models\core.py |
| 12 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0035 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 13 | `LazyComponentStore.values` | method | - | 31 | 0.0034 | codewiki\mcp\cache.py |
| 14 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0032 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 15 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0032 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 16 | `LazyComponentStore.keys` | method | - | 27 | 0.0031 | codewiki\mcp\cache.py |
| 17 | `CrossServiceMatcher.match` | method | - | 20 | 0.0028 | ...ency_analyzer\analysis\cross_service_matcher.py |
| 18 | `meta_resolve` | function | - | 24 | 0.0027 | codewiki\src\config.py |
| 19 | `is_cbm_enabled` | function | - | 6 | 0.0024 | codewiki\mcp\cbm_client.py |
| 20 | `RouteNode` | class | - | 15 | 0.0022 | ...\be\dependency_analyzer\models\cross_service.py |

---
*基于 1482 个组件、2757 条依赖边计算。*