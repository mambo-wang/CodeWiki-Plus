# CodeWiki-CN vs codebase-memory-mcp 功能对齐研究报告

> 研究日期：2026-07-29
> 研究对象：
> - **CodeWiki-CN**（`D:\repos\CodeWiki-CN`）：Python MCP 服务器，tree-sitter 解析 + LLM 文档生成
> - **codebase-memory-mcp / CBM**（`D:\repos\codebase-memory-mcp-src`，二进制部署在 `D:\software\codebase-memory-mcp`）：纯 C MCP 服务器，tree-sitter + Hybrid LSP 知识图谱引擎
>
> 资料来源：两个项目的实际源码（CBM 已克隆完整源码到 `D:\repos\codebase-memory-mcp-src`，含 5604 个测试与 README/docs），不依赖任何猜测。

---

## 一、执行摘要（TL;DR）

| 维度 | CodeWiki-CN | CBM | 对齐难度 |
|------|-------------|-----|---------|
| 实现语言 | Python（pydantic + tree-sitter Python 绑定） | 纯 C，零依赖，单二进制 | 架构性差异 |
| 解析语言数 | 11（py/js/ts/tsx/java/kt/cs/c/cpp/php/go） | 158（vendored grammars） | 中（可补） |
| 类型解析 | 仅 tree-sitter 语法层 + 启发式 callee 解析 | tree-sitter + Hybrid LSP（10 种语言深度类型推断） | **高（架构性）** |
| 图存储 | SQLite（components/dependencies/routes/symbols/wiki_links） | SQLite（nodes/edges + FTS5 + 属性 JSON） | 中（schema 重设计） |
| 图查询 | 手写 BFS（`list_dependencies` / `analyze_impact`） | 完整 openCypher 子集（4803 行 cypher.c） | **高** |
| 全文搜索 | 自实现 BM25 + jieba（针对 wiki 文档/notes） | SQLite FTS5 + camelCase tokenizer（针对图节点） | 低 |
| 语义/向量搜索 | **无** | nomic-embed-code 768d int8 内嵌 + 11 信号融合 | **高（需引入模型）** |
| 社区检测 | LLM 聚类（`cluster_modules.py`，提示词驱动） | Leiden 多层算法（store.c 5987-6308 行） | 中（可移植算法） |
| 跨服务分析 | Route 节点 + HTTP/MQ 匹配（已借鉴 CBM） | Route + Channel + gRPC/GraphQL/tRPC + CROSS_* 双向边 + DATA_FLOWS | 中（已起步） |
| 复杂度指标 | 仅 TS analyzer 有占位 `'complexity': 1` | cyclomatic / cognitive / loop_depth / transitive_loop_depth / linear_scan_in_loop / alloc_in_loop / recursion_in_loop | 中 |
| 增量索引 | 文件指纹（mtime/sha）+ session 缓存 | file_hashes 表 + git watcher 守护进程 + zstd 团队共享 artifact | 中 |
| 主要交付物 | **Markdown Wiki 文档** + 知识库 notes | **结构化图查询结果**（不生成文档） | 不可对齐（产品定位不同） |

**核心结论**：

1. **不能也不应该完全对齐**。两者产品定位根本不同：CBM 是"结构分析后端"（README 第 239 行原话："structural analysis backend — it does not include an LLM"），CodeWiki-CN 是"LLM Wiki 生成器 + 知识库"。CBM 把 LLM 智能层留给上游 Agent，CodeWiki-CN 自己内嵌 LLM 调用并产出文档。
2. **图查询/语义搜索/Hybrid LSP 是架构性差距**，无法在 Python 中简单"补齐"——CBM 的 Linux 内核 3 分钟索引（28M LOC）依赖 RAM-first C 管线、LZ4、Aho-Corasick、内嵌量化模型，Python 重写既不现实也不必要。
3. **可对齐的部分（推荐做）**：Cypher 子集查询、Leiden 社区检测、复杂度指标、dead-code 检测、DATA_FLOWS、CROSS_* 双向边、git-diff 影响映射、ADR 管理。这些是"算法/数据模型"层面的差距，Python 实现完全可行。
4. **正确策略**（与 `docs/codebase-memory-mcp跨服务分析-源码借鉴分析.md` 已有结论一致）：CBM 已安装时通过 MCP 调用其能力（CodeWiki 已有 `cbm_integration.py` 占位但未真正接通），未安装时用 CodeWiki 自己的轻量 Python 实现兜底。

---

## 二、codebase-memory-mcp 深度分析

### 2.1 项目定位与整体架构

CBM 是 DeusData 出品的纯 C 代码智能引擎，单二进制 ~270MB（含 158 个 tree-sitter grammar 与 nomic 嵌入模型）。README 第 17 行：

> "Full-indexes an average repository in milliseconds, the Linux kernel (28M LOC, 75K files) in 3 minutes. Answers structural queries in under 1ms."

源码目录结构（`D:\repos\codebase-memory-mcp-src\src`）：

```
src/
  main.c              入口（MCP stdio + CLI + install/update/config）
  daemon/             跨会话协调守护进程（IPC、watcher、UI 共享）
  mcp/                MCP 服务器（15 工具，JSON-RPC 2.0）
  cli/                43 个 Agent 客户端的安装/适配
  store/              SQLite 图存储 + Leiden 社区检测（store.c 6700+ 行）
  pipeline/           多 pass 索引管线（25+ 个 pass_*.c）
  cypher/             openCypher 子集（lexer/parser/planner/executor，4803 行）
  semantic/           nomic-embed-code 嵌入 + 11 信号融合
  simhash/            MinHash + LSH 近克隆检测
  discover/           文件发现（.gitignore / .cbmignore）
  watcher/            git 后台监听
  traces/             OTLP 运行时 trace 摄入
  ui/                 3D 图可视化（可选 UI 二进制）
internal/cbm/         vendored tree-sitter grammars（158 种语言）
```

### 2.2 15 个 MCP 工具（实测自源码）

`src/mcp/mcp.c` 第 347-654 行的 `TOOLS[]` 数组定义了 15 个工具（用户提到的 8 个是早期版本，最新源码已扩展到 15 个）：

