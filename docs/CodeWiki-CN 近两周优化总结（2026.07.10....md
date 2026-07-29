# CodeWiki-CN 近两周优化总结（2026.07.10 — 07.23）

#

## 概览

两周内完成 20+ 次提交，将 CodeWiki-CN 从"能用"提升到"好用"。核心方向：性能优化（SQLite 缓存 + 增量解析）、MCP 协议规范化（参考 CodingHub）、知识层能力增强（参考 llm\_wiki / WeKnora / codebase-memory）。

***

## 一、从开源工具借鉴的特性

### 1. codebase-memory-mcp（codebase-memory）

**借鉴特性：SQLite 持久化缓存 + 跨会话复用**

codebase-memory 使用 SQLite 存储代码图谱（节点、边、文件指纹），支持跨会话增量更新。我们借鉴了这一架构：

* 新增 `AnalysisCache`（cache.py），SQLite WAL 模式存储组件索引、文件指纹、依赖关系、BM25 搜索索引、符号映射
* `LazyComponentStore` 替代内存中的 `Dict[str, Node]`，LRU 缓存按需加载组件完整数据
* 跨会话共享 `AnalysisCache` 注册表，同一仓库的多次分析复用同一 SQLite 数据库
* 内容哈希（SHA-256 前 64KB）+ mtime 双重变更检测

### 2. CodingHub MCP Server

**借鉴特性：MCP 协议最佳实践（instructions / prompts / resources）**

参考 CodingHub 的 MCP Server 实现，对 CodeWiki-CN 的 server.py 进行全面优化：

* **Server Instructions**：添加 1624 字符的能力概览 + 工作流指南 + 约束说明，使 MCP 不依赖 Skill 也能独立使用
* **6 个 MCP Prompt 模板**：generate-wiki、extract-knowledge、search-wiki、quality-check、incremental-update、workspace-analysis，每个 Prompt 返回 USER 消息引导 Agent 完成特定任务
* **3 个静态 Resource + 3 个 ResourceTemplate**：wiki-catalog、module-tree、index-status 等只读资源，支持 IDE 直接浏览 Wiki 状态
* **21 个工具描述全面丰富**：添加工作流上下文、跨工具引用、行为约束、枚举值说明

### 3. nashsu/llm\_wiki

**借鉴特性：结构化知识层 + 页面类型路由 + 交叉链接**

llm\_wiki 的 Obsidian 插件设计启发我们构建了 LLM Wiki 知识层：

* 6 种页面类型（module/entity/concept/source/comparison/query）分目录组织
* `page_router.py` 统一路由，`write_doc_file` 按 `page_type` 自动路由到正确目录
* 交叉链接自动注入（基于组件依赖关系）
* 别名（aliases）3× BM25 权重提升
* 来源引用（source\_refs）内联标注

### 4. Tencent/WeKnora

**借鉴特性：外部文档管理 + 文档健康检查**

调研 WeKnora 后（决策：不集成，借鉴设计思路）：

* `ingest_source` / `retract_source` 管理第三方文档完整生命周期
* `source_registry.json` 注册表追踪导入状态
* `lint_wiki` 从 5 项扩展到 10 项检查（新增 orphan\_pages / no\_outlinks / missing\_aliases / stale\_sources / overview\_stale）
* `health_score`（0-100）综合评估文档质量

***

## 二、性能优化

### 1. SQLite 倒排索引替代 JSON

**改动**：将 BM25 搜索引擎从 JSON 文件存储重写为 SQLite 倒排索引

* Schema：`search_index`（文档元数据）+ `search_token_index`（token→doc 倒排）+ `search_stats`（全局统计）
* 性能提升：100 文档 2.5× 快，500 文档 3.8× 快，2000 文档 4.8× 快
* SQL 级 BM25 评分（CTE + JOIN + GROUP BY）替代 Python 逐候选遍历

### 2. Frontmatter 搜索加权

**改动**：`_build_indexable_text()` 提取 frontmatter 字段并加权

* tags 3× boost、description 2×、title 2×、aliases 3×、severity 2×
* 大幅提高同义词、缩写的搜索命中率

### 3. 元数据整合到 .meta/

**改动**：metadata.json、module\_tree.json、symbol\_map.json 等从 repowiki/ 根目录迁移到 `.meta/` 子目录

* 防止用户误删元数据文件
* `meta_join()` / `meta_resolve()` 统一读写，向后兼容旧路径

### 4. list\_components 摘要模式

**改动**：`summary: true` 参数按文件聚合组件，返回 `{count, types, classes}`

