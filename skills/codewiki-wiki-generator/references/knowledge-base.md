# LLM Wiki 知识库详解

Wiki 生成完成后，CodeWiki 提供三个知识管理工具，让 Agent 在日常编码中持续利用 Wiki 积累的上下文。这些工具**不需要活跃的 session**，通过 `output_dir` 定位 Wiki 即可使用。

## 工具选择原则：Wiki 查知识，代码查实现

Agent 在查找信息时，必须根据信息类型选择正确的工具，**避免用代码搜索替代 Wiki 查询**：

| 你想找什么 | 用什么工具 | 不要用 |
|------------|-----------|--------|
| 历史踩坑经验、Bug 修复记录 | `query_wiki`（`include_notes: true`） | grep / 代码搜索 |
| 设计决策原因（为什么选 A 不选 B） | `query_wiki` | grep / 代码搜索 |
| 架构约定、模块划分理由 | `query_wiki` | grep / 代码搜索 |
| 某函数的具体实现和调用链 | grep / 代码搜索 / CodeGraph | `query_wiki` |
| 某文件的当前代码内容 | 直接读取文件 | `query_wiki` |

**核心规则**：凡是「为什么」和「踩过什么坑」类的问题，只用 `query_wiki`，不要检索代码。代码里只有 what（做了什么），没有 why（为什么这么做）和 lesson（踩过什么坑）——这些知识只存在于 Wiki 笔记中。

## query_wiki — 查询文档和笔记

在编码、调试或做设计决策时，先查询 Wiki 获取相关上下文：

```json
{
  "query": "如何处理依赖分析",
  "scope": "dependency_graph_construction",
  "include_notes": true,
  "include_code_refs": true,
  "max_results": 10,
  "expand_terms": ["依赖图", "依赖追踪", "调用关系"]
}
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `query` | string | 自然语言描述问题（如「如何处理循环依赖」而非「circular dependency」） |
| `scope` | string | 限定搜索范围到某个模块，减少噪声 |
| `include_notes` | bool | 是否包含笔记（决策/经验/架构说明） |
| `include_code_refs` | bool | 是否包含代码引用 |
| `max_results` | int | 最大返回结果数 |
| `expand_terms` | string[] | 同义词/近义词列表，BM25 搜索同时匹配这些词，提升召回率 |

### 搜索策略

- `query` 用自然语言描述问题，而非代码关键词
- `scope` 可限定搜索范围到某个模块
- `expand_terms` 传入同义词/近义词，特别适合中文场景（如「鉴权」↔「授权」↔「认证」）
- 返回结果包含 `context_package`（上下文片段摘要）和相关组件 ID

## ingest_note — 归档决策和经验

当团队做出重要设计决策、发现经验教训或明确架构意图时，归档到知识库：

```json
{
  "note_type": "decision",
  "title": "选择 SQLite 作为缓存后端",
  "content": "## 背景\n\n需要一个轻量、零依赖的缓存方案...\n\n## 决策\n\n选择 SQLite，原因：1) 单文件部署... 2) 并发读性能好...\n\n## 替代方案\n\n考虑过 Redis，但增加了部署复杂度。",
  "related_modules": ["analysis_cache"]
}
```

### note_type 可选值

| 类型 | 适用场景 | 示例 |
|------|----------|------|
| `decision` | 设计决策（ADR） | 选择某框架、某算法、某 API 风格 |
| `lesson` | 经验教训 | 踩过的坑、性能调优发现 |
| `architecture` | 架构说明 | 模块划分理由、数据流设计 |
| `bug_fix` | Bug 修复记录 | 根因分析、修复方案 |
| `general` | 通用笔记 | 其他不归入以上分类的知识 |

笔记存储在 `<output_dir>/notes/` 目录，带 YAML frontmatter，可被 `query_wiki` 全文检索。`related_modules` 如果省略会自动检测。

## lint_wiki — 文档一致性检查

定期运行检查文档与代码是否同步：

```json
{}
```

### 5 项检查

1. **过时引用** — 文档引用的组件在代码中已不存在
2. **断链** — 文档间的交叉引用指向不存在的文件
3. **未文档化组件** — 代码中有组件但文档未覆盖
4. **循环依赖** — 模块之间存在循环引用
5. **覆盖率** — 统计文档对组件的覆盖比例

当 `high_impact_threshold`（schema.yaml 中配置，默认 5）个以上组件受影响时，lint 会标记为高优先级。建议在增量更新后或定期执行，保持文档健康度。