| 工具 | 功能 | 关键参数 |
|------|------|---------|
| `index_repository` | 索引仓库；4 种模式 full/moderate/fast/cross-repo-intelligence | `repo_path`, `mode`, `target_projects`, `persistence` |
| `search_graph` | 三种搜索：BM25 全文 / 正则 name_pattern / 向量 semantic_query | `query`, `name_pattern`, `semantic_query[]`, `min_degree`, `fields[]` |
| `query_graph` | openCypher 子集查询，100k 行上限 | `query`, `project`, `graph: code\|missed` |
| `trace_path` | BFS 调用追踪，3 种模式 calls/data_flow/cross_service | `function_name`, `direction`, `depth(1-5)`, `mode`, `cursor` |
| `get_code_snippet` | 按 qualified_name 读源码 | `qualified_name`, `include_neighbors` |
| `get_graph_schema` | 节点/边统计、关系模式、属性定义 | `project` |
| `get_architecture` | 架构总览：languages/packages/routes/hotspots/boundaries/layers/**clusters**/cycles | `aspects[]`, `path` |
| `search_code` | 图增强 grep（去重到函数级、按结构重要性排序） | `pattern`, `mode: compact\|full\|files`, `path_filter` |
| `list_projects` | 列出已索引项目 | — |
| `delete_project` | 删除项目 | `project` |
| `index_status` | 索引状态 + 覆盖报告（parse_partial / skipped） | `project`, `verbose` |
| `check_index_coverage` | 路径级权威覆盖检查 | `paths[]`, `scopes[]` |
| `detect_changes` | git diff → 影响符号 + blast radius + 风险分级 | `scope`, `direction`, `depth`, `since` |
| `manage_adr` | 架构决策记录 CRUD | `mode: get\|update\|sections` |
| `ingest_traces` | 摄入运行时 trace 验证 HTTP_CALLS | `traces[]` |

### 2.3 图数据模型（SQLite Schema）

`src/store/store.c` 第 226-304 行：

```sql
CREATE TABLE nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project TEXT, label TEXT, name TEXT, qualified_name TEXT,
  file_path TEXT, start_line INTEGER, end_line INTEGER,
  properties TEXT DEFAULT '{}',          -- JSON 属性袋
  UNIQUE(project, qualified_name)
);
CREATE TABLE edges (
  id INTEGER PRIMARY KEY,
  project TEXT, source_id INTEGER, target_id INTEGER,
  type TEXT, properties TEXT DEFAULT '{}',
  url_path_gen TEXT GENERATED ALWAYS AS (json_extract(properties,'$.url_path')),
  local_name_gen TEXT GENERATED ALWAYS AS (...),
  UNIQUE(source_id, target_id, type, local_name_gen)
);
CREATE VIRTUAL TABLE nodes_fts USING fts5(name, qualified_name, label, file_path,
  content='', tokenize='unicode61 remove_diacritics 2');
```

**节点标签**（README 第 594 行）：`Project, Package, Folder, File, Module, Class, Function, Method, Interface, Enum, Type, Route, Resource`

**边类型**（README 第 598 行 + 源码补充）：`CONTAINS_PACKAGE/FOLDER/FILE, DEFINES, DEFINES_METHOD, IMPORTS, CALLS, HTTP_CALLS, ASYNC_CALLS, IMPLEMENTS, HANDLES, USAGE, CONFIGURES, WRITES, MEMBER_OF, TESTS, USES_TYPE, FILE_CHANGES_WITH, DATA_FLOWS, SIMILAR_TO, SEMANTICALLY_RELATED, EMITS, LISTENS_ON, CROSS_HTTP_CALLS, CROSS_ASYNC_CALLS, CROSS_CHANNEL, CROSS_GRPC_CALLS, CROSS_GRAPHQL_CALLS, CROSS_TRPC_CALLS, RESOLVED_CALLS`

### 2.4 关键高级能力（源码佐证）

#### 2.4.1 Leiden 社区检测（不是 Louvain）

`src/store/store.c` 第 5987-6308 行实现了完整的 **多层 Leiden 算法**（Traag, Waltman & van Eck 2019）：

- `leiden_move()`（第 6134 行）：local-moving 阶段，贪心移动节点到邻居社区
- `leiden_refine()`（第 6237 行）：refinement 阶段，将单例节点合并到最佳子社区（修复了单层 Louvain 的"内部不连通"缺陷）
- `leiden_relabel()`（第 6211 行）：标签压实
- `cbm_leiden()`（store.h 第 764 行）：暴露给 `get_architecture(aspects=["clusters"])`，resolution γ=1.0

README 第 178 行写的"Louvain community detection"是早期描述，**实际源码已是 Leiden**（注释明确写了 "Multi-level Leiden"）。

#### 2.4.2 语义/向量搜索（nomic-embed-code 内嵌）

`src/semantic/semantic.h` 第 35-36 行：

```c
/* 768 = nomic-embed-code embedding dimension. Matches PRETRAINED_DIM. */
enum { CBM_SEM_DIM = 768 };
```

`src/semantic/semantic.c` 第 443-450 行：先查预训练 nomic 向量（int8 量化，4x 内存效率），fallback 到 TF-IDF / Random Indexing。README 第 184 行说明 11 信号融合：

> "TF-IDF, RRI, API/Type/Decorator signatures, AST profiles, data flow, Halstead-lite, MinHash, module proximity, graph diffusion"

模型完全编译进二进制，**无 API key、无 Ollama、无 Docker**。

#### 2.4.3 Hybrid LSP（10 种语言深度类型解析）

README 第 691-712 行详述。这是 CBM 与一般 tree-sitter 工具的最大差异：tree-sitter 只给语法 AST，Hybrid LSP 在 C 层重新实现了主流语言服务器的类型解析算法（pyright/gopls/tsserver/Roslyn/JDT/rust-analyzer 兼容）：

- Python：dataclasses、Self、generics、@property、SQLAlchemy 2.0 Mapped[T]、Pydantic、isinstance narrowing、typing.cast
- TS/JS：generics、JSX 组件分发、JSDoc 推断、.d.ts、方法链返回类型传播
- C#：global usings、records、LINQ 方法语法、async Task<T> 解包
- Java：class hierarchies、overload matching、lambdas → functional interfaces
- Rust：impl 块、trait 方法、UFCS、derive 宏方法合成

