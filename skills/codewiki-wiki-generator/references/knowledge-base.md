# LLM Wiki 知识库详解

Wiki 生成完成后，CodeWiki 提供 8 个知识管理工具，让 Agent 在日常编码中持续利用 Wiki 积累的上下文。这些工具**不需要活跃的 session**，通过 `output_dir` 定位 Wiki 即可使用。

## 结构化 Wiki 布局

所有 Wiki 内容按页面类型（page type）组织在 `wiki/` 子目录下：

| 页面类型 | 目录 | 说明 |
|----------|------|------|
| `module` | `wiki/modules/` | 模块文档（原有文档自动迁移到此目录） |
| `entity` | `wiki/entities/` | 实体页面：类、接口、数据库表、配置项等 |
| `concept` | `wiki/concepts/` | 概念页面：设计模式、业务概念、架构风格等 |
| `source` | `wiki/sources/` | 外部文档摘要：导入的第三方文档 |
| `comparison` | `wiki/comparisons/` | 对比分析：技术选型、方案比较等 |
| `query` | `wiki/queries/` | 研究查询：调研结论、问题排查记录等 |

另有 `raw/sources/`（第三方文档原始文件）、`.meta/issues.json`（质量问题追踪）、`.meta/source_registry.json`（外部文档注册表）。

`write_doc_file` 工具的 `page_type` 参数控制文件路由，指定类型即可自动存入正确目录。

## 工具选择原则：Wiki 查知识，代码查实现

Agent 在查找信息时，必须根据信息类型选择正确的工具，**避免用代码搜索替代 Wiki 查询**：

| 你想找什么 | 用什么工具 | 不要用 |
|------------|-----------|--------|
| 历史踩坑经验、Bug 修复记录 | `query_wiki`（`include_notes: true`） | grep / 代码搜索 |
| 设计决策原因（为什么选 A 不选 B） | `query_wiki` | grep / 代码搜索 |
| 架构约定、模块划分理由 | `query_wiki` | grep / 代码搜索 |
| 已导入的第三方文档内容 | `query_wiki`（`include_sources: true`） | grep / 代码搜索 |
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
  "include_sources": true,
  "type_filter": "module",
  "max_results": 10,
  "expand_terms": ["依赖图", "依赖追踪", "调用关系"]
}
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `query` | string | 自然语言描述问题（如「如何处理循环依赖」而非「circular dependency」） |
| `scope` | string | 限定搜索范围，支持模块名或目录前缀（如 `wiki/entities`、`notes`） |
| `include_notes` | bool | 是否包含笔记（决策/经验/架构说明） |
| `include_code_refs` | bool | 是否包含代码引用 |
| `include_sources` | bool | 是否包含已导入的第三方文档 |
| `type_filter` | string | 按页面类型过滤：module/entity/concept/source/comparison/query |
| `max_results` | int | 最大返回结果数 |
| `expand_terms` | string[] | 同义词/近义词列表，BM25 搜索同时匹配这些词，提升召回率 |

### 搜索策略

- `query` 用自然语言描述问题，而非代码关键词
- `scope` 支持目录前缀过滤（如 `wiki/entities` 只搜实体页面）
- `type_filter` 限定页面类型，减少噪声
- `expand_terms` 传入同义词/近义词，特别适合中文场景（如「鉴权」↔「授权」↔「认证」）
- **BM25 权重增强**：aliases 3× boost、severity 2× boost
- 返回结果包含 `context_package`（上下文片段摘要）和相关组件 ID

## ingest_note — 归档决策和经验

当团队做出重要设计决策、发现经验教训或明确架构意图时，归档到知识库：

```json
{
  "note_type": "decision",
  "title": "选择 SQLite 作为缓存后端",
  "content": "## 背景\n\n需要一个轻量、零依赖的缓存方案...\n\n## 决策\n\n选择 SQLite，原因：1) 单文件部署... 2) 并发读性能好...\n\n## 替代方案\n\n考虑过 Redis，但增加了部署复杂度。",
  "related_modules": ["analysis_cache"],
  "aliases": ["SQLite缓存", "缓存方案选型"],
  "source_ref": "rfc-sqlite-caching"
}
```

### note_type 可选值

| 类型 | 适用场景 | 新增字段 |
|------|----------|----------|
| `decision` | 设计决策（ADR） | — |
| `lesson` | 经验教训 | — |
| `architecture` | 架构说明 | — |
| `bug_fix` | Bug 修复记录 | — |
| `pitfall` | 踩坑记录 | `severity`（critical/high/medium/low）、`root_cause` |
| `known_issue` | 已知问题 | `source_ref` |
| `workaround` | 临时方案 | `severity`、`root_cause` |
| `general` | 通用笔记 | — |

