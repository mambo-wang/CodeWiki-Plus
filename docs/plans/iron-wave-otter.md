# CodeWiki-CN LLM Wiki 知识层扩展 — 实现计划

## Context

基于 `docs/LLM-Wiki-扩展方案.md` v2 设计文档，将 CodeWiki-CN 从扁平 module 文档结构升级为结构化 LLM Wiki 知识库，支持 entity/concept/source/comparison/query 等页面类型、第三方文档导入、踩坑记录增强、质量问题追踪。消费者为 AI Agent（MCP 协议）。

## 实现顺序（16 步，按依赖关系排列）

### Step 1: `config.py` 新增常量
**文件:** `codewiki/src/config.py`
- 新增: `WIKI_DIR = "wiki"`, `RAW_DIR = "raw"`, `RAW_SOURCES_DIR = "raw/sources"`
- 新增: `SOURCE_REGISTRY_FILENAME = "source_registry.json"`, `ISSUES_FILENAME = "issues.json"`, `PURPOSE_FILENAME = "purpose.md"`
- 新增: `PAGE_TYPE_DIRS` dict 映射 page_type → 子目录名

### Step 2: 新建 `page_router.py`
**新文件:** `codewiki/mcp/tools/page_router.py`
- `resolve_wiki_path(output_dir, schema) -> dict` — 返回完整路径映射
- `resolve_doc_path(filename, page_type, output_dir, schema) -> Path` — 单文件路由
- `compute_link_path(from_file, to_module, output_dir) -> str` — 跨目录相对路径
- `load_schema(output_dir) -> dict` — 带缓存的 schema.yaml 读取
- `get_page_type_dir(page_type, output_dir, schema) -> Path` — 查路由表

### Step 3: 重写 `_safe_doc_path()` 
**文件:** `codewiki/mcp/tools/doc_writer.py` (line 33)
- 改为接受 `page_type` 参数，调用 `resolve_doc_path()`
- `_build_okf_frontmatter()` (line 44) 改为从 page_type 推导 type 字段
- 两处 `_inject_crosslinks()` 硬编码路径 (line 293, 299) 替换为 `compute_link_path()`

### Step 4: 扩展 `schema_generator.py`
**文件:** `codewiki/mcp/tools/schema_generator.py`
- `_get_defaults()` (line 87) 新增 `page_types`, `extraction_granularity`, `wiki_link_syntax` 默认值
- `_merge_schemas()` 增加 page_types 的浅层 dict merge（按 page type name）
- `generate_schema()` 首次生成时包含完整 page_types 路由表

### Step 5: 所有 `.glob`/`iterdir` → 递归扫描
**6 个文件需修改:**
1. `cache.py:504` `build_search_index()` — `od.iterdir()` → `od.rglob("*.md")` + 排除 wiki/ 系统文件
2. `wiki_search.py:146` `build_full_index()` — 同上
3. `wiki_lint.py:102,150` — `output_dir.glob("*.md")` → `output_dir.rglob("*.md")`
4. `wiki_lint.py:115,165` — 链接解析改为从源文件目录计算相对路径
5. `knowledge_loop.py:527` — `output_dir.glob("*.md")` → `output_dir.rglob("*.md")`
6. `wiki_index.py:66-72` `rebuild_index()` — `output_dir.iterdir()` → 递归扫描 wiki/ 子目录

### Step 6: 扩展 `write_doc_file` 工具
**文件:** `codewiki/mcp/tools/doc_writer.py`, `codewiki/mcp/server.py`
- `server.py` `_fine_grained_tools()` (line 74): inputSchema 新增 `page_type` (enum) 和 `frontmatter_extra` (object)
- `doc_writer.py`: `handle_write_doc_file` 提取 page_type → 传给 `_safe_doc_path()`
- 新增 `_extract_source_refs(content)` — 从正文解析 `[^src:name:range]`
- 新增 `_inject_wiki_links(content, slug_index)` — `[[slug|display]]` 注入（可选）
- Frontmatter 生成: 6 种类型的专属字段 + aliases + source_refs/chunk_refs

### Step 7: 扩展 `ingest_note` 工具
**文件:** `codewiki/mcp/tools/knowledge_loop.py`, `codewiki/mcp/server.py`
- `server.py` inputSchema: note_type enum 增加 `pitfall/known_issue/workaround`, 新增 `severity/root_cause/source_ref/aliases`
- `knowledge_loop.py`: frontmatter 生成增加新字段
- `_inject_symbol_links()` (line 135): depth 计算改用 `_compute_depth(file_path, output_dir)`

### Step 8: 新建 `source_ingest.py` — `ingest_source` + `retract_source`
**新文件:** `codewiki/mcp/tools/source_ingest.py`
- `handle_ingest_source(arguments, store)` — 存储第三方文档到 raw/sources/，注册到 source_registry.json
- `handle_retract_source(arguments, store)` — 删除源文件，flag_stale 或 remove_refs 模式
- `server.py`: 注册两个新工具到 `_fine_grained_tools()` 和 `call_tool` 路由

### Step 9: 新建 `batch_ingest.py`
**新文件:** `codewiki/mcp/tools/batch_ingest.py`
- `handle_batch_ingest(arguments, store)` — 串行处理 items 列表，支持 items_file
- 内部调用 ingest_note/ingest_source 的处理函数
- 最后统一 rebuild_index + append_log