源码：`src/pipeline/pass_lsp_cross.c`（1126 行）实现项目级跨文件类型解析，"per-package summary" 模式避免 O(D×F) 开销。

#### 2.4.4 跨服务/跨仓库分析

详见已有文档 `docs/codebase-memory-mcp跨服务分析-源码借鉴分析.md`。核心要点：

- **Route 节点**（`pass_route_nodes.c` 1231 行）：协议无关会合点，QN 格式 `__route__POST__/api/orders/{}`
- **路径规范化**（第 59-129 行）：`:id` / `{id}` / `<int:id>` / `${userId}` 全部归一为 `{}`
- **四阶段跨仓库匹配**（`pass_cross_repo.c` 1356 行）：HTTP / 异步消息 / Channel / gRPC-GraphQL-tRPC
- **双向边写入**：源/目标项目 DB 都写 CROSS_* 边
- **DATA_FLOWS 边**（第 590-914 行）：caller→handler 端到端数据流，含 `handler_params` 与 `caller_args`，可做参数级追踪

#### 2.4.5 复杂度与热路径分析

`src/pipeline/pass_complexity.c`（207 行）：

- 基础：cyclomatic、cognitive、loop_count、loop_depth
- **过程间传播**：`transitive_loop_depth`（沿 CALLS 边传播的最坏嵌套度数）、`recursive` 标志
- **热路径信号**：`linear_scan_in_loop`（循环内 find/contains/indexOf——隐藏的 O(n²)）、`alloc_in_loop`、`recursion_in_loop`、`unguarded_recursion`、`param_count`、`max_access_depth`

`query_graph` 描述（mcp.c 第 449 行）给了一个典型查询：

```cypher
MATCH (f:Function)
WHERE f.transitive_loop_depth >= 3 OR f.linear_scan_in_loop >= 1
RETURN f.qualified_name, f.transitive_loop_depth, f.linear_scan_in_loop
ORDER BY f.transitive_loop_depth DESC
```

#### 2.4.6 其他

- **MinHash + LSH 近克隆检测**（`pass_similarity.c` 353 行 + `simhash/minhash.h`）→ `SIMILAR_TO` 边带 Jaccard 分数
- **git history 耦合**（`pass_githistory.c`）→ `FILE_CHANGES_WITH` 边
- **OTLP trace 摄入**（`src/traces/`）→ 运行时数据补静态分析盲区
- **K8s/Dockerfile/Kustomize 索引**（`pass_k8s.c` / `pass_infrascan.c`）→ Resource/Module 节点
- **Cypher 引擎**（`src/cypher/cypher.c` 4803 行）：MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN/ORDER BY/SKIP/LIMIT/DISTINCT/UNWIND/UNION/CASE，变长路径 `[*1..3]`，聚合 count/sum/avg/min/max/collect，`EXISTS{}` 用于 dead-code 检测
- **团队共享 artifact**：`.codebase-memory/graph.db.zst`（zstd 1.5.7，8-13:1 压缩），`VACUUM INTO` + 索引剥离

---

## 三、CodeWiki-CN 深度分析

### 3.1 项目定位

CodeWiki-CN 是 LLM Wiki 生成器：tree-sitter 解析代码 → LLM 生成 Markdown 文档 → 知识库 notes 沉淀。MCP 工具围绕"文档生命周期"组织（生成、查询、维护、归档），而非"图查询"。

### 3.2 25 个 MCP 工具（实测自 `codewiki/mcp/registry.py`）

| 类别 | 工具 | 实现位置 |
|------|------|---------|
| 索引 | `analyze_repo`, `analyze_workspace`, `close_session` | `tools/analysis.py`, `tools/workspace_analyzer.py`, `tools/close_session.py` |
| 组件读取 | `read_code_components`, `list_components`, `view_repo_file`, `get_module_tree`, `save_module_tree`, `get_processing_order` | `tools/code_reader.py`, `tools/component_list.py`, `tools/file_viewer.py`, `tools/module_tree.py` |
| 依赖/影响 | `list_dependencies`, `analyze_impact` | `tools/crosslink.py`, `tools/impact.py` |
| 跨服务 | `query_cross_service` | `tools/cross_service.py` |
| 文档生成 | `write_doc_file`, `edit_doc_file`, `generate_docs` (legacy) | `tools/doc_writer.py`, `tools/legacy_tools.py` |
| 知识库 | `ingest_note`, `query_wiki`, `confirm_note`, `reject_note`, `ingest_source`, `retract_source`, `batch_ingest`, `flag_issue` | `tools/knowledge_loop.py`, `tools/source_ingest.py`, `tools/batch_ingest.py`, `tools/issue_tracker.py` |
| 维护 | `lint_wiki`, `wiki_index` | `tools/wiki_lint.py`, `tools/wiki_index.py` |
| 其他 | `get_prompt`, `agents_md`, `crosslink`, `schema_generator` | `tools/prompt_server.py`, `tools/agents_md.py` |

### 3.3 解析管线（`codewiki/src/be/dependency_analyzer/`）

**入口**：`ast_parser.py::DependencyParser.parse_repository()` → `AnalysisService._analyze_call_graph()` → `CallGraphAnalyzer.analyze_code_files()`。

**支持语言**（`analysis_service.py` 第 303-315 行）：python, javascript, typescript, java, csharp, c, cpp, php, go, rust, kotlin（**11 种**）。

**实现方式**：
- Python：标准库 `ast`（`analyzers/python.py` 第 1 行 `import ast`）
- 其他 10 种：tree-sitter Python 绑定（`analyzers/{c,cpp,csharp,go,java,javascript,kotlin,php,typescript}.py` 都 `from tree_sitter import Parser, Language` + `import tree_sitter_<lang>`）

**核心数据模型**（`models/core.py` 第 7-47 行）：

```python
class Node(BaseModel):
    id, name, component_type, file_path, relative_path
    depends_on: Set[str]            # 唯一的"边"——扁平依赖集合
    source_code, start_line, end_line
    has_docstring, docstring, parameters
    node_type, base_classes, class_name
    qualified_name, language
```

**关键观察**：CodeWiki 的"图"是 **每个节点一个 `depends_on: Set[str]`**，没有边类型、没有边属性、没有独立的 edges 表。这与 CBM 的 `nodes + edges + properties JSON` 关系模型有本质差距。

