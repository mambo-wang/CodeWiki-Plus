---
type: Concept
title: "阅读指南"
generated: { by: codewiki/reading_guide.py, at: 2026-09-04T04:20:00Z }
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
| 1 | `CLILogger.debug` | method | - | 105 | 0.0164 | codewiki\cli\utils\logging.py |
| 2 | `LazyComponentStore.items` | method | - | 122 | 0.0121 | codewiki\mcp\cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0081 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 4 | `NamespaceResolver.resolve` | method | - | 112 | 0.0060 | ...iki\src\be\dependency_analyzer\analyzers\php.py |
| 5 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0059 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 6 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0051 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 7 | `CLILogger.error` | method | - | 32 | 0.0044 | codewiki\cli\utils\logging.py |
| 8 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0035 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 9 | `CrossServiceMatcher.match` | method | - | 34 | 0.0035 | ...ency_analyzer\analysis\cross_service_matcher.py |
| 10 | `LazyComponentStore.values` | method | - | 37 | 0.0033 | codewiki\mcp\cache.py |
| 11 | `CallRelationship` | class | - | 19 | 0.0032 | codewiki\src\be\dependency_analyzer\models\core.py |
| 12 | `Node` | class | - | 19 | 0.0032 | codewiki\src\be\dependency_analyzer\models\core.py |
| 13 | `KnowledgeStore.relpath` | method | - | 28 | 0.0030 | codewiki\src\store.py |
| 14 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0029 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 15 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0027 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 16 | `LazyComponentStore.keys` | method | - | 30 | 0.0027 | codewiki\mcp\cache.py |
| 17 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0026 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 18 | `atomic_write` | function | - | 30 | 0.0026 | codewiki\src\store.py |
| 19 | `load_schema` | function | - | 27 | 0.0024 | codewiki\mcp\tools\page_router.py |
| 20 | `ModuleProgressBar.update` | method | - | 22 | 0.0022 | codewiki\cli\utils\progress.py |

---
*基于 1795 个组件、3426 条依赖边计算。*