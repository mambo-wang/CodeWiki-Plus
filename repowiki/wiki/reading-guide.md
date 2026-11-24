---
type: Concept
title: "Reading Guide"
generated: { by: codewiki/reading_guide.py, at: 2026-10-26T01:59:17Z }
stale_after: 2099-12-31
description: "> Generated automatically from PageRank dependency analysis. Components ranked higher are depended on by more modules — read them first."
---
# Reading Guide

> Generated automatically from PageRank dependency analysis. Components ranked higher are depended on by more modules — read them first.
> Ranking is by PageRank score (weighing both how many dependents a component has and how important those dependents are),
> The "Direct Dependents" column is the raw in-degree and is provided for reference only.

## Recommended reading order

| # | Component | Type | Module | Direct Dependents | PageRank | File |
|---|------|------|----------|--------------|----------|------|
| 1 | `CLILogger.debug` | method | - | 105 | 0.0164 | codewiki/cli/utils/logging.py |
| 2 | `LazyComponentStore.items` | method | - | 123 | 0.0122 | codewiki/mcp/cache.py |
| 3 | `TreeSitterTSAnalyzer._get_node_text` | method | - | 26 | 0.0081 | .../be/dependency_analyzer/analyzers/typescript.py |
| 4 | `NamespaceResolver.resolve` | method | - | 112 | 0.0060 | ...iki/src/be/dependency_analyzer/analyzers/php.py |
| 5 | `TreeSitterTSAnalyzer._find_child_by_type` | method | - | 19 | 0.0059 | .../be/dependency_analyzer/analyzers/typescript.py |
| 6 | `TreeSitterJSAnalyzer._get_node_text` | method | - | 19 | 0.0050 | .../be/dependency_analyzer/analyzers/javascript.py |
| 7 | `CLILogger.error` | method | - | 32 | 0.0044 | codewiki/cli/utils/logging.py |
| 8 | `TreeSitterJSAnalyzer._find_child_by_type` | method | - | 14 | 0.0035 | .../be/dependency_analyzer/analyzers/javascript.py |
| 9 | `CrossServiceMatcher.match` | method | - | 34 | 0.0035 | ...ency_analyzer/analysis/cross_service_matcher.py |
| 10 | `LazyComponentStore.values` | method | - | 38 | 0.0034 | codewiki/mcp/cache.py |
| 11 | `CallRelationship` | class | - | 19 | 0.0032 | codewiki/src/be/dependency_analyzer/models/core.py |
| 12 | `Node` | class | - | 19 | 0.0032 | codewiki/src/be/dependency_analyzer/models/core.py |
| 13 | `KnowledgeStore.relpath` | method | - | 28 | 0.0030 | codewiki/src/store.py |
| 14 | `TreeSitterJSAnalyzer._get_relative_path` | method | - | 9 | 0.0029 | .../be/dependency_analyzer/analyzers/javascript.py |
| 15 | `TreeSitterTSAnalyzer._add_relationship` | method | - | 8 | 0.0027 | .../be/dependency_analyzer/analyzers/typescript.py |
| 16 | `LazyComponentStore.keys` | method | - | 30 | 0.0026 | codewiki/mcp/cache.py |
| 17 | `TreeSitterJSAnalyzer._get_component_id` | method | - | 8 | 0.0026 | .../be/dependency_analyzer/analyzers/javascript.py |
| 18 | `atomic_write` | function | - | 30 | 0.0026 | codewiki/src/store.py |
| 19 | `load_schema` | function | - | 27 | 0.0024 | codewiki/mcp/tools/page_router.py |
| 20 | `ModuleProgressBar.update` | method | - | 22 | 0.0022 | codewiki/cli/utils/progress.py |

---
*Computed from 1800 components and 3435 dependency edges.*