**调用解析**（`call_graph_analyzer.py` 第 532-650 行）：
- `_resolve_call_relationships()`：构建 exact / simple 双索引，按 qualified_name → component_id → name 多级回退
- `_is_external_callee()`：基于 `is_external_symbol()` + Java 包前缀 + C/C++ 宏命名约定过滤外部调用
- **没有类型推断**：`user.profile.display_name()` 这种跨模块属性链无法解析（CBM Hybrid LSP 的强项）

### 3.4 存储层（`codewiki/mcp/cache.py`，1390 行）

SQLite Schema（第 260-311 行）：

```sql
CREATE TABLE repo_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE components (...);                  -- 节点
CREATE TABLE file_fingerprints (...);           -- 增量索引
CREATE TABLE dependencies (...);                -- 边（仅 source/target，无类型）
CREATE TABLE search_index (...);                -- 自实现 BM25
CREATE TABLE search_token_index (...);
CREATE TABLE search_stats (key, value);
CREATE TABLE symbols (...);
CREATE TABLE wiki_links (...);                  -- 文档间链接
CREATE TABLE routes (...);                      -- 跨服务 Route 节点（已借鉴 CBM）
```

**没有 FTS5**，BM25 是 Python 自实现（`tools/wiki_search.py` 第 1 行 "BM25 search engine for CodeWiki docs + notes"），用 jieba 分词，**搜索对象是 wiki 文档与 notes，不是代码符号**。

### 3.5 跨服务能力（已部分借鉴 CBM）

`dependency_analyzer/analysis/cross_service_matcher.py`（241 行）已实现：

- `path_matches_template()`（第 26-47 行）：直接移植 CBM `cr_path_matches_template()`，注释明确写了 "Borrowed from CBM"
- `CrossServiceMatcher` 类：HTTP 路由匹配（精确 + 模糊模板回退）+ MQ 匹配
- 数据模型（`models/cross_service.py`）：`RouteProtocol {HTTP, GRPC, GRAPHQL, MQ}`、`RouteRole {SERVER, CLIENT}`、`RouteNode`、`CrossServiceLink`、`WorkspaceTopology`
- 路由提取器（`analyzers/route_extractors/`）：go/java/js/python + 通用 mq_patterns

**已实现 Phase 1（HTTP）+ Phase 2（MQ）**，源码注释（第 81-83 行）：

```python
# Phase 3-4: placeholders for future expansion
# links.extend(self._match_channels())
# links.extend(self._match_typed_routes())
```

**未实现**：Channel（EMITS/LISTENS_ON）、gRPC/GraphQL/tRPC、CROSS_* 双向边、DATA_FLOWS。

### 3.6 服务/基础设施感知

- `analysis/service_detector.py`（581 行）：从 docker-compose / Dockerfile / build manifests / 约定目录 / Spring 配置检测服务
- `analysis/infra_scanner.py`（240 行）：解析 docker-compose、.env、application.yml，提取服务 URL
- `analysis/topology_visualizer.py`（123 行）：生成 Mermaid 拓扑图

### 3.7 LLM 聚类（不是图算法）

`src/be/cluster_modules.py`（第 56-108 行）的 `cluster_modules()` 是 **LLM 提示词驱动的模块聚类**：把潜在核心组件列表 + 当前模块树喂给 LLM，让 LLM 决定子模块划分。这与 CBM 的 Leiden 算法是两条完全不同的路线：

- CodeWiki：LLM 主观判断，结果用于"文档目录组织"
- CBM：图算法客观聚类，结果用于"发现 de-facto 模块边界"（`get_architecture(aspects=["clusters"])`）

### 3.8 CBM 集成现状（占位但未接通）

`mcp/tools/cbm_integration.py`（98 行）：

```python
def cbm_trace_cross_service(...):
    if not is_cbm_available():
        return None
    # CBM is typically accessed via MCP — this would need the MCP client
    # to call trace_path. For now, return None to trigger local fallback.
    logger.debug("CBM trace_path not yet wired to MCP client, using local fallback")
    return None
```

`is_cbm_available()` 用 `importlib.util.find_spec("codebase_memory_mcp")` 检测——但 CBM 是二进制 MCP 服务器，**不是 Python 包**，这个检测永远不会成功。集成层是占位代码，**实际从未调用过 CBM**。

---

## 四、功能对比矩阵

### 4.1 工具级对比（CBM 15 工具 vs CodeWiki 25 工具）

| CBM 工具 | CodeWiki 对应 | 覆盖度 | 差距说明 |
|---------|--------------|-------|---------|
| `index_repository` | `analyze_repo` / `analyze_workspace` | **部分** | CodeWiki 输出是 Markdown + SQLite 缓存；CBM 输出是图数据库。CodeWiki 没有 cross-repo-intelligence 模式、没有 zstd artifact 团队共享 |
| `search_graph` | `query_wiki`（搜文档）+ `list_components`（按名字） | **小部分** | CodeWiki 没有 BM25 over 代码符号、没有正则 name_pattern、没有 degree 过滤、**完全没有向量搜索** |
| `query_graph` (Cypher) | **无** | **缺失** | CodeWiki 没有任何图查询语言，只有硬编码 BFS |
| `trace_path` | `analyze_impact`（仅依赖方向）+ `list_dependencies` | **部分** | CodeWiki 有 BFS 但无 cursor 分页、无 data_flow 模式、无 cross_service 模式、无 risk_labels、无 test 过滤 |
| `get_code_snippet` | `read_code_components` / `view_repo_file` | **覆盖** | 功能等价 |
| `get_graph_schema` | **无** | **缺失** | CodeWiki 没有 schema 自省 |
| `get_architecture` | `analyze_workspace`（仅服务表）+ LLM 生成 overview | **小部分** | 缺 hotspots / boundaries / layers / **clusters（Leiden）** / cycles / file_tree |
| `search_code` | **无**（建议用 Grep） | **缺失** | CodeWiki 没有图增强 grep |
| `list_projects` | **无**（session 概念不同） | **缺失** | CodeWiki 是 per-repo session，没有全局项目注册表 |
| `delete_project` | **无** | **缺失** | 同上 |
| `index_status` | **无** | **缺失** | CodeWiki 没有 parse_partial / skipped 覆盖报告 |
| `check_index_coverage` | **无** | **缺失** | 同上 |
| `detect_changes` | `_detect_doc_changes`（analysis.py 第 622 行）+ `_find_affected_modules` | **部分** | CodeWiki 检测的是"文档是否过时"，CBM 检测的是"代码符号 blast radius"。语义不同 |
| `manage_adr` | `ingest_note(note_type="decision")` | **部分** | CodeWiki 的 decision notes 是 Markdown，CBM 的 ADR 是结构化 sections |
| `ingest_traces` | **无** | **缺失** | CodeWiki 没有 OTLP 摄入 |

