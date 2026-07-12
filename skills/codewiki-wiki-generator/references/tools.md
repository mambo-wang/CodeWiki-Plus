# 工具速查表

## CodeWiki 工具（必需）

| 工具 | 用途 | 关键参数 | 数据流 |
|------|------|----------|--------|
| `analyze_repo` | 分析仓库，构建依赖图 | `repo_path`, `output_dir`, `include_patterns`, `exclude_patterns` | 写 summary.json/changes.json 到 workspace，返回路径 + 统计 |
| `list_components` | 获取组件列表 | `session_id`, `summary`(bool), `file_prefix`(string) | `summary=true` → component_summary.json；否则 → component_list.json。返回 `{file, total}` |
| `read_code_components` | 获取组件源码 | `session_id`, `component_ids`(string[]) | 每个组件写入 sources/*.src，返回路径 |
| `write_doc_file` | 创建 .md 文档 | `session_id`, `filename`, `content` | 直接写文件，自动 Mermaid 校验 |
| `edit_doc_file` | 编辑文档 | `session_id`, `filename`, `command`(str_replace/insert/undo) | 直接改文件 |
| `save_module_tree` | 保存模块聚类 | `session_id`, `module_tree`(object) | 写 .meta/module_tree.json + processing_order.json |
| `get_processing_order` | 获取叶优先处理顺序 | `session_id` | 写 processing_order.json，返回路径 |
| `get_prompt` | 获取提示词模板 | `prompt_type`(cluster/system_leaf/overview_module/overview_repo), `variables`(object) | 内联返回（数据量小） |
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
| `query_wiki` | 搜索文档和笔记，返回排序结果 + 上下文片段 | `query`, `scope`, `expand_terms`, `include_notes`, `include_code_refs`, `max_results` |
| `ingest_note` | 归档决策/经验/架构说明到知识库 | `title`, `content`, `note_type`, `related_modules` |
| `lint_wiki` | 文档-代码一致性检查（5 项） | 无参数（自动扫描 output_dir） |

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
