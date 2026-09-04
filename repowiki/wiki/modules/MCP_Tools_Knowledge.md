---
title: MCP_Tools_Knowledge
type: Module
generated:
  by: codewiki/5.2.0
  at: 2026-08-02 23:41:39+00:00
stale_after: '2027-02-22'
metadata:
  depth: 2
  module_type: leaf
  component_count: 41
  generated_by: codewiki
  generator_version: '1.0'
  updated_at: 2026-07-28
description: '`MCP_Tools_Knowledge` 是 CodeWiki MCP 服务的知识库工具集（leaf 模块），聚焦于**离线知识沉淀与检索闭环**：从源码/AGENTS.md
  生成结构化文档，录入笔记要点，并提供多模式的 Wiki 查询能力。'
aliases:
- MCP_Tools_Knowledge
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:19Z'
sources:
- id: repo://codewiki/mcp/tools/task_manager.py#L87-L110
  resource: repo://codewiki/mcp/tools/task_manager.py#L87-L110
  content_hash: sha256:af2b8ecd5393c303553a4e605752b04fa718992dced47c09500f80d6cb8709d9
- id: repo://codewiki/mcp/tools/note_query.py#L118-L150
  resource: repo://codewiki/mcp/tools/note_query.py#L118-L150
  content_hash: sha256:4e4d584abb75839e2f6551ca8f7fcfd3bc3b5605c1aa959c13321f8652673c22
- id: repo://codewiki/mcp/tools/note_writer.py#L36-L70
  resource: repo://codewiki/mcp/tools/note_writer.py#L36-L70
  content_hash: sha256:33c885523cc9aa526df1238fe5a264128cb8ea3482a94b8ae1ff94d471329986
- id: repo://codewiki/mcp/tools/note_types.py#L93-L130
  resource: repo://codewiki/mcp/tools/note_types.py#L93-L130
  content_hash: sha256:9499d922e51fd20f72228bc259386b5043f097901dfb60995dd580160b7a16bd
- id: repo://codewiki/mcp/tools/note_consolidation.py#L231-L270
  resource: repo://codewiki/mcp/tools/note_consolidation.py#L231-L270
  content_hash: sha256:b0c89f0634d1727f9e45e86324f1e0f5830c7a4149cefb6768eff835755be58e
- id: repo://codewiki/mcp/tools/distill_conversation.py#L341-L399
  resource: repo://codewiki/mcp/tools/distill_conversation.py#L341-L399
  content_hash: sha256:cb66ba5412ba9f86aed92fcea5c1e509e57b5d5487e4b98f41563be3248062fa
- id: repo://codewiki/mcp/tools/hook_registry.py#L31-L71
  resource: repo://codewiki/mcp/tools/hook_registry.py#L31-L71
  content_hash: sha256:ad0ab76fd97983b71d5c74fd62578bbe8bac67bac67ab6d8e1a7d32712edada0
---

# MCP_Tools_Knowledge 模块文档

## 概述

`MCP_Tools_Knowledge` 是 CodeWiki MCP 服务的知识库工具集（leaf 模块），聚焦于**离线知识沉淀与检索闭环**：从源码/AGENTS.md 生成结构化文档，录入笔记要点，并提供多模式的 Wiki 查询能力。包含 6 个源文件、44 个组件，对外暴露 10 个 `handle_*` 工具入口，内部由大量 `_` 私有辅助函数支撑解析、匹配、打分与符号链接注入。

## 组件清单