### 4.2 反向：CodeWiki 独有能力（CBM 没有）

| CodeWiki 工具 | CBM 是否有 | 说明 |
|--------------|----------|------|
| `write_doc_file` / `edit_doc_file` | **无** | CBM 不生成文档 |
| `generate_docs`（LLM 文档生成） | **无** | CBM 明确"no built-in LLM" |
| `ingest_note` / `query_wiki` / `confirm_note` / `reject_note` | **无** | 知识库 notes 工作流是 CodeWiki 独有 |
| `lint_wiki` | **无** | 文档与代码一致性检查 |
| `ingest_source` / `retract_source` / `batch_ingest` | **无** | 外部知识源管理 |
| `flag_issue` | **无** | 文档问题追踪 |
| `get_prompt` | **无** | LLM 提示词模板服务 |
| `agents_md` | **无** | AGENTS.md 自动生成（CBM 的 install 写 AGENTS.md 但不暴露为 MCP 工具） |
| `save_module_tree` / `get_module_tree` | **无** | 模块树由 LLM 聚类生成 |

### 4.3 能力维度对比

| 能力 | CodeWiki-CN | CBM | 差距类型 |
|------|------------|-----|---------|
| tree-sitter 解析 | 11 语言（Python 用 ast） | 158 语言（vendored） | 数量差距，可补 |
| 类型推断 | 启发式名字匹配 | Hybrid LSP（10 语言深度推断） | **架构性** |
| 节点模型 | Node + depends_on:Set | nodes 表 + 13 种 label | 数据模型差距 |
| 边模型 | 无独立边（仅 depends_on） | edges 表 + 30+ 种 type + properties JSON | **架构性** |
| 图查询 | 硬编码 BFS | openCypher 子集（4803 行） | **架构性** |
| 全文搜索 | 自实现 BM25 + jieba（搜文档） | FTS5 + camelCase（搜符号） | 中（目标不同） |
| 向量搜索 | **无** | nomic-embed-code 768d int8 + 11 信号 | **架构性**（需引入模型） |
| 社区检测 | LLM 提示词聚类 | Leiden 多层算法 | 中（可移植） |
| 复杂度指标 | TS 占位 `'complexity': 1` | cyclomatic/cognitive/loop_depth/transitive_loop_depth/linear_scan_in_loop/alloc_in_loop | 中（可移植） |
| Dead code 检测 | **无** | `EXISTS{}` Cypher + entry-point 排除 | 中 |
| 近克隆检测 | **无** | MinHash + LSH + Jaccard | 中 |
| 跨服务 HTTP | ✅ Route + 模糊匹配 | ✅ + 双向边 + DATA_FLOWS | 小（已起步） |
| 跨服务 MQ | ✅ Kafka/RabbitMQ/RocketMQ | ✅ + Channel EMITS/LISTENS_ON | 小 |
| 跨服务 gRPC/GraphQL/tRPC | **无** | ✅ + protobuf Route 提取 | 中 |
| 跨仓库匹配 | workspace 级 Route 合并 | CROSS_* 双向边写入双方 DB | 中 |
| 增量索引 | file_fingerprints（mtime/sha） | file_hashes + git watcher daemon | 中 |
| K8s/Docker 索引 | service_detector + infra_scanner（仅服务发现） | Resource/Module 节点 + IMPORTS 边入图 | 中 |
| OTLP trace | **无** | ingest_traces 工具 | 中 |
| 团队共享索引 | **无** | graph.db.zst（zstd 1.5.7） | 中 |
| Git diff 影响 | _detect_doc_changes（文档维度） | detect_changes（符号 blast radius + 风险分级） | 中 |
| ADR | ingest_note(decision) | manage_adr（结构化 sections） | 小 |
| 文档生成 | ✅ 核心能力 | **无** | CodeWiki 独有 |
| 知识库 notes | ✅ 核心能力 | **无** | CodeWiki 独有 |

---

## 五、技术可行性分析

### 5.1 tree-sitter 解析能力对比

| 维度 | CodeWiki | CBM |
|------|---------|-----|
| 解析器 | tree-sitter Python 绑定（py-tree-sitter） | vendored C grammars 静态编译 |
| 语言数 | 11 | 158 |
| 性能 | Python 调用开销，串行（`for idx, file_info in enumerate(code_files)`，call_graph_analyzer.py 第 106 行） | RAM-first C 管线 + LZ4 + worker_pool 并行 |
| 类型解析 | 无（仅语法 AST + 名字匹配） | Hybrid LSP（10 语言） |
| 错误恢复 | 文件级 try/except，失败跳过 | parse_partial 标记 + missed graph 可查询 |

**可行性**：
- 增加语言数：低难度（pip 安装 tree-sitter 绑定 + 写 analyzer），但每语言约 200-1000 行（参考 CodeWiki 现有 analyzer 行数：c.py 215、cpp.py 676、typescript.py 980）
- Hybrid LSP：**不可行**。CBM 的 pass_lsp_cross.c 1126 行 + 各语言类型解析逻辑（pyright/gopls/tsserver 兼容）是数万人时工作量，Python 重写性能也不达标
- 性能：Python 单线程串行 vs C 并行，对 Linux 内核量级仓库不可行；对一般仓库（< 100K LOC）够用

### 5.2 图存储与查询能力差异

**CodeWiki 现状**（`cache.py`）：
- `components` + `dependencies` 两表，dependencies 仅 source/target，**无 type、无 properties**
- 查询全靠 Python 加载到内存做 BFS（`impact.py::handle_analyze_impact`、`crosslink.py::handle_list_dependencies`）

