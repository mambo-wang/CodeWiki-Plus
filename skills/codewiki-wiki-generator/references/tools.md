# 工具速查表

## CodeWiki 工具（必需）

| 工具 | 用途 | 关键参数 | 数据流 |
|------|------|----------|--------|
| `analyze_repo` | 分析仓库，构建依赖图 | `repo_path`, `output_dir`, `include_patterns`, `exclude_patterns` | 写 summary.json/changes.json 到 workspace，返回路径 + 统计 |
| `list_components` | 获取组件列表 | `session_id`, `summary`(bool), `file_prefix`(string) | `summary=true` → component_summary.json；否则 → component_list.json。返回 `{file, total}` |
| `read_code_components` | 获取组件源码 | `session_id`, `component_ids`(string[]) | 每个组件写入 sources/*.src，返回路径 |
| `write_doc_file` | 创建 .md 文档 | `session_id`, `filename`, `content`, `page_type`(module/entity/concept/source/comparison/query), `frontmatter_extra`(object) | 按 page_type 路由到 wiki/ 子目录，自动 Mermaid 校验 |
| `edit_doc_file` | 编辑文档 | `session_id`, `filename`, `command`(str_replace/insert/undo) | 直接改文件 |
| `save_module_tree` | 保存模块聚类 | `session_id`, `module_tree`(object) | 写 .meta/module_tree.json + processing_order.json |
| `get_processing_order` | 获取叶优先处理顺序 | `session_id` | 写 processing_order.json，返回路径 |
| `get_prompt` | 获取提示词模板 | `prompt_type`(cluster/system_leaf/overview_module/overview_repo/entity_page/concept_page/source_summary/comparison_page/query_page/taxonomy_plan/extraction_scan/wiki_knowledge_loop/wiki_lint_report), `variables`(object) | 内联返回（数据量小） |
| `close_session` | 关闭会话释放资源 | `session_id` | 清理 workspace 文件 |

### list_components 模式对比

| 模式 | 参数 | 输出文件 | 体积 | 适用场景 |
|------|------|----------|------|----------|
| 完整列表 | 无额外参数 | component_list.json | 大 | 需要完整组件 ID 时 |
| 按目录过滤 | `file_prefix: "src/engine/"` | component_list.json | 中 | 阶段 3 按模块获取 |
| 摘要模式 | `summary: true` | component_summary.json | 小（~1/8） | 阶段 1-2 快速了解结构 |

### edit_doc_file 命令

| 命令 | 用途 | 额外参数 |
|------|------|----------|
| `str_replace` | 替换文本 | `old_str`, `new_str` |
| `insert` | 插入文本 | `insert_str`, `line_number` |
| `undo` | 撤销上次编辑 | 无 |

## LLM Wiki 工具（知识库）

Wiki 生成完成后的日常知识管理工具，无需 session 即可使用（通过 `output_dir` 定位 wiki）。

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `query_wiki` | 搜索文档和笔记，返回排序结果 + 上下文片段 | `query`, `scope`(支持目录前缀), `expand_terms`, `include_notes`, `include_code_refs`, `include_sources`, `type_filter`(module/entity/concept/source/comparison/query), `max_results` |
| `ingest_note` | 归档决策/经验/架构/踩坑/临时方案到知识库 | `title`, `content`, `note_type`(decision/lesson/architecture/bug_fix/pitfall/known_issue/workaround/general), `related_modules`, `severity`, `root_cause`, `source_ref`, `aliases` |
| `lint_wiki` | 文档-代码一致性检查（9 项）+ health_score | `checks`(stale_refs/undocumented/broken_links/cycles/coverage/orphan_pages/no_outlinks/missing_aliases/stale_sources) |
| `ingest_source` | 导入第三方文档到 raw/sources/ | `name`, `source_type`(api_doc/rfc/spec/design_doc/manual/other), `source_path`, `description`, `related_pages`, `version` |
| `retract_source` | 撤回已导入的外部文档 | `source_name`, `mode`(flag_stale/remove_refs) |
| `batch_ingest` | 批量导入多个笔记/文档 | `items`(列表，每项含 item_type:note/source), `items_file`(JSON 文件路径) |
| `flag_issue` | 标记 Wiki 质量问题到 issues.json | `issue_type`(broken_link/missing_doc/inconsistent/outdated/orphan), `page_path`, `severity`(error/warning/info), `description` |
| `list_dependencies` | 查询组件/模块依赖关系 | `session_id`, `component_id`, `direction`(upstream/downstream/both), `page`, `page_size` |

## CodeGraph 工具（可选增强）

| 工具 | 用途 | 使用阶段 |
|------|------|----------|
| `codegraph_status` | 索引健康检查 | 阶段 0 + 阶段 1 |
| `codegraph_files` | 文件树 + 每文件符号数 | 阶段 1 |
| `codegraph_explore` | 源码 + 调用路径（主力工具） | 阶段 1-3 |
| `codegraph_node` | 单个符号详情 + 源码 | 阶段 3 |
| `codegraph_callers` | 谁调用了某个符号 | 阶段 2 + 阶段 3 |
| `codegraph_callees` | 某个符号调用了谁 | 阶段 2 + 阶段 3 |
| `codegraph_impact` | 变更影响范围 | 阶段 3 + 增量更新 |
| `codegraph_search` | 按名称查找符号 | 阶段 2 |