### Step 10: 新建 `issue_tracker.py` — `flag_issue`
**新文件:** `codewiki/mcp/tools/issue_tracker.py`
- `handle_flag_issue(arguments, store)` — 写入 .meta/issues.json
- 生成稳定 ID（FNV-1a hash of type::page_path）

### Step 11: 扩展 `get_prompt`
**文件:** `codewiki/mcp/tools/prompt_server.py`, `codewiki/src/be/prompt_template.py`
- `_PROMPT_CATALOG` (line 114) 新增 7 个 prompt_type: entity_page, concept_page, source_summary, comparison_page, query_page, taxonomy_plan, extraction_scan
- `_build_schema_constraints()` (line 30): 新增 page_types 路由表注入 + extraction_granularity + purpose.md 读取
- `prompt_template.py`: 新增 7 个提示模板字符串

### Step 12: 扩展 `query_wiki`
**文件:** `codewiki/mcp/tools/knowledge_loop.py`, `codewiki/mcp/server.py`
- `server.py` inputSchema 新增 `type_filter` (enum) 和 `include_sources` (boolean)
- `handle_query_wiki`: scope 参数支持目录前缀（`wiki/entities`, `wiki/sources`, `notes`）
- BM25 搜索增加 type_filter WHERE 子句
- source 类型文档加入搜索结果

### Step 13: 搜索索引增强
**文件:** `codewiki/mcp/cache.py`
- `_build_indexable_text()` (line 102): 新增可选 `page_type` 参数，aliases 3x boost，severity boost
- `build_search_index()` (line 499): 递归扫描 wiki/ 子目录，source 类型文档索引
- `search()` 方法: 支持 type_filter 过滤

### Step 14: 扩展 `lint_wiki`
**文件:** `codewiki/mcp/tools/wiki_lint.py`, `codewiki/mcp/server.py`
- `server.py` inputSchema checks enum 新增: `orphan_pages`, `no_outlinks`, `missing_aliases`, `stale_sources`
- 新增 4 个 check 函数
- `handle_lint_wiki` 返回值增加 `health_score` 字段（0-100）

### Step 15: 重构 `rebuild_index()`
**文件:** `codewiki/mcp/tools/wiki_index.py`
- 递归扫描 wiki/ 所有子目录
- 按 page_type 分区渲染（modules/entities/concepts/sources/comparisons/queries）
- index.md 顶部展示 Health Score
- `_EXCLUDED_FROM_INDEX` 扩展: 增加 overview.md, schema.yaml, purpose.md
- `append_log()` 路径改为 wiki/log.md

### Step 16: 适配其余文件
- `agents_md.py:93-112` — 模块链接改为 `{rel_path}/wiki/modules/{m}.md`, overview/index 改为 `{rel_path}/wiki/`
- `workspace_analyzer.py:73,100,180` — overview.md 路径检查兼容 wiki/overview.md
- `server.py:700-703` close_session — index/log 路径使用 wiki/

## 执行方式

- 按 Step 1-16 顺序逐步实现，每步完成后验证再进入下一步
- Step 1-5（基础设施）是最高风险阶段，涉及 11 个文件的路径统一化，需仔细验证
- Step 6-10（新工具）相对独立，可快速推进
- Step 11-16（增强）依赖前面步骤的接口定义

## 验证策略

1. **单元测试**: 对 `page_router.py` 的路径解析写 pytest，覆盖所有 page_type
2. **集成验证**: 对 WeKnora 项目自身运行 `analyze_repo` + `write_doc_file`(page_type=entity) 验证文件路由
3. **搜索验证**: ingest 一个 source 文档后 `query_wiki` 验证 BM25 命中
4. **Lint 验证**: 故意创建孤立页面，`lint_wiki` 验证 orphan_pages 检出
5. **索引验证**: 运行完整 pipeline 后检查 index.md 是否按类型分区展示

## 关键文件路径

| 文件 | 修改类型 |
|------|----------|
| `codewiki/src/config.py` | 新增常量 |
| `codewiki/mcp/tools/page_router.py` | **新建** |
| `codewiki/mcp/tools/source_ingest.py` | **新建** |
| `codewiki/mcp/tools/batch_ingest.py` | **新建** |
| `codewiki/mcp/tools/issue_tracker.py` | **新建** |
| `codewiki/mcp/tools/doc_writer.py` | 重写路径+扩展 frontmatter |
| `codewiki/mcp/tools/knowledge_loop.py` | 扩展 ingest_note/query_wiki |
| `codewiki/mcp/tools/wiki_index.py` | 重构 rebuild_index |
| `codewiki/mcp/tools/wiki_lint.py` | 新增检查项+health score |
| `codewiki/mcp/tools/wiki_search.py` | 递归扫描 |
| `codewiki/mcp/tools/prompt_server.py` | 7 个新 prompt_type |
| `codewiki/mcp/tools/schema_generator.py` | page_types 路由表 |
| `codewiki/mcp/tools/agents_md.py` | 链接路径适配 |
| `codewiki/mcp/tools/workspace_analyzer.py` | overview 路径兼容 |
| `codewiki/mcp/cache.py` | 递归索引+aliases boost |
| `codewiki/mcp/server.py` | 新工具注册+inputSchema |
| `codewiki/src/be/prompt_template.py` | 7 个新模板 |