**CBM 现状**（`store.c`）：
- `nodes` + `edges` + `properties JSON` + 9 个索引 + FTS5 虚表
- Cypher 引擎（`cypher.c` 4803 行）：lexer → parser → planner → executor，支持变长路径、聚合、UNION、EXISTS

**对齐方案**：
1. **Schema 升级**（中难度）：将 `dependencies` 表改为 `edges(source_id, target_id, type, properties)`，迁移现有 depends_on 数据为 `CALLS` 类型
2. **Cypher 引擎**（高难度）：Python 有 `pypher`、`opencypher` 等库但都不成熟；自实现一个子集（MATCH/WHERE/RETURN/LIMIT）约 1500-2500 行 Python，性能可接受（节点 < 100K 时）
3. **替代方案**：嵌入 `sqlite-graph` 或 `kuzu`（嵌入式图数据库，支持 Cypher），但增加依赖

### 5.3 向量/语义搜索

**CBM 方案**：nomic-embed-code 模型量化为 int8 编译进二进制（`PRETRAINED_VECTOR_BLOB`），768 维，无外部依赖。

**CodeWiki 对齐选项**：
1. ** sentence-transformers + nomic-embed-code-v1.5**（HuggingFace）：约 1.5GB 模型，Python 推理慢但可接受（CPU 上 ~50ms/句）。**问题**：CodeWiki 当前是轻量 MCP 服务器，引入 torch 会破坏部署体验
2. **调用 LLM 提供商的 embedding API**：违反 CodeWiki "可离线" 假设
3. **不对齐**：CodeWiki 的搜索目标是 wiki 文档（短文本，jieba+BM25 足够），代码符号搜索可以委托给 CBM

**推荐**：选项 3。语义搜索是 CBM 的核心竞争力，Python 重写性价比低；通过 MCP 调用 CBM 即可。

### 5.4 社区检测/聚类

**CBM**：Leiden 算法（store.c 第 5987-6308 行，约 320 行 C）。

**CodeWiki 现状**：LLM 提示词聚类（cluster_modules.py），用于文档目录组织。

**对齐方案**：
- Python 有 `leidenalg` + `igraph` 成熟包，移植成本低（约 100 行胶水代码）
- 输入：从 edges 表构建 igraph.Graph（权重 = 调用次数）
- 输出：写入 module_tree 或新增 `clusters` 字段
- **关键差异**：CBM 的 Leiden 用于"发现 de-facto 模块"（客观），CodeWiki 的 LLM 聚类用于"组织文档目录"（主观）。两者**互补不冲突**——可以在 generate_docs 之前先跑 Leiden 给 LLM 提供结构提示

### 5.5 跨服务分析

CodeWiki 已实现 Phase 1（HTTP）+ Phase 2（MQ），数据模型（RouteNode/CrossServiceLink/WorkspaceTopology）与 CBM 高度兼容。**剩余差距**：

| 项 | 工作量 |
|----|-------|
| Channel（EMITS/LISTENS_ON）：Socket.IO/EventEmitter 检测 | 中（约 200 行） |
| gRPC：解析 .proto 创建 `__grpc__Service/Method` Route | 中（约 150 行） |
| GraphQL：解析 schema 与 operation | 中（约 200 行） |
| tRPC：检测 router 定义与 client 调用 | 中（约 150 行） |
| CROSS_* 双向边写入双方 SQLite | 小（约 80 行） |
| DATA_FLOWS 边（caller_args / handler_params） | 中（约 200 行，需 AST 实参提取） |

---

## 六、对齐方案

### 6.1 总体策略：分层对齐 + 委托集成

**核心原则**（与 `docs/codebase-memory-mcp跨服务分析-源码借鉴分析.md` 第 4.7 节一致）：

> "CodeWiki-CN 不需要也不应该重新实现 CBM 的完整引擎。"

分三层：

1. **委托层**（CBM 已安装时）：通过 MCP 客户端调用 CBM 工具，CodeWiki 把结果转化为 wiki 文档
2. **借鉴层**（CBM 未安装时）：在 Python 中实现轻量版核心能力（Route 匹配、Leiden、复杂度、Cypher 子集）
3. **独有层**：保留并强化 CodeWiki 的文档生成与知识库能力（CBM 永远不会有）

### 6.2 阶段化路线图

#### Phase 1（P0，约 3-5 天）：图模型升级 + 真正接通 CBM

| 任务 | 工作量 | 文件 |
|------|-------|------|
| 修复 `cbm_integration.py::is_cbm_available()`：用 MCP 客户端探测（如尝试调用 `list_projects`），而非 `find_spec` | 0.5 天 | `mcp/tools/cbm_integration.py` |
| 实现 MCP 客户端调用 CBM（CodeWiki 作为 client 连接 CBM server） | 1.5 天 | 新增 `mcp/cbm_client.py` |
| `dependencies` 表升级为 `edges(source_id, target_id, type, properties)` | 1 天 | `mcp/cache.py` |
| 在 `analyze_repo` 中可选调用 CBM `get_architecture(aspects=["clusters","hotspots"])` 写入 wiki overview | 1 天 | `mcp/tools/analysis.py` |

#### Phase 2（P1，约 5-7 天）：算法移植

| 任务 | 工作量 | 实现 |
|------|-------|------|
| Leiden 社区检测（用 `leidenalg` + `igraph`） | 1.5 天 | 新增 `dependency_analyzer/analysis/community_detector.py` |
| 复杂度指标（cyclomatic / cognitive / loop_depth） | 2 天 | 扩展各语言 analyzer，写入 Node 属性 |
| Dead-code 检测（zero in-degree + entry-point 排除） | 1 天 | 新增 `tools/dead_code.py` 或并入 `analyze_impact` |
| Git diff 符号级 blast radius（增强现有 `_find_affected_modules`） | 1.5 天 | `mcp/tools/analysis.py` |
| 跨服务 Phase 3（Channel）+ Phase 4（gRPC） | 2 天 | `analyzers/route_extractors/` |

#### Phase 3（P2，约 7-10 天）：查询能力