| 组件 | 类型 | 文件 | 职责 |
|------|------|------|------|
| `handle_query_wiki` | 公开 | knowledge_loop.py | Wiki 多模式查询总入口（overview/directory/detail） |
| `handle_ingest_note` | 公开 | knowledge_loop.py | 接收用户笔记要点并暂存为待确认 note |
| `handle_confirm_note` | 公开 | knowledge_loop.py | 确认 note，注入到对应模块文档 |
| `handle_reject_note` | 公开 | knowledge_loop.py | 拒绝 note，标记状态 |
| `handle_batch_ingest` | 公开 | batch_ingest.py | 批量摄入 notes/sources；完整逐项报告落盘 `.meta/batch_ingest_report.json`，返回值仅含摘要与报告路径 |
| `handle_read_code_components` | 公开 | code_reader.py | 读取代码组件（类/函数）用于文档生成 |
| `handle_view_repo_file` | 公开 | file_viewer.py | 查看仓库内文件内容 |
| `handle_ingest_source` | 公开 | source_ingest.py | 摄入源文件并建立 source→doc 注册表 |
| `handle_retract_source` | 公开 | source_ingest.py | 撤回已摄入的源文件 |
| `write_agents_md` | 公开 | agents_md.py | 生成 AGENTS.md 入口文档 |
| `_extract_*` (`_extract_frontmatter`,`_extract_frontmatter_block`,`_extract_keywords`,`_extract_section`,`_extract_tags`,`_get_module_components`,`_get_module_doc_name`) | 私有 | knowledge_loop.py | 从文档抽取 frontmatter/关键词/段落/标签与模块组件映射 |
| `_query_mode_*` (`_query_mode_overview`,`_query_mode_directory`,`_query_mode_detail`) | 私有 | knowledge_loop.py | 三种查询模式的内部实现 |
| `_` 其他辅助 (`_auto_match_modules`,`_collect`,`_walk`,`_load_symbol_map`,`_inject_symbol_links`,`_replace_symbol`,`_protect`,`_resolve_within`,`_score_document`,`_slugify`,`_legacy_keyword_search`,`_update_note_status`) | 私有 | knowledge_loop.py | 模块自动匹配、目录遍历、符号映射/链接注入、文档打分、slug 化与状态更新 |
| `_build_section` / `_extract_modules` / `_write_agents_md` | 私有 | agents_md.py | 构建 AGENTS.md 章节、解析模块列表、落盘写入 |
| `_read_source_from_disk` | 私有 | code_reader.py | 从磁盘读取源文件内容 |
| `_clean_source_refs` / `_count_source_refs` / `_load_registry` / `_resolve_output_dir` / `_save_registry` | 私有 | source_ingest.py | 源引用清理/计数、注册表加载/保存、输出目录解析 |
| `create_task` / `list_tasks` / `get_task` / `get_task_context` / `complete_task` / `delete_task` / `set_session_task` / `add_task_memory` / `compact_task_memories` | 公开 | task_manager.py | 任务记忆工具族：任务 CRUD、会话绑定、记忆追加/上下文拉取与压缩 |
| `_read_index` / `_find_by_id` | 私有 | task_manager.py | 读取任务索引（tasks/ 目录为真相的缓存）；按 id 查找任务 |
| `_extract_frontmatter_block` | 私有 | note_query.py | 从笔记文本切出 frontmatter 块，供检索/去重前解析 |
| `_norm_status` | 私有 | note_writer.py | 规范化笔记 status 值（别名归一、非法回退） |
| `load_note_types` | 私有 | note_types.py | 从 schema 加载 note_type 定义（约束笔记类型集合） |
| `_scan_scenarios` | 私有 | note_consolidation.py | 扫描 scenarios 目录待聚合入口笔记（consolidate 前置） |
| `_unquote_fm` | 私有 | distill_conversation.py | 兼容层：剥离旧 raw 笔记中残留的包裹引号（统一 frontmatter reader 已做 json 解码） |
| `load_registry` | 私有 | hook_registry.py | 读取 IDE hook 注册表（启用的 hook 清单） |

## 关键设计

1. **查询三模式**：`overview` 给目录鸟瞰，`directory` 列模块与组件，`detail` 深入单模块文档并注入符号链接。
2. **符号链接注入**：`_load_symbol_map` + `_inject_symbol_links` + `_replace_symbol` 将文档中的 `[[Symbol]]` 跨文档互链，提升可导航性。
3. **笔记闭环**：`ingest→confirm/reject` 状态机（`_update_note_status`）保证用户知识可控沉淀。
4. **源注册表**：source_ingest 维护 registry 记录 source 与生成 doc 的映射，支持 retract 回滚。
5. **AGENTS.md 自动生成**：从各模块 frontmatter 抽取组件，聚合为仓库入口文档。
6. **大载荷报告落盘**：`handle_batch_ingest` 将完整逐项结果写入 `<output_dir>/.meta/batch_ingest_report.json`，返回值仅含 `summary` 与 `report_file` 路径，避免 MCP 通道大载荷超时；调用方可用 `view_repo_file` 读取报告详情。无 `output_dir` 时退回内联 `results`。
7. **任务记忆与笔记同管**：`task_manager` 是任务记忆工具族（与笔记笔记知识同属知识沉淀闭环），索引读取走 [KnowledgeStore](KnowledgeStore.md) 的「目录为真相、缓存校验重建」约定（`_read_index`/`_find_by_id` 支撑会话绑定与上下文拉取）。
8. **知识工具家族拆分**：note/task/distill/hook 从 `knowledge_loop` 大文件中拆出后各自独立成文件，仍共享同一套 frontmatter 收敛点；统一 reader 落地后，旧式手工剥引号补丁（`_unquote_fm`）降级为兼容层只处理历史遗留值。

## 数据流（mermaid）

```mermaid
flowchart LR
  A[handle_ingest_source] --> B[_load_registry/_resolve_output_dir]
  B --> C[生成 doc + _save_registry]
  D[handle_batch_ingest] --> E[handle_read_code_components]
  E --> F[_read_source_from_disk]
  F --> G[write_agents_md/_write_agents_md]
  H[handle_ingest_note] --> I[_auto_match_modules]
  I --> J[待确认 note]
  J --> K[handle_confirm_note/handle_reject_note]
  K --> L[_update_note_status + _inject_symbol_links]
  M[handle_query_wiki] --> N[_query_mode_overview/_directory/_detail]
  N --> O[_score_document/_extract_*]
  O --> P[返回 Wiki 内容]
```

## 依赖关系

- [MCP_Server](MCP_Server.md)：注册并调度上述 `handle_*` 工具。
- [MCP_Core](MCP_Core.md)：复用知识库读写与文档模型。
- [MCP_Cache](MCP_Cache.md)：缓存 symbol map 与查询结果。
- [MCP_Tools_Quality](MCP_Tools_Quality.md)：文档质量校验（注入前）。
- [SharedConfig](SharedConfig.md)：仓库路径、输出目录等配置。

## 使用示例

```python
# 摄入源码并生成文档
await handle_ingest_source(repo="myrepo", paths=["src/foo.py"])
resp = await handle_batch_ingest(repo="myrepo", items=[{"kind": "source", "paths": ["src/"]}])
# resp 含 status/total/succeeded/failed 与 report_file（如 .meta/batch_ingest_report.json）
# 完整逐项结果用 view_repo_file 读取该报告

# 用户补充知识
await handle_ingest_note(repo="myrepo", text="Foo 负责鉴权", module="Foo")
await handle_confirm_note(repo="myrepo", note_id="n1")

# 查询 Wiki
result = await handle_query_wiki(repo="myrepo", mode="detail", module="Foo")
```

## 扩展点（新增知识库工具）

1. 在 `knowledge_loop.py` 新增 `handle_*` 并复用 `_extract_*`/`_score_document` 辅助。
2. 新增查询模式：扩展 `_query_mode_*` 并在 `handle_query_wiki` 分发。
3. 新的摄入源类型：仿 `source_ingest.py` 增加 registry 维护函数。
4. AGENTS.md 模板扩展：`_build_section` 支持新 frontmatter 字段。

## 相关模块

[MCP_Server](MCP_Server.md) [MCP_Core](MCP_Core.md) [MCP_Cache](MCP_Cache.md) [MCP_Tools_Quality](MCP_Tools_Quality.md) [MCP_Tools_DocWriter](MCP_Tools_DocWriter.md) [MCP_Tools_Analysis](MCP_Tools_Analysis.md) [SharedConfig](SharedConfig.md) [LLM_Backend](LLM_Backend.md)
