# CodeWiki-CN LLM Wiki 知识层扩展方案 v2

## 1. 背景与目标

### 1.1 业务场景

开发人员在设计新需求时需要从三个知识域获取上下文：

| 知识域 | 来源 | 当前支持 |
|--------|------|----------|
| 现有实现 | 代码库本身 | 已支持（module 文档 + 依赖图 + 组件读取） |
| 历史踩坑 | 开发过程中积累 + 历史文档批量导入 | 部分支持（notes/ 扁平目录，5 种固定类型） |
| 第三方系统 | 依赖的 SDK/API 文档（PDF/MD/DOCX） | 不支持 |

消费者为 AI Agent（CodeBuddy/Cursor 等 IDE），通过 MCP 协议查询知识库辅助方案设计。

### 1.2 参考原型

本方案综合参考了两个项目的 LLM Wiki 实现：

**[nashsu/llm_wiki](https://github.com/nashsu/llm_wiki)**（Tauri 桌面应用）：提供了 Entity/Concept/Source/Comparison/Synthesis 等页面类型、结构化目录、purpose.md 意图文档、Review 审阅系统等设计模式。

**[Tencent/WeKnora](https://github.com/Tencent/WeKnora)**（Go 后端 + Vue 前端，v0.7.0）：提供了经 40,000 文档验证的生产级实践，关键借鉴包括：

- **Aliases（别名）**：每个页面维护别名/缩写/翻译列表，解决"UserService = 用户服务 = USvc"的交叉引用问题
- **Chunk-level 引用**（chunk_refs）：追溯到源文件的具体行号范围，而非仅文档级别
- **三档提取粒度**（focused/standard/exhaustive）：控制 Agent 提取多少 entity/concept
- **统一分类规划**：批量将页面分类到目录树，避免 Agent 每次独立决策导致目录混乱
- **源文件撤回**（retraction）：删除源文档时精确移除仅来源于该文档的内容
- **Issue 追踪 + Health Score**：wiki 质量度量和问题跟踪系统
- **Jaccard 预过滤去重**：在 LLM 去重前用 bigram 相似度预筛选，防止大规模知识库上的幻觉合并
- **`[[slug|display]]` wiki-link 语法**：比纯 markdown link 更健壮的互链语法，带 forbidden spans 保护

### 1.3 设计原则

- **纯工具链不变**：CodeWiki-CN 保持 MCP 工具服务器定位，不引入 LLM API。Agent 负责推理和生成，MCP 负责存储、索引、检索。
- **直接结构化**：不保留扁平兼容，所有 wiki 直接使用 structured 目录布局。
- **File Side-Channel 不变**：大数据仍走磁盘文件 + 紧凑摘要返回。
- **WeKnora 验证过的模式优先**：优先采用 WeKnora 在 40K 文档规模下验证过的实践（aliases、chunk_refs、taxonomy planning、retraction）。

---

## 2. 目录结构

```
repowiki/
├── purpose.md                  # 项目意图文档（用户 + Agent 共同维护）
├── schema.yaml                 # 页面类型路由表 + 文档约定 + 提取粒度配置
├── wiki/
│   ├── index.md                # 内容目录（按类型分组，自动维护）
│   ├── log.md                  # 操作日志（追加写入）
│   ├── overview.md             # 全局架构概述
│   ├── modules/                # 模块文档（现有，从根目录移入）
│   │   └── <module_name>.md
│   ├── entities/               # 关键类/接口/数据模型/API 端点
│   │   └── <entity_name>.md
│   ├── concepts/               # 设计模式/架构理念/领域概念
│   │   └── <concept_name>.md
│   ├── sources/                # 第三方文档摘要
│   │   └── <source_name>.md
│   ├── comparisons/            # 方案对比/技术选型分析
│   │   └── <comparison_name>.md
│   └── queries/                # 方案设计决策记录（含推理过程）
│       └── <query_name>.md
├── raw/
│   └── sources/                # 第三方文档原文（Agent 提取后的文本）
│       └── <source_name>.<ext>
├── notes/                      # 知识笔记（扩展子类型）
│   └── YYYY-MM-DD-slug.md
└── .meta/
    ├── metadata.json           # 生成基线（commit + timestamp）
    ├── module_tree.json        # 模块聚类层次
    ├── first_module_tree.json  # 初始聚类快照
    ├── symbol_map.json         # PascalCase -> 源文件映射
    ├── source_registry.json    # 第三方源文件注册表
    └── issues.json             # Wiki 质量问题追踪
```

### 2.1 与现有结构的差异

| 变更 | 说明 |
|------|------|
| 模块文档移入 `wiki/modules/` | 根目录不再放置 `.md` 文件 |
| 新增 `wiki/entities/` 等子目录 | 6 种页面类型各有目录 |
| 新增 `raw/sources/` | 第三方文档原文存储 |
| 新增 `.meta/source_registry.json` | 源文件索引 |
| 新增 `.meta/issues.json` | 质量问题追踪 |
| 新增 `purpose.md` | 项目意图文档 |
| `index.md`/`log.md`/`overview.md` 移入 `wiki/` | 统一管理 |

---

## 3. Schema 扩展设计

### 3.1 schema.yaml 新增字段

```yaml
# === 页面类型路由表 ===
page_types:
  module:
    directory: "wiki/modules"
    description: "代码模块文档，描述一个功能模块的架构、组件和依赖"
    required_sections:
      - "Architecture Overview"
      - "Component Responsibilities"
      - "Cross-References"

  entity:
    directory: "wiki/entities"
    description: "关键类、接口、数据模型、API 端点的独立文档"
    required_sections:
      - "职责描述"
      - "公开 API"
      - "使用示例"
      - "依赖关系"

  concept:
    directory: "wiki/concepts"
    description: "设计模式、架构理念、领域概念的文档"
    required_sections:
      - "概念定义"
      - "适用场景"
      - "在本项目中的应用"

  source:
    directory: "wiki/sources"
    description: "第三方文档（SDK/API/框架文档）的摘要"
    required_sections:
      - "文档概述"
      - "关键 API/概念"
      - "与本项目相关的部分"

  comparison:
    directory: "wiki/comparisons"
    description: "方案对比、技术选型分析"
    required_sections:
      - "背景与目标"
      - "候选方案"
      - "对比分析"
      - "结论与决策"

  query:
    directory: "wiki/queries"
    description: "方案设计决策记录，包含推理过程和权衡"
    required_sections:
      - "问题描述"
      - "调研过程"
      - "方案权衡"
      - "决策结论"

# === 提取粒度配置（参考 WeKnora 三档粒度） ===
extraction_granularity: "standard"
# focused: 每个源文件提取 3-7 个核心 entity/concept
# standard: 平衡提取，覆盖主要实体和概念（默认）
# exhaustive: 穷举提取，不遗漏任何命名实体

# === Wiki Link 语法配置 ===
wiki_link_syntax: true
# true: 使用 [[slug|display]] 语法（WeKnora 风格）
# false: 使用标准 [display](path.md) 语法（现有风格）
```

### 3.2 Frontmatter 规范（所有页面类型通用）

```yaml
---
type: Entity                    # Module | Entity | Concept | Source | Comparison | Query
title: "UserService"
aliases: ["用户服务", "USvc"]   # 别名/缩写/翻译（参考 WeKnora aliases）
description: "用户注册、认证、积分管理服务"
tags: [user, auth, points]
created: "2026-07-19"
updated: "2026-07-19"
---
```

**各类型专属字段：**

```yaml
# Entity 专属
category: "class"               # class | interface | model | endpoint

# Concept 专属
domain: "architecture"          # architecture | design_pattern | domain

# Source 专属
origin: "https://redis.io/docs/management/sentinel/"
version: "7.2"
format: "markdown"

# Comparison 专属
decision: "Redis Sentinel"      # 最终选择

# Query 专属
status: "decided"               # draft | decided | superseded
decided_at: "2026-07-19"

# Note（pitfall/known_issue/workaround）专属
severity: "high"                # critical | high | medium | low
root_cause: "并发问题"
```

### 3.3 Source Refs 和 Chunk Refs（参考 WeKnora）

每个 wiki 页面可在正文中标注内容来源，使用内联标注语法：

```markdown
## 故障转移机制

Sentinel 通过 quorum 投票决定主从切换[^src:redis-sentinel-v7:45-78]。
当主节点在 `down-after-milliseconds` 内无响应时，Sentinel 将其标记为 SDOWN[^src:redis-sentinel-v7:82-95]。
```

`source_refs` 和 `chunk_refs` 在 frontmatter 中汇总：

```yaml
source_refs:
  - "redis-sentinel-v7"          # 引用了哪些源文件
chunk_refs:
  - "redis-sentinel-v7:45-78"    # 具体引用了哪些行号范围
  - "redis-sentinel-v7:82-95"
```

**Agent 行为**：Agent 在生成 wiki 页面时，用 `[^src:<source_name>:<line_range>]` 标注事实来源。MCP 工具在写入时自动从正文解析并填充 frontmatter 的 `source_refs` 和 `chunk_refs`。

### 3.4 purpose.md 规范

```markdown
# 项目文档目的

## 文档关注范围
- 后端服务的架构设计和模块职责
- 核心业务流程的实现细节
- 第三方依赖的使用方式

## 关键技术决策背景
- 选择 PostgreSQL 因为需要 JSONB 支持
- 使用 Redis Sentinel 而非 Cluster 因为规模限制

## 文档重点覆盖
- 认证和授权流程
- 消息队列的消费逻辑
- 数据同步机制

## 不在文档范围内
- 前端 UI 实现
- 运维部署脚本
```

### 3.5 路径解析（统一入口）

```python
def resolve_wiki_path(output_dir: str, schema: dict) -> dict:
    """所有 wiki 文件路径的唯一权威来源"""
    wiki = os.path.join(output_dir, "wiki")
    paths = {
        "modules":      os.path.join(wiki, "modules"),
        "entities":     os.path.join(wiki, "entities"),
        "concepts":     os.path.join(wiki, "concepts"),
        "sources":      os.path.join(wiki, "sources"),
        "comparisons":  os.path.join(wiki, "comparisons"),
        "queries":      os.path.join(wiki, "queries"),
        "notes":        os.path.join(output_dir, "notes"),
        "raw_sources":  os.path.join(output_dir, "raw", "sources"),
        "index":        os.path.join(wiki, "index.md"),
        "log":          os.path.join(wiki, "log.md"),
        "overview":     os.path.join(wiki, "overview.md"),
        "schema":       os.path.join(output_dir, "schema.yaml"),
        "purpose":      os.path.join(output_dir, "purpose.md"),
    }
    # 从 schema.page_types 覆盖目录（用户可自定义）
    for ptype, config in schema.get("page_types", {}).items():
        if ptype in paths:
            paths[ptype] = os.path.join(output_dir, config["directory"])
    return paths
```

---

## 4. MCP 工具变更详设

### 4.1 `write_doc_file` 扩展

**新增参数：**

```json
{
  "page_type": {
    "type": "string",
    "enum": ["module", "entity", "concept", "source", "comparison", "query"],
    "description": "页面类型。文件自动路由到对应目录。默认 module。"
  },
  "frontmatter_extra": {
    "type": "object",
    "description": "额外 frontmatter 字段（aliases、category、origin、severity 等），合并到自动生成的 frontmatter。"
  }
}
```

**路由逻辑：**

```python
def _resolve_doc_path(filename, page_type, output_dir, schema):
    paths = resolve_wiki_path(output_dir, schema)
    target_dir = paths.get(page_type, paths["modules"])
    # filename 可含子目录前缀（如 "entities/UserService.md"）
    # 如果已含则直接使用，否则拼接到 target_dir
    if "/" in filename or "\\" in filename:
        return Path(output_dir) / filename
    return Path(target_dir) / filename
```

**Source Refs 自动解析：**

写入时从正文中提取 `[^src:<name>:<range>]` 标注，自动填充 frontmatter 的 `source_refs` 和 `chunk_refs`：

```python
def _extract_source_refs(content: str) -> tuple[list[str], list[str]]:
    """从正文中提取源文件引用和行号引用"""
    pattern = r'\[\^src:([^:]+):(\d+-\d+)\]'
    source_refs = set()
    chunk_refs = []
    for match in re.finditer(pattern, content):
        source_name, line_range = match.groups()
        source_refs.add(source_name)
        chunk_refs.append(f"{source_name}:{line_range}")
    return sorted(source_refs), chunk_refs
```

**Wiki-link 注入（参考 WeKnora linkifyContent）：**

当 `schema.wiki_link_syntax: true` 时，写入后自动扫描正文中的标识符，替换为 `[[slug|display]]` 语法。保护区域：fenced code blocks、inline code、现有 wiki links、markdown links、images、HTML comments。

```python
def _inject_wiki_links(content: str, slug_index: dict, schema: dict) -> str:
    """
    将正文中出现的已知标识符替换为 wiki-link。
    slug_index: {display_name: slug} 来自所有页面的 aliases + title。
    按 display_name 长度降序匹配（长者优先，参考 WeKnora）。
    每个 ref 最多出现一次链接。
    """
```

**Frontmatter 生成逻辑：**

```python
def _build_frontmatter(filename, page_type, content, session, schema, extra=None):
    fm = {
        "type": page_type.capitalize(),
        "title": _derive_title(filename),
        "aliases": extra.get("aliases", []),  # 来自 frontmatter_extra
        "description": _extract_description(content),  # 首段非标题非代码
        "tags": _derive_tags(filename, page_type, schema),
        "created": today(),
        "updated": today(),
    }
    # 类型专属字段
    if page_type == "module":
        fm["source_files"] = _match_module_sources(filename, session.module_tree)
    elif page_type == "source":
        fm["origin"] = extra.get("origin", "")
        fm["version"] = extra.get("version", "")
        fm["format"] = extra.get("format", "")
    # 源引用
    source_refs, chunk_refs = _extract_source_refs(content)
    fm["source_refs"] = source_refs
    fm["chunk_refs"] = chunk_refs
    # 合并 frontmatter_extra 中的其他字段
    for k, v in (extra or {}).items():
        if k not in fm:
            fm[k] = v
    return fm
```

### 4.2 `edit_doc_file` 扩展

无 interface 变更。路径解析自动使用新的 `_resolve_doc_path()`。编辑后自动重新解析 `source_refs`/`chunk_refs`。

### 4.3 `ingest_note` 扩展

**新增 note 子类型：**

```json
{
  "note_type": {
    "enum": ["decision", "lesson", "architecture", "bug_fix", "general",
             "pitfall", "known_issue", "workaround"]
  }
}
```

**新增参数：**

```json
{
  "severity": {
    "type": "string",
    "enum": ["critical", "high", "medium", "low"],
    "description": "严重程度（pitfall/known_issue 有效）"
  },
  "root_cause": {
    "type": "string",
    "description": "根因分类（pitfall 有效）"
  },
  "source_ref": {
    "type": "string",
    "description": "关联的第三方源文件标识"
  },
  "aliases": {
    "type": "array",
    "items": { "type": "string" },
    "description": "笔记别名，便于搜索命中"
  }
}
```

**扩展 Frontmatter：**

```yaml
---
type: pitfall
title: "Redis Sentinel 主从切换延迟导致写入丢失"
aliases: ["Sentinel 切换丢数据", "主从延迟写入失败"]
date: 2026-07-19
severity: high
root_cause: "并发问题"
related_modules: ["cache", "message_queue"]
related_components: ["src/cache/sentinel.py::SentinelClient"]
source_ref: "redis-sentinel-docs-v7"
chunk_refs: ["redis-sentinel-docs-v7:120-145"]
tags: [redis, sentinel, 并发, 数据丢失]
---
```

### 4.4 `ingest_source` 新工具

存储第三方文档并注册到源文件索引。

```json
{
  "type": "object",
  "properties": {
    "session_id":   { "type": "string" },
    "output_dir":   { "type": "string" },
    "source_name":  { "type": "string", "description": "源文件唯一标识，如 'redis-sentinel-v7'" },
    "origin":       { "type": "string", "description": "来源信息（URL/包名/文档名）" },
    "version":      { "type": "string" },
    "format":       { "type": "string", "enum": ["pdf", "markdown", "docx", "text"] },
    "content":      { "type": "string", "description": "提取的文本内容" },
    "content_file": { "type": "string", "description": "替代 content 的文件路径" },
    "raw_file":     { "type": "string", "description": "原始文件路径，复制到 raw/sources/ 保存" },
    "aliases":      { "type": "array", "items": { "type": "string" }, "description": "源文档别名" }
  },
  "required": ["source_name", "origin", "format"]
}
```

**处理流程：**

```
1. 解析 output_dir
2. 创建 raw/sources/ 目录（如不存在）
3. 如果提供 raw_file，复制到 raw/sources/{source_name}.{ext}
4. 将 content/content_file 注册到 .meta/source_registry.json
5. 将内容写入搜索索引（source 类型，BM25）
6. append_log("ingest_source", source_name)
7. rebuild_index()
```

**source_registry.json：**

```json
{
  "sources": {
    "redis-sentinel-v7": {
      "origin": "https://redis.io/docs/management/sentinel/",
      "version": "7.2",
      "format": "markdown",
      "aliases": ["Redis Sentinel 文档", "哨兵模式文档"],
      "raw_path": "raw/sources/redis-sentinel-v7.md",
      "ingested_at": "2026-07-19T10:30:00+08:00",
      "content_hash": "sha256:abc123...",
      "char_count": 15420,
      "summary_page": "wiki/sources/redis-sentinel-v7.md",
      "cited_by": [
        "wiki/modules/cache_module.md",
        "notes/2026-07-19-redis-pitfall.md"
      ]
    }
  }
}
```

**返回值：**

```json
{
  "status": "ingested",
  "source_name": "redis-sentinel-v7",
  "raw_path": "raw/sources/redis-sentinel-v7.md",
  "char_count": 15420,
  "index_updated": true
}
```

### 4.5 `retract_source` 新工具（参考 WeKnora retraction）

删除第三方源文件并清理引用。

```json
{
  "type": "object",
  "properties": {
    "session_id":   { "type": "string" },
    "output_dir":   { "type": "string" },
    "source_name":  { "type": "string" },
    "mode": {
      "type": "string",
      "enum": ["remove_refs", "flag_stale"],
      "description": "remove_refs=从引用页面中移除仅来源于此文档的内容；flag_stale=仅标记为过时（写入 issues.json）。默认 flag_stale。"
    },
    "dry_run": { "type": "boolean", "description": "预览变更不执行" }
  },
  "required": ["source_name"]
}
```

**处理逻辑：**

```
1. 从 source_registry.json 获取 cited_by 列表
2. 扫描引用页面的 source_refs 和 chunk_refs：
   a. 如果某页面的 source_refs 仅包含此源文件 → 整页标记为 stale
   b. 如果某页面还引用了其他源 → 仅移除引用此源的 chunk_refs
3. mode=flag_stale: 将受影响页面写入 issues.json（type: "stale_source"）
4. mode=remove_refs: 实际编辑受影响页面，移除相关引用
5. 从 source_registry.json 中删除条目
6. 删除 raw/sources/ 中的文件（移入 .trash/）
7. append_log("retract_source", source_name)
```

### 4.6 `batch_ingest` 新工具

```json
{
  "type": "object",
  "properties": {
    "session_id":  { "type": "string" },
    "output_dir":  { "type": "string" },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "kind":        { "type": "string", "enum": ["note", "source"] },
          "title":       { "type": "string" },
          "content":     { "type": "string" },
          "content_file":{ "type": "string" },
          "note_type":   { "type": "string" },
          "source_name": { "type": "string" },
          "origin":      { "type": "string" },
          "format":      { "type": "string" },
          "metadata":    { "type": "object", "description": "额外字段（severity、aliases 等）" }
        },
        "required": ["kind"]
      },
      "maxItems": 50
    },
    "items_file":  { "type": "string", "description": "替代 items 的 JSON 文件路径" }
  },
  "required": ["items"]
}
```

**处理流程：**

```
1. 解析 items（或从 items_file 读取）
2. 串行处理每个 item：
   a. kind=note -> ingest_note 内部函数
   b. kind=source -> ingest_source 内部函数
3. 统一 rebuild_index() + append_log()（批量只触发一次）
4. 返回汇总结果（含 succeeded/failed 计数）
```

### 4.7 `query_wiki` 扩展

**新增参数：**

```json
{
  "type_filter": {
    "type": "string",
    "enum": ["module", "entity", "concept", "source", "comparison", "query", "note", "all"],
    "description": "按页面类型过滤。默认 all。"
  },
  "include_sources": {
    "type": "boolean",
    "description": "是否包含第三方文档摘要和原文。默认 true。"
  }
}
```

**scope 参数语义扩展：**

```
scope="auth"           -> 匹配 wiki/modules/auth.md（现有行为）
scope="wiki/entities"  -> 匹配 wiki/entities/ 下所有文件
scope="notes"          -> 匹配 notes/ 下所有文件
scope="wiki/sources"   -> 匹配第三方文档摘要
```

**搜索索引 source 字段：**

| 值 | 含义 |
|---|------|
| `"doc"` | wiki/ 下所有页面（modules、entities、concepts 等） |
| `"note"` | notes/ 下的笔记 |
| `"source"` | raw/sources/ 下的第三方文档原文 |

**Aliases 搜索增强：**

搜索时，查询词同时匹配页面标题和 aliases 字段。实现方式：在 `_build_indexable_text()` 中将 aliases 以 3x boost 加入索引文本（与 tags 同级）。

### 4.8 `get_prompt` 扩展

**新增 prompt_type：**

| prompt_type | 描述 | 变量 |
|-------------|------|------|
| `entity_page` | 指导 Agent 生成 entity 页面 | `entity_name`, `page_type_constraints`, `granularity` |
| `concept_page` | 指导 Agent 生成 concept 页面 | `concept_name`, `page_type_constraints` |
| `source_summary` | 指导 Agent 为第三方文档生成摘要 | `source_name`, `page_type_constraints` |
| `comparison_page` | 指导 Agent 生成对比分析 | `topic`, `page_type_constraints` |
| `query_page` | 指导 Agent 记录设计决策 | `question`, `page_type_constraints` |
| `taxonomy_plan` | 指导 Agent 批量规划页面分类（参考 WeKnora） | `candidate_pages`, `existing_folders` |
| `extraction_scan` | 指导 Agent 从源文件提取候选 entity/concept | `source_content`, `granularity`, `existing_pages` |

**Schema 约束注入增强：**

```python
def _build_schema_constraints(schema: dict, output_dir: str) -> str:
    constraints = []
    # 现有：required_sections, dimensions, line constraints, OKF
    # 新增：page_types 路由表
    for ptype, config in schema.get("page_types", {}).items():
        constraints.append(
            f"### {ptype}\n"
            f"- 目录: {config['directory']}/\n"
            f"- 必需章节: {', '.join(config.get('required_sections', []))}"
        )
    # 新增：提取粒度指引
    granularity = schema.get("extraction_granularity", "standard")
    constraints.append(f"## 提取粒度: {granularity}")
    # 新增：purpose.md 内容注入
    purpose_path = Path(output_dir) / "purpose.md"
    if purpose_path.exists():
        text = purpose_path.read_text(encoding="utf-8")
        if len(text) > 2000:
            text = text[:2000] + "\n...(truncated)"
        constraints.append(f"## 项目文档目的\n{text}")
    return "\n\n".join(constraints)
```

### 4.9 `lint_wiki` 扩展

**新增检查项：**

```json
{
  "checks": {
    "enum": [
      "all", "stale_refs", "undocumented", "broken_links", "cycles", "coverage",
      "orphan_pages", "no_outlinks", "missing_aliases", "stale_sources"
    ]
  }
}
```

| 新检查项 | 严重度 | 逻辑 |
|----------|--------|------|
| `orphan_pages` | warning | 无任何入链的页面（参考 WeKnora orphan_page） |
| `no_outlinks` | info | 不链接到其他页面的页面 |
| `missing_aliases` | info | 标题含 CJK 但 aliases 为空（或缺少英文名），或反之 |
| `stale_sources` | error | source_refs 引用了不在 source_registry 中的源文件 |

**Health Score（参考 WeKnora）：**

```python
def compute_health_score(issues: list) -> int:
    """0-100 分，扣分项："""
    score = 100
    weights = {
        "error": 10,       # 每个 error -10
        "warning": 3,      # 每个 warning -3
        "info": 1,         # 每个 info -1
        "orphan": 2,       # 每个孤立页 -2
        "stale_source": 8, # 每个过时源 -8
    }
    for issue in issues:
        score -= weights.get(issue["check"], 1)
    return max(0, score)
```

### 4.10 `flag_issue` 新工具（参考 WeKnora wiki_flag_issue）

```json
{
  "type": "object",
  "properties": {
    "session_id":  { "type": "string" },
    "output_dir":  { "type": "string" },
    "page_path":   { "type": "string", "description": "问题页面路径（相对 output_dir）" },
    "issue_type":  {
      "type": "string",
      "enum": ["mixed_entity", "contradictory_facts", "out_of_date",
               "stale_source", "missing_cross_ref", "empty_content"]
    },
    "description": { "type": "string" },
    "affected_pages": {
      "type": "array",
      "items": { "type": "string" },
      "description": "关联的其他页面"
    }
  },
  "required": ["page_path", "issue_type", "description"]
}
```

**issues.json 结构：**

```json
{
  "issues": {
    "abc123": {
      "id": "abc123",
      "page_path": "wiki/entities/UserService.md",
      "issue_type": "contradictory_facts",
      "description": "缓存策略描述与 cache_module.md 矛盾",
      "affected_pages": ["wiki/modules/cache_module.md"],
      "status": "open",
      "created_at": "2026-07-19T10:30:00+08:00",
      "resolved_at": null
    }
  }
}
```

---

## 5. 数据模型变更

### 5.1 搜索索引扩展

`search_index` 表无 schema 变更，`source` 字段新增值 `"source"`：

```
doc_key 示例：
  "wiki/modules/auth_module.md"           source="doc"
  "wiki/entities/UserService.md"          source="doc"
  "notes/2026-07-19-redis-pitfall.md"     source="note"
  "raw/sources/redis-sentinel-v7.md"      source="source"
```

**`_build_indexable_text()` 扩展**（签名兼容）：

```python
def _build_indexable_text(content: str, page_type: str | None = None) -> str:
    """保持单参数向后兼容。page_type 提供时额外 boost 类型专属字段。"""
    parts = []
    fm = _parse_frontmatter(content)

    # 现有：tags 3x, description 2x, title 2x
    if fm.get("tags"):
        for tag in fm["tags"]:
            parts.extend([str(tag)] * 3)
    if fm.get("description"):
        parts.extend([fm["description"]] * 2)
    if fm.get("title"):
        parts.extend([fm["title"]] * 2)

    # 新增：aliases 3x boost（参考 WeKnora）
    if fm.get("aliases"):
        for alias in fm["aliases"]:
            parts.extend([alias] * 3)

    # 新增：类型专属字段 boost
    if page_type == "entity" and fm.get("category"):
        parts.extend([fm["category"]] * 2)
    elif page_type == "source" and fm.get("origin"):
        parts.extend([fm["origin"]] * 2)
    elif page_type == "note" and fm.get("severity"):
        severity_boost = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        weight = severity_boost.get(fm["severity"], 1)
        parts.extend([fm["severity"]] * weight)

    # body
    parts.append(_strip_frontmatter(content))
    return "\n".join(parts)
```

### 5.2 index.md 重建

`rebuild_index()` 递归扫描 `wiki/` 子目录，按 page_type 分区展示：

```markdown
# 项目文档索引

> 自动生成于 2026-07-19T15:30:00+08:00 | Health Score: 87/100

## 架构概述
| 文档 | 说明 |
|------|------|
| [全局架构](overview.md) | 系统整体架构和设计决策 |

## 模块文档
| 文档 | 说明 |
|------|------|
| [认证模块](modules/auth_module.md) | 用户认证和授权流程 |

## 实体
| 文档 | 类型 | 别名 | 说明 |
|------|------|------|------|
| [UserService](entities/UserService.md) | class | 用户服务 | 用户管理服务 |

## 概念
| 文档 | 说明 |
|------|------|
| [事件驱动架构](concepts/event_driven.md) | 异步消息处理的设计模式 |

## 第三方文档
| 文档 | 来源 | 版本 | 说明 |
|------|------|------|------|
| [Redis Sentinel](sources/redis-sentinel-v7.md) | redis.io | 7.2 | Sentinel 高可用方案 |

## 方案对比
| 文档 | 决策 | 说明 |
|------|------|------|
| [消息队列选型](comparisons/mq_comparison.md) | RabbitMQ | RabbitMQ vs Kafka |

## 设计决策
| 文档 | 状态 | 说明 |
|------|------|------|
| [缓存策略](queries/cache_strategy.md) | decided | 多级缓存方案选型 |

## 知识笔记
| 标题 | 类型 | 日期 | 严重程度 | 文件 |
|------|------|------|----------|------|
| Redis 主从切换延迟 | pitfall | 2026-07-19 | high | [链接](../notes/2026-07-19-redis-pitfall.md) |

## 未解决问题 (3)
| 页面 | 类型 | 说明 |
|------|------|------|
| UserService | contradictory_facts | 缓存策略描述与 cache_module 矛盾 |
```

### 5.3 需修改的文件清单

```
doc_writer.py:        _safe_doc_path(), _build_okf_frontmatter(), _inject_crosslinks()
wiki_index.py:        rebuild_index(), append_log(), _EXCLUDED_FROM_INDEX
wiki_search.py:       build_full_index(), update_file(), _legacy_keyword_search()
cache.py:             build_search_index(), update_search_doc(), _build_indexable_text()
wiki_lint.py:         _check_stale_refs(), _check_broken_links() [改为 rglob]
knowledge_loop.py:    handle_ingest_note(), query_wiki handler
agents_md.py:         _build_section() [路径适配]
workspace_analyzer.py: _generate_overview() [路径适配]
server.py:            close_session handler, 新工具注册
schema_generator.py:  generate_schema() [新增 page_types, extraction_granularity]
prompt_server.py:     _build_schema_constraints(), _PROMPT_CATALOG
```

所有路径构造统一使用 `resolve_wiki_path()` 返回的映射。所有 `.glob("*.md")` 改为 `.rglob("*.md")`。所有链接解析从源文件所在目录计算相对路径。

---

## 6. Agent 工作流示例

### 6.1 方案设计：查询三个知识域

Agent 为"添加用户积分系统"做方案设计：

```
# 1. 查现有实现
query_wiki(query="用户 账户 积分", type_filter="module")

# 2. 查历史踩坑
query_wiki(query="积分 账户 扣减 并发", type_filter="note")

# 3. 查第三方文档
query_wiki(query="Redis Lua 原子操作 事务", scope="wiki/sources")

# 4. 查历史决策
query_wiki(query="缓存 策略 选型", type_filter="query")

# 5. 查相关实体
query_wiki(query="UserService 用户服务", type_filter="entity")
# aliases 确保 "用户服务" 和 "UserService" 都能命中
```

### 6.2 从第三方文档提取知识（参考 WeKnora 两阶段提取）

```
# 阶段 1：提取候选 entity/concept（get_prompt: extraction_scan）
get_prompt(
    prompt_type="extraction_scan",
    variables={
        "source_content": "...",  # Agent 读取的第三方文档内容
        "granularity": "standard",
        "existing_pages": "UserService, CacheManager, ..."
    }
)
# Agent 输出候选列表：[{name, slug, aliases, description}]

# 阶段 2：统一分类规划（get_prompt: taxonomy_plan）
get_prompt(
    prompt_type="taxonomy_plan",
    variables={
        "candidate_pages": "[{name: 'Sentinel', slug: 'sentinel', ...}]",
        "existing_folders": "cache, database, messaging"
    }
)
# Agent 输出每个候选页面的目录归属

# 阶段 3：逐个生成页面
write_doc_file(filename="sentinel.md", content="...", page_type="entity",
    frontmatter_extra={
        "aliases": ["哨兵模式", "Redis Sentinel"],
        "category": "concept"
    }
)
```

### 6.3 录入踩坑记录（边做边记）

```
ingest_note(
    title="Redis Pipeline 批量操作在 Sentinel 切换时部分失败",
    content="## 问题描述\n...\n## 根因\nSentinel 切换期间 pipeline 的写入\n[^src:redis-sentinel-v7:120-145]",
    note_type="pitfall",
    severity="high",
    root_cause="并发问题",
    aliases=["Pipeline 切换失败", "批量写入丢失"],
    source_ref="redis-sentinel-v7"
)
```

### 6.4 批量导入历史踩坑文档

```
batch_ingest(items_file="/path/to/exported_notes.json")
# JSON:
# [
#   {"kind": "note", "title": "...", "content": "...",
#    "note_type": "pitfall",
#    "metadata": {"severity": "high", "root_cause": "配置错误",
#                 "aliases": ["XX 问题", "YY 故障"]}},
#   ...
# ]
```

### 6.5 导入第三方文档 + 生成摘要

```
# 1. Agent 用自身 PDF 阅读能力解析文档
# 2. 存储源文件
ingest_source(
    source_name="redis-sentinel-v7",
    origin="https://redis.io/docs/management/sentinel/",
    version="7.2",
    format="markdown",
    content="...",
    raw_file="/path/to/redis-sentinel.md",
    aliases=["Redis Sentinel 文档", "哨兵模式文档"]
)

# 3. 获取摘要模板 + 生成摘要页面
get_prompt(prompt_type="source_summary", variables={"source_name": "redis-sentinel-v7"})
write_doc_file(
    filename="redis-sentinel-v7.md",
    content="...",
    page_type="source",
    frontmatter_extra={"origin": "redis.io", "version": "7.2"}
)
```

---

## 7. 实施阶段

### Phase 1: 基础设施（预计 3 天）

| 任务 | 涉及文件 | 说明 |
|------|----------|------|
| 新增 `page_router.py` | 新文件 | `resolve_wiki_path()`、`_resolve_doc_path()`、`_compute_link_path()` |
| 重写 `_safe_doc_path()` | `doc_writer.py` | 直接使用 `resolve_wiki_path()` 路由 |
| 扩展 `schema_generator.py` | 修改 | 生成 page_types 路由表、extraction_granularity、wiki_link_syntax |
| 扩展 `config.py` | 修改 | 新增 WIKI_DIR, RAW_DIR, ISSUES_FILENAME 等常量 |
| 所有 `.glob` → `.rglob` | 6 个文件 | 见 §5.3 清单 |
| 路径统一化 | 11 个文件 | 所有路径构造改用 `resolve_wiki_path()` |
| 链接解析适配 | `doc_writer.py`, `wiki_lint.py` | 从源文件目录计算相对路径 |

### Phase 2: 页面类型 + 新工具（预计 4 天）

| 任务 | 涉及文件 | 说明 |
|------|----------|------|
| 扩展 `write_doc_file` | `doc_writer.py` | page_type、frontmatter_extra、source_refs 解析 |
| 扩展 frontmatter 生成 | `doc_writer.py` | 6 种页面类型的 frontmatter 模板 |
| Wiki-link 注入 | `doc_writer.py` | `[[slug|display]]` 语法（可选） |
| 扩展 `ingest_note` | `knowledge_loop.py` | 新增 pitfall/known_issue/workaround + severity/root_cause/aliases |
| 实现 `ingest_source` | 新文件 `tools/source_ingest.py` | 第三方文档存储和注册 |
| 实现 `retract_source` | `source_ingest.py` | 源文件撤回 |
| 实现 `batch_ingest` | 新文件 `tools/batch_ingest.py` | 批量导入 |
| 实现 `flag_issue` | 新文件 `tools/issue_tracker.py` | 质量问题追踪 |
| 扩展 `get_prompt` | `prompt_server.py` | 7 个新 prompt_type + schema 约束注入 |

### Phase 3: 查询增强 + 质量系统（预计 3 天）

| 任务 | 涉及文件 | 说明 |
|------|----------|------|
| 扩展 `query_wiki` | `knowledge_loop.py` | type_filter、include_sources、scope 前缀 |
| Aliases 搜索增强 | `cache.py` | aliases 字段 3x boost |
| 扩展 BM25 索引 | `cache.py` | source 类型、doc_key 新路径 |
| 扩展 `_build_indexable_text()` | `cache.py` | 可选 page_type 参数 |
| 扩展 `lint_wiki` | `wiki_lint.py` | 4 个新检查项 + Health Score |
| `rebuild_index()` 重构 | `wiki_index.py` | 递归扫描 + 按类型分区 + Health Score 展示 |
| `agents_md.py` 适配 | `agents_md.py` | 链接路径适配 wiki/ 结构 |
| `workspace_analyzer.py` 适配 | `workspace_analyzer.py` | overview.md 路径兼容 |
| `close_session` 适配 | `server.py` | index/log 路径使用 wiki/ |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 搜索索引 doc_key 路径变更 | 旧索引失效 | Phase 1 路径统一化后自动 `build_full_index()` |
| `[[slug|display]]` 与现有 `[text](link)` 混用 | 链接风格不一致 | `wiki_link_syntax` 配置项控制；新增页面用 wiki-link，旧页面保持不变 |
| `retract_source` mode=remove_refs 误删内容 | 信息丢失 | 默认 mode=flag_stale；remove_refs 需 dry_run 确认 |
| batch_ingest 大文件内存压力 | OOM | 逐条串行 + content_file 旁路 |
| 提取粒度配置不生效 | Agent 提取过多/过少 entity | `extraction_scan` 提示模板硬编码粒度约束 |
| purpose.md 内容被恶意注入 | prompt 注入 | 读取时限制 2000 字 |

---

## 附录 A：llm_wiki vs WeKnora vs CodeWiki-CN 特性对照

| 特性 | llm_wiki | WeKnora | CodeWiki-CN (本方案) |
|------|----------|---------|---------------------|
| 页面类型 | 9 种（含 thesis/methodology/finding） | 7 种 | 6 种（module/entity/concept/source/comparison/query） |
| 目录结构 | 文件系统 | 数据库 + 虚拟文件夹 | 文件系统 |
| Aliases | 无 | frontmatter aliases | frontmatter aliases |
| Chunk-level 引用 | 无 | chunk_refs UUID | `[^src:name:range]` + chunk_refs |
| 源文件撤回 | 级联删除 | retraction prompt | retract_source 工具 |
| 提取粒度 | 无 | focused/standard/exhaustive | 同 WeKnora |
| 分类规划 | 每页独立 | 批量 taxonomy planning | taxonomy_plan prompt |
| 去重 | 内容+embedding | Jaccard 预过滤 + LLM | BM25 搜索预筛（轻量） |
| 互链语法 | `[[wikilink]]` | `[[slug|display]]` | `[[slug|display]]`（可选） |
| Issue 追踪 | Review items | wiki_page_issues | issues.json |
| Health Score | 无 | 0-100 | lint_wiki 扩展 |
| Wiki Boost | 无 | RAG 1.3x | BM25 frontmatter boost |
| 存储后端 | 文件系统 + LanceDB | PostgreSQL + Redis | 文件系统 + SQLite |
| LLM 集成 | 内置多 provider | 内置（通过 Go 后端） | 无（Agent 提供 LLM） |