| 任务 | 工作量 | 实现 |
|------|-------|------|
| Cypher 子集查询引擎（MATCH/WHERE/RETURN/LIMIT/ORDER BY，无变长路径） | 5 天 | 新增 `mcp/cypher/`（lexer/parser/executor），约 2000 行 Python |
| `query_graph` MCP 工具 | 1 天 | `mcp/tools/` |
| `get_graph_schema` MCP 工具 | 0.5 天 | 同上 |
| `trace_path` 增强（cursor 分页 + data_flow 模式 + risk_labels） | 2 天 | 升级 `impact.py` |
| `search_graph` 统一工具（BM25 over 符号 + 正则 + degree 过滤） | 2 天 | 升级 `wiki_search.py` 或新增 |

#### Phase 4（P3，可选，约 5-7 天）：高级能力

| 任务 | 工作量 | 备注 |
|------|-------|------|
| DATA_FLOWS 边（caller_args / handler_params 提取） | 2 天 | 需各语言 AST 实参提取 |
| MinHash 近克隆检测（用 `datasketch` 库） | 1.5 天 | 写入 SIMILAR_TO 边 |
| OTLP trace 摄入 | 2 天 | 新增 `tools/trace_ingest.py` |
| K8s/Dockerfile 入图（Resource/Module 节点） | 1.5 天 | 升级 `infra_scanner.py` |
| 团队共享 artifact（zstd 压缩 SQLite） | 1 天 | 用 `zstandard` 库 |

#### Phase 5（不建议）：架构性差距

以下能力**不建议**在 CodeWiki 中对齐：

- **Hybrid LSP**：CBM 数万人时的 C 实现，Python 重写性能不达标，且 CodeWiki 的目标用户不需要 IDE 级精度
- **158 语言**：CodeWiki 用户群（Java/Python/TS/Go 微服务团队）用 11 语言已够
- **nomic-embed-code 内嵌**：引入 torch 破坏部署体验，应通过 CBM 委托
- **Linux 内核量级性能**：CodeWiki 是文档生成器，不需要 3 分钟索引 28M LOC

### 6.3 工作量估算汇总

| 阶段 | 工作量 | 价值 |
|------|-------|------|
| Phase 1（图模型 + CBM 委托） | 3-5 天 | **高**：立即获得 CBM 全部能力（CBM 已安装时） |
| Phase 2（算法移植） | 5-7 天 | **高**：CBM 未安装时也有 Leiden / 复杂度 / dead-code |
| Phase 3（Cypher 查询） | 7-10 天 | 中：Agent 可写自定义查询，但多数场景 trace_path 够用 |
| Phase 4（高级能力） | 5-7 天 | 中：DATA_FLOWS / 近克隆对特定场景有用 |
| **合计（不含 Phase 5）** | **20-29 天** | — |

---

## 七、结论

### 7.1 能否完全对齐？

**不能，也不应该。** 三个层面的原因：

1. **产品定位不同**（不可对齐）：CBM 是结构分析后端（无 LLM、不生成文档），CodeWiki 是 LLM Wiki 生成器（有 LLM、产出 Markdown）。CBM 的 README 第 239 行明确说："It does not include an LLM. Instead, it relies on your MCP client to be the intelligence layer." 这两个产品在 AI 工作流中是**互补关系**，不是竞争关系。

2. **架构性差距**（不应在 Python 中对齐）：
   - Hybrid LSP 类型推断（CBM 用 C 重写各语言服务器算法）
   - 内嵌量化嵌入模型（nomic-embed-code 768d int8）
   - Linux 内核量级性能（RAM-first C 管线 + LZ4 + Aho-Corasick）
   - 158 语言 vendored grammars

   这些是 CBM 的核心竞争力，Python 重写既不现实（性能差 10-100x）也不必要（CodeWiki 用户不需要）。

3. **数据模型差距**（可对齐但成本高）：
   - CodeWiki 的 `Node.depends_on: Set[str]` vs CBM 的 `edges + type + properties`
   - 没有 Cypher 引擎、没有 FTS5、没有向量索引

   这些可以补齐（Phase 1-3，约 15-22 天），但需要 schema 迁移与大量重构。

### 7.2 哪些能对齐？

**推荐对齐**（按 ROI 排序）：

| 能力 | 工作量 | ROI |
|------|-------|-----|
| 真正接通 CBM MCP 委托（修复 cbm_integration.py） | 2 天 | **极高** |
| Leiden 社区检测（leidenalg） | 1.5 天 | 高 |
| 复杂度指标 + dead-code 检测 | 3 天 | 高 |
| 跨服务 Phase 3/4（Channel + gRPC） | 2 天 | 高 |
| edges 表升级（带 type/properties） | 1 天 | 高（基础设施） |
| Git diff 符号级 blast radius | 1.5 天 | 中 |
| Cypher 子集查询 | 5 天 | 中 |
| DATA_FLOWS / MinHash / OTLP | 5.5 天 | 中（特定场景） |

### 7.3 哪些是架构性差异无法简单补齐？

| 能力 | 为什么补不齐 |
|------|------------|
| Hybrid LSP 类型推断 | 数万人时 C 实现，Python 性能不达标；CodeWiki 启发式名字匹配已能满足文档生成需求 |
| 内嵌向量搜索 | 引入 torch/transformers 破坏 CodeWiki 轻量部署；应委托 CBM |
| 158 语言 | 边际收益低（CodeWiki 用户主要用 5-6 种语言）；每语言 analyzer 维护成本高 |
| Linux 内核量级性能 | Python 串行 vs C 并行 + RAM-first；CodeWiki 不需要这种规模 |
| 单二进制零依赖分发 | Python 项目本质做不到；CodeWiki 用 pip 安装是合理选择 |

### 7.4 最终建议

1. **立即做**（Phase 1）：修复 `cbm_integration.py`，让 CodeWiki 真正能调用 CBM。这是 ROI 最高的一步——CBM 已安装时立即获得 15 工具的全部能力，无需自己实现。

2. **短期做**（Phase 2）：移植 Leiden、复杂度、dead-code 等"算法层"能力到 Python。这些是 CBM 未安装时的兜底，也是 CodeWiki 自身图分析能力的根基。

3. **中期做**（Phase 3）：根据用户实际需求决定是否引入 Cypher 子集。如果 Agent 主要用 `trace_path` 风格的固定查询，可以推迟。

