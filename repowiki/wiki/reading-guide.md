# 阅读指南

> 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。
> 排序依据为 PageRank 得分（综合考虑被依赖数量及依赖方自身的重要性），
> 表中「直接被依赖数」列为原始入度，仅供参考。

## 推荐阅读顺序

| # | 组件 | 类型 | 所属模块 | 直接被依赖数 | PageRank | 文件 |
|---|------|------|----------|--------------|----------|------|
| 1 | `CLILogger.debug` | method | - | 72 | 0.0189 | codewiki\cli\utils\logging.py |
| 2 | `LazyComponentStore.items` | method | - | 91 | 0.0136 | codewiki\mcp\cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0117 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 4 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0085 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 5 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0073 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 6 | `CLILogger.error` | method | - | 32 | 0.0063 | codewiki\cli\utils\logging.py |
| 7 | `NamespaceResolver.resolve` | method | - | 70 | 0.0056 | ...iki\src\be\dependency_analyzer\analyzers\php.py |
| 8 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0050 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 9 | `CallRelationship` | class | - | 19 | 0.0047 | codewiki\src\be\dependency_analyzer\models\core.py |
| 10 | `Node` | class | - | 19 | 0.0046 | codewiki\src\be\dependency_analyzer\models\core.py |
| 11 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0041 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 12 | `LazyComponentStore.values` | method | - | 29 | 0.0040 | codewiki\mcp\cache.py |
| 13 | `SessionWorkspace.write_text` | method | - | 35 | 0.0039 | codewiki\mcp\workspace.py |
| 14 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0039 | ...\be\dependency_analyzer\analyzers\typescript.py |
| 15 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0037 | ...\be\dependency_analyzer\analyzers\javascript.py |
| 16 | `LazyComponentStore.keys` | method | - | 24 | 0.0036 | codewiki\mcp\cache.py |
| 17 | `meta_resolve` | function | - | 24 | 0.0032 | codewiki\src\config.py |
| 18 | `is_cbm_enabled` | function | - | 6 | 0.0028 | codewiki\mcp\cbm_client.py |
| 19 | `RouteNode` | class | - | 15 | 0.0027 | ...\be\dependency_analyzer\models\cross_service.py |
| 20 | `TreeSitterPHPAnalyzer._find_child_by_type` | method | - | 10 | 0.0022 | ...iki\src\be\dependency_analyzer\analyzers\php.py |

---
*基于 1246 个组件、2274 条依赖边计算。*