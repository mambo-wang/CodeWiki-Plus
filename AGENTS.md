<!-- CodeWiki LLM Wiki -->

## CodeWiki LLM Wiki

本项目已使用 [CodeWiki](https://github.com/mambo-wang/CodeWiki-CN) 生成 LLM Wiki 文档，位于 `repowiki/` 目录。

**入口文件：**

- [`repowiki/wiki/overview.md`](repowiki/wiki/overview.md) — 仓库级架构总览（含 Mermaid 架构图）
- [`repowiki/wiki/index.md`](repowiki/wiki/index.md) — 文档目录与知识笔记索引
- [`repowiki/wiki/schema.yaml`](repowiki/wiki/schema.yaml) — 项目文档约定（命名规范、必填章节等）

### MCP 工具用法

如果当前 IDE 已配置 CodeWiki MCP 服务器，可直接使用以下工具：

**查询文档和笔记（query_wiki）：**

```json
{
  "query": "如何处理依赖分析",
  "scope": "模块名（可选，限定搜索范围）",
  "include_notes": true,
  "include_code_refs": true,
  "max_results": 10,
  "expand_terms": ["依赖图", "依赖追踪"]
}
```

返回排序后的匹配结果（含上下文片段）和相关组件 ID。在编码、调试或做设计决策时，先查询 wiki 获取相关上下文。

**归档决策/经验教训（ingest_note）：**

```json
{
  "note_type": "decision",
  "title": "选择 SQLite 作为缓存后端",
  "content": "选择原因：...",
  "related_modules": ["模块名"]
}
```

`note_type` 可选值：`decision`（设计决策）、`lesson`（经验教训）、`architecture`（架构说明）、`bug_fix`（Bug 修复记录）、`general`（通用笔记）。笔记存储在 `repowiki/notes/` 目录，可被 `query_wiki` 检索。

**文档一致性检查（lint_wiki）：**

```json
{}
```

检查文档与代码是否一致，包括：过时引用、断链、未文档化组件、循环依赖、覆盖率。

### MCP 工具参数速查

以下为全部 25 个工具的**必填参数**（其余均为可选）。参数名以 MCP server 强制校验的 schema 为准，传错参数名会被 server 直接拒绝。

> 常见陷阱：`analyze_repo` / `analyze_workspace` 会返回 `session_id`，但**下游工具并不接收 `session_id`**，请改用 `repo_path` 或 `output_dir`。

| 工具 | 必填参数 | 常用可选参数 |
| --- | --- | --- |
| analyze_repo | repo_path | include_patterns, output_dir, exclude_patterns, max_workers |
| read_code_components | repo_path, component_ids | include_bodies, include_source_refs |
| write_doc_file | output_dir, filename, content | page_type, frontmatter, content_file |
| edit_doc_file | output_dir, filename, command | page_type, old_str, new_str, target_heading |
| save_module_tree | repo_path | module_tree, module_tree_file |
| get_processing_order | repo_path | — |
| get_prompt | prompt_type | variables, repo_path |
| close_session | repo_path | — |
| list_dependencies | repo_path | component_ids, direction, dependency_types, max_depth |
| analyze_impact | repo_path, component_ids | direction, max_depth, include_paths |
| lint_wiki | output_dir | checks, severity_filter, page_types |
| ingest_note | output_dir, note_type, title, content | aliases, related_modules |
| query_wiki | output_dir, query | scope, type_filter, include_notes, max_results, expand |
| confirm_note | output_dir, note_file | — |
| reject_note | output_dir, note_file | reason |
| ingest_source | output_dir, source_path | name, description, source_type |
| retract_source | output_dir | name, source_id, mode, dry_run |
| batch_ingest | output_dir, items | — |
| flag_issue | output_dir, issue_type, page_path, description | severity, related_components |
| analyze_workspace | workspace_path | output_dir, include_patterns, max_workers |
| list_components | repo_path | component_types, file_path, name_pattern |
| view_repo_file | repo_path, path | max_lines, line_offset, include_line_numbers |
| query_cross_service | workspace_path | filter_type, repo_name, http_method, min_confidence |
| get_module_tree | repo_path, wiki_base_dir | — |
| generate_docs | repo_path, wiki_base_dir | page_types, max_workers |

注：`generate_docs`（legacy）会调用火山引擎方舟（Volcengine Ark）远程 LLM 生成文档，需配置有效 CodingPlan 订阅；未配置时返回 `InvalidSubscription`。

### 使用建议

1. **编码前**：先用 `query_wiki` 搜索相关模块文档，了解架构约定和依赖关系
2. **做决策时**：用 `query_wiki` 搜索已有的 `decision` 类型笔记，避免重复讨论
3. **完成重要决策后**：用 `ingest_note` 归档，让未来的 Agent 和团队成员都能查到
4. **定期维护**：用 `lint_wiki` 检查文档是否过时，保持文档与代码同步

### 纠正识别与经验沉淀

当你被用户纠正、吐槽或补充了未知上下文时，这可能是值得沉淀的经验。按以下规则处理：

**识别纠正信号（满足任一即触发）：**

- 用户明确否定你的输出："不对""你搞错了""不是这样的""应该是…"
- 用户表达重复犯错的不满："又…""上次就…""为什么又…"
- 你修改了自己的输出后用户仍不满意，说明理解有根本偏差
- 用户补充了你不知道的关键上下文："你不知道吗…""这个项目一直都是…""我们约定过…"
- 用户指出方法名/Javadoc 与实际行为不一致，或指出代码中的历史遗留问题

**执行三步流程：**

1. **反思**：明确说出自己错在哪里、正确做法是什么、根因是什么（是缺少项目上下文？还是对代码理解有误？）
2. **起草笔记**：将教训整理为结构化内容，包含：背景（什么场景下犯了错）、正确做法、根因分析
3. **征求确认**：向用户展示笔记草稿，询问"要把这条经验记录到 Wiki 吗？"——**必须得到用户确认后才执行 `ingest_note`**，不要默默保存

**归档示例：**

```json
{
  "note_type": "lesson",
  "title": "OrderService.process() 只做参数校验不做业务处理",
  "content": "## 背景\n\nAgent 误以为 OrderService.process() 包含完整业务逻辑，基于方法名做了错误的设计假设。\n\n## 正确做法\n\nprocess() 仅做入参校验和格式化，实际业务处理在 OrderService.execute() 中。老项目方法名与实际行为不一致是常见情况，应优先阅读实现而非信任方法名。\n\n## 根因\n\n十几年老项目，方法经过多次重构但名称未更新。",
  "related_modules": ["order"]
}
```

**注意**：不是每次纠正都需要沉淀。只记录有复用价值的经验——特定于本次任务的临时调整、用户个人偏好等不需要记录。判断标准：如果未来的 Agent 或新同事遇到同样场景时这条经验有用，就值得记录。

<!-- /CodeWiki LLM Wiki -->