* 大项目输出从 \~15MB 降到 \~2MB
* 聚类阶段用摘要概览，精确阶段用 file\_prefix 过滤

### 5. SHA256 增量选择性重解析

**改动**：增量更新时跳过未变更文件的解析

* 检测变更后计算未变更文件集合，加载缓存组件
* `skip_file_paths` 参数贯穿全链路：`DependencyGraphBuilder` → `DependencyParser` → `AnalysisService` → `CallGraphAnalyzer`
* `batch_insert_components(incremental=True)` 使用 `INSERT OR REPLACE` 替代 `DELETE all + INSERT`
* 解析完成后合并缓存组件与新解析组件

### 6. Overview stale 精确判定

**改动**：精确判定 overview\.md 是否需要更新，替代无条件级联

* `_extract_overview_refs()` 解析 overview\.md 中的 wiki-links 和 markdown links
* 引用关系持久化到 `.meta/overview_refs.json`
* `_check_overview_stale()` 检查受影响模块是否在 overview 引用列表中
* `metadata.json` 新增 `overview_stale` 字段
* `lint_wiki` 新增 `overview_stale` 检查项

***

## 三、功能增强

### 1. LLM Wiki 知识层

完整的知识管理系统：

* 结构化知识库布局（6 种页面类型）
* schema.yaml 文档规范 + page\_types 路由表
* 外部文档管理（ingest\_source / retract\_source）
* 知识笔记增强（pitfall / known\_issue / workaround）
* 批量操作（batch\_ingest）
* 质量问题追踪（flag\_issue + health\_score）

### 2. MCP Server 全面优化

* Server Instructions（能力概览 + 工作流 + 约束）
* 6 个 Prompt 模板（generate-wiki / extract-knowledge / search-wiki / quality-check / incremental-update / workspace-analysis）
* 3 个静态 Resource + 3 个 ResourceTemplate
* 21 个工具描述全面丰富

### 3. Wikilink 图谱多跳搜索

* `wiki_links` 表存储页面间有向边（wikilink / mdlink）
* `graph_expand()` BFS 多跳扩展（decay 衰减）
* `get_related_pages()` 关联页面查询
* `search()` 新增 `hop` / `decay` 参数，结果附带 `related` 字段

### 4. doc\_type 支持

* `business` 文档类型（业务工作流、状态转换、领域规则）
* `design` 文档类型（技术设计、接口契约、设计决策）— 设为默认
* overview 与 module-level 提示词分离

### 5. 零配置启动

* 所有写入工具自动创建 output\_dir 及 .meta/ 子目录
* 默认 output\_dir 从 "docs" 改为 "repowiki"
* 空项目场景：直接调用 ingest\_note 即可开始积累设计知识

### 6. write\_doc\_file 无 session 模式

* 支持传 `output_dir` 替代 `session_id`
* 用于知识提取等不需要 analyze\_repo 的场景
* 轻量 frontmatter（title/type/description）
* 跳过 crosslink/symbol 注入但保留核心功能

***

## 四、Bug 修复

* scope 过滤改为三重匹配（stem/路径前缀/路径组件）
* batch\_ingest 顶层 output\_dir 自动注入子项
* generate\_docs/get\_module\_tree 相对 output\_dir 基于 repo\_path 解析
* Windows 短路径问题（tempfile.mkdtemp 返回 ADMINI\~1）
* remove\_by\_file 路径归一化（绝对 vs 相对路径匹配）

***

## 五、代码统计

* 20+ 次提交
* 7 个核心文件大幅修改（cache.py / analysis.py / server.py / wiki\_search.py / wiki\_lint.py / doc\_writer.py / knowledge\_loop.py）
* 新增 \~3000 行代码，删除 \~1500 行
* 新增 10 个 MCP 工具（list\_dependencies / lint\_wiki / ingest\_note / query\_wiki / ingest\_source / retract\_source / batch\_ingest / flag\_issue / list\_components / analyze\_workspace）

***

## 六、致谢

借鉴的开源项目：

* [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) — 核心工具链（Tree-sitter AST 解析、依赖图构建）
* [codebase-memory-mcp](https://github.com/nicobailon/codebase-memory-mcp) — SQLite 缓存架构
* [nashsu/llm\_wiki](https://github.com/nashsu/llm_wiki) — 结构化知识层设计、页面类型路由
* [Tencent/WeKnora](https://github.com/Tencent/WeKnora) — 外部文档管理、文档健康检查思路
* [CodingHub](https://github.com/mambo-wang/CodingHub) — MCP Server 最佳实践（instructions/prompts/resources）