4. **不做**：Hybrid LSP、内嵌嵌入模型、158 语言、Linux 内核量级性能。这些是 CBM 的护城河，CodeWiki 应该把精力放在自己的护城河上——**LLM 文档生成 + 知识库 notes 工作流**（CBM 永远不会做）。

5. **战略定位**：把 CodeWiki 定位为"CBM 的 LLM 文档前端"——CBM 提供结构与查询，CodeWiki 提供文档与知识沉淀。两者通过 MCP 协议组合，而非互相替代。这与现有 `codewiki-wiki-generator` skill 的"三层增强模式"（codebase-memory-mcp 深度增强 / CodeGraph 调用图增强 / 纯 CodeWiki 标准模式）思路完全一致。

---

## 附录 A：关键源码引用索引

### CodeWiki-CN
- 25 工具注册：`D:\repos\CodeWiki-CN\codewiki\mcp\registry.py`（第 68-1235 行）
- 数据模型：`codewiki\src\be\dependency_analyzer\models\core.py`（Node 第 7-47 行）
- 解析入口：`codewiki\src\be\dependency_analyzer\ast_parser.py`（DependencyParser 第 19-177 行）
- 调用图分析：`codewiki\src\be\dependency_analyzer\analysis\call_graph_analyzer.py`（863 行）
- 跨服务匹配：`codewiki\src\be\dependency_analyzer\analysis\cross_service_matcher.py`（241 行）
- Route 数据模型：`codewiki\src\be\dependency_analyzer\models\cross_service.py`（65 行）
- SQLite Schema：`codewiki\mcp\cache.py`（第 260-311 行）
- LLM 聚类：`codewiki\src\be\cluster_modules.py`（cluster_modules 第 56-108 行）
- CBM 集成占位：`codewiki\mcp\tools\cbm_integration.py`（98 行，未接通）
- 服务检测：`codewiki\src\be\dependency_analyzer\analysis\service_detector.py`（581 行）
- 基础设施扫描：`codewiki\src\be\dependency_analyzer\analysis\infra_scanner.py`（240 行）

### codebase-memory-mcp
- 15 工具定义：`D:\repos\codebase-memory-mcp-src\src\mcp\mcp.c`（TOOLS[] 第 347-654 行）
- SQLite Schema：`src\store\store.c`（init_schema 第 224-350 行）
- Leiden 算法：`src\store\store.c`（第 5987-6308 行）
- 语义嵌入：`src\semantic\semantic.h`（CBM_SEM_DIM=768 第 36 行）+ `semantic.c`（nomic 第 443 行）
- 复杂度 pass：`src\pipeline\pass_complexity.c`（207 行）
- Route 节点：`src\pipeline\pass_route_nodes.c`（1231 行，DATA_FLOWS 第 590-914 行）
- 跨仓库匹配：`src\pipeline\pass_cross_repo.c`（1356 行）
- Hybrid LSP：`src\pipeline\pass_lsp_cross.c`（1126 行）
- Cypher 引擎：`src\cypher\cypher.c`(4803 行)
- MinHash 相似度：`src\pipeline\pass_similarity.c`（353 行）
- git 历史耦合：`src\pipeline\pass_githistory.c`（FILE_CHANGES_WITH 第 460 行）
- 增量索引：`src\pipeline\pipeline_incremental.c`
- README：`README.md`（777 行，含 15 工具表、Hybrid LSP 表、性能基准）

### 已有相关文档
- `D:\repos\CodeWiki-CN\docs\codebase-memory-mcp跨服务分析-源码借鉴分析.md`（365 行，2026-07-25）：跨服务分析专项分析，本报告与其结论一致并扩展到其他能力维度
- `D:\repos\CodeWiki-CN\docs\跨服务调用分析-实现计划.md`：跨服务实现计划
- `D:\repos\CodeWiki-CN\docs\CodeWiki-CN-优化Roadmap.md`：整体优化路线图

---

## 附录 B：典型场景下的能力对照

### 场景 1：Agent 问"ProcessOrder 函数被谁调用了？"

- **CBM**：`trace_path(function_name="ProcessOrder", direction="inbound")` → <10ms 返回调用链
- **CodeWiki**：`analyze_impact(component_ids=["...ProcessOrder"], direction="depended_by")` → BFS 返回，**功能等价**但无 cursor 分页、无 risk_labels

### 场景 2：Agent 问"这个项目有哪些功能模块？"

- **CBM**：`get_architecture(aspects=["clusters"])` → Leiden 算法客观聚类，返回 label/member count/cohesion/top_nodes
- **CodeWiki**：`get_module_tree` → LLM 提示词聚类，返回文档目录结构。**两者结果不同但互补**

### 场景 3：Agent 问"找出所有热路径函数（嵌套循环 + 线性扫描）"

- **CBM**：`query_graph("MATCH (f:Function) WHERE f.transitive_loop_depth >= 3 OR f.linear_scan_in_loop >= 1 RETURN ...")` → 一次查询
- **CodeWiki**：**完全做不到**。没有复杂度指标，没有 Cypher。需要 Agent 自己 grep + 阅读源码

### 场景 4：Agent 问"Service A 的 checkout() 调用了 Service B 的哪个 API？"

- **CBM**：`trace_path(function_name="checkout", mode="cross_service")` → 沿 HTTP_CALLS + CROSS_HTTP_CALLS 边追踪
- **CodeWiki**：`query_cross_service(filter_type="trace", filter_value="checkout")` → 已实现，但仅 Route 级（不到函数级 data_flow）

### 场景 5：Agent 问"为这个仓库生成完整 Wiki"

- **CBM**：**做不到**（不生成文档）
- **CodeWiki**：`analyze_repo` + `generate_docs` + `write_doc_file` → 核心能力

### 场景 6：Agent 问"我修改了 utils.py，会影响哪些函数？"

- **CBM**：`detect_changes(scope="impact", direction="inbound")` → 符号级 blast radius + 风险分级
- **CodeWiki**：`_detect_doc_changes`（仅检测哪些文档需要更新）+ `analyze_impact`（手动指定 component_ids）。**缺少 git diff → 符号的自动映射**

---

*报告完。所有结论均基于 2026-07-29 实际源码与文档；CBM 源码克隆自 GitHub main 分支，CodeWiki-CN 为本地工作副本。*