笔记存储在 `<output_dir>/notes/` 目录，带 YAML frontmatter，可被 `query_wiki` 全文检索。`related_modules` 如果省略会自动检测。所有类型支持 `aliases`（别名，3× BM25 boost）和 `source_ref`（来源引用）。

## ingest_source — 导入第三方文档

将 API 文档、设计规范、RFC 等外部文档导入 Wiki：

```json
{
  "name": "rfc-7519-jwt",
  "source_type": "rfc",
  "source_path": "/path/to/rfc7519.txt",
  "description": "JWT 规范，定义 token 结构和签名算法",
  "related_pages": ["auth-module", "token-service"],
  "version": "1.0"
}
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `name` | 唯一标识符，用于 source_ref 引用 |
| `source_type` | 文档类型：api_doc/rfc/spec/design_doc/manual/other |
| `source_path` | 原始文件路径（会被复制到 `raw/sources/`） |
| `description` | 文档摘要 |
| `related_pages` | 关联的 Wiki 页面列表 |
| `version` | 文档版本（可选） |

原始文件存储在 `raw/sources/`，注册信息保存在 `.meta/source_registry.json`。Agent 应在导入后使用 `write_doc_file`（`page_type: "source"`）在 `wiki/sources/` 生成摘要页面。

## retract_source — 撤回外部文档

当外部文档过期或不再适用时撤回：

```json
{"source_name": "rfc-7519-jwt", "mode": "flag_stale"}
```

两种撤回模式：

| 模式 | 行为 |
|------|------|
| `flag_stale` | 在 `source_registry.json` 中标记为 retracted，保留原文件，相关页面不受影响 |
| `remove_refs` | 删除原文件，并从所有 wiki/notes 页面中清理 `[^src:name:range]` 引用和 frontmatter 中的 source_ref 字段 |

## batch_ingest — 批量导入

一次调用处理多个笔记或外部文档，减少 Agent 往返次数：

```json
{
  "items": [
    {"item_type": "note", "note_type": "decision", "title": "选择 PostgreSQL", "content": "...", "related_modules": ["database"]},
    {"item_type": "note", "note_type": "pitfall", "title": "连接池超时", "content": "...", "severity": "high"},
    {"item_type": "source", "source_type": "api_doc", "source_path": "/path/to/api.md", "name": "payment-api"}
  ]
}
```

也支持 `items_file` 参数传入 JSON 文件路径，适合大批量导入。所有项目处理完毕后统一重建索引和日志。

## flag_issue — 标记质量问题

发现 Wiki 中的质量问题时标记到 `.meta/issues.json`：

```json
{
  "issue_type": "broken_link",
  "page_path": "wiki/modules/auth.md",
  "severity": "error",
  "description": "链接指向不存在的页面 modules/legacy-auth.md"
}
```

### issue_type 可选值

| 类型 | 说明 |
|------|------|
| `broken_link` | 断链 |
| `missing_doc` | 缺少文档 |
| `inconsistent` | 文档与代码不一致 |
| `outdated` | 文档过期 |
| `orphan` | 孤立页面 |

每个 issue 使用 FNV-1a 哈希生成稳定 ID（基于 `type::page_path`），重复标记会自动增加 `occurrences` 计数并更新时间戳。问题严重级别（error/warning/info）直接影响 health score。

## lint_wiki — 文档一致性检查

定期运行检查文档与代码是否同步：

```json
{"checks": ["stale_refs", "broken_links", "orphan_pages", "missing_aliases", "stale_sources"]}
```

### 9 项检查

**原有 5 项：**

1. **过时引用** — 文档引用的组件在代码中已不存在
2. **断链** — 文档间的交叉引用指向不存在的文件
3. **未文档化组件** — 代码中有组件但文档未覆盖
4. **循环依赖** — 模块之间存在循环引用
5. **覆盖率** — 统计文档对组件的覆盖比例

**LLM Wiki 新增 4 项：**

6. **孤立页面**（`orphan_pages`）— 没有任何页面链接到的孤立页面
7. **无出链**（`no_outlinks`）— 没有链接到任何其他页面的死端页面
8. **缺少别名**（`missing_aliases`）— 实体页面缺少 aliases 声明
9. **过期外部源**（`stale_sources`）— 引用了已撤回（retracted）外部文档的页面

### Health Score

`lint_wiki` 返回 `health_score`（0-100），计算方式为：

```
health_score = 100 - Σ(error×10 + warning×3 + info×1)
```

`index.md` 顶部也会展示当前健康分数。建议在增量更新后或定期执行，保持文档健康度。
