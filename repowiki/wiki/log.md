# 操作日志

> 本文件为追加写入的操作记录，由系统自动维护

## 2026-08-13
* **lint_wiki**: 检查完成: 53 个问题
* **lint_wiki**: 检查完成: 53 个问题
* **lint_wiki**: 检查完成: 53 个问题

## 2026-08-12
* **ingest_note**: 添加笔记: IDE hook 采用「同步采集 + 异步蒸馏」两段式执行模型
* **ingest_note**: 添加笔记: repowiki/raw/ 目录堆积会使同步捕获线性变慢，逼近 60s 超时
* **ingest_note**: 添加笔记: TencentDB-Agent-Memory 四层记忆金字塔：逐层蒸馏 + 触发式调度
* **ingest_note**: 添加笔记: query_wiki 的 output_dir 非必填，解析顺序为 output_dir → session → repo_path
* **ingest_note**: 添加笔记: MCP 工具无法自动探测当前项目路径，需显式传 repo_path
* **ingest_note**: 添加笔记: resolve_session 恢复的 session.output_dir 会覆盖 repo_path 推断，导致 Note not found
* **ingest_note**: 添加笔记: confirm_note/reject_note 的 output_dir 解析顺序改为 output_dir → repo_path → session
* **ingest_note**: 添加笔记: CodeBuddy IDE 把系统上下文注入 user 消息，采集时必须剥离系统标签块
* **ingest_note**: 添加笔记: 块剥离正则不要用 ^ 行首锚点：系统块前可能有 user: 前缀
* **analyze_repo**: 分析仓库 CodeWiki-CN，1311 个组件

## 2026-08-09
* **ingest_note**: 添加笔记: CodeBuddy index.json transcript 是裸 JSON 数组，_load_transcript 必须支持 list 顶层展开
* **ingest_note**: 添加笔记: Windows 下 hook 按 sys.stdin.read() 读取中文事件会崩溃，必须按字节读 + 显式 UTF-8 解码
* **ingest_note**: 添加笔记: 同一会话的 PreCompact/Stop 不带 transcript_path，落空信封会被 duplicate 去重，应视为 no-op
* **ingest_note**: 添加笔记: hook 事件信封合成时须置空 source_session_id，否则 supersede 会覆盖真实 transcript（数据丢失）
* **ingest_note**: 添加笔记: 归档对话文件名用用户首句 slug，且与 conversation_id 必须一致（蒸馏链路依赖此约束）
* **ingest_note**: 添加笔记: 无知识的 raw 对话蒸馏后也应清理，删除条件要用 produced is not None 而非 truthy

## 2026-08-08
* **capture_conversation**: 采集对话: conv-20260808T081955Z.md (2 turns, link_to=-)
* **ingest_note**: 添加笔记: CodeBuddy IDE transcript_path 指向的 index.json 只存元数据，真实内容在 messages/<id>.json

## 2026-08-06
* **capture_conversation**: 采集对话: conv-20260806T013027Z.md (2 turns, link_to=-)

## 2026-08-05
* **capture_conversation**: 采集对话: conv-20260805T075743Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T103603Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T104343Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T104547Z.md (2 turns, link_to=-)

## 2026-08-03
* **lint_wiki**: 检查完成: 27 个问题

<!-- 以下为 v5.1.x 旧格式日志存档 -->
| 时间 | 操作 | 说明 |
|------|------|------|
| 2026-07-28T11:52:32+08:00 | analyze_repo | 分析仓库 CodeWiki-CN，528 个组件 |
| 2026-07-28T11:57:00+08:00 | write_doc_file | 创建 /Users/kirito/repos/CodeWiki-CN/repowiki/wiki/modules/CLI_Adapter.md |
| 2026-07-28T18:00:00+08:00 | write_doc_file (批量) | 生成其余 25 个模块文档：CLI / CLI_Commands / CLI_Config / CLI_Utils / DependencyAnalyzer / AnalysisPipeline / AnalyzerModels / AnalyzerUtils / GraphAndSort / LanguageAnalyzers / RouteExtractors / Frontend / DocVisualizer / WebApp / LLM_Backend / SharedConfig / MCP_Server / MCP_Cache / MCP_Core / MCP_Prompts / MCP_Tools_Analysis / MCP_Tools_Dependency / MCP_Tools_DocWriter / MCP_Tools_Knowledge / MCP_Tools_Quality |
| 2026-07-28T18:00:00+08:00 | rebuild_index | 重建 index.md（26 个模块文档索引）与 overview.md（仓库架构总览） |
| 2026-07-28T12:49:03+08:00 | close_session | 会话关闭 |
| 2026-07-28T13:06:32+08:00 | analyze_repo | 分析仓库 CodeWiki-CN，528 个组件 |
| 2026-07-28T13:09:33+08:00 | write_doc_file | 创建 mcp_smoke_test.md |
| 2026-07-28T13:09:36+08:00 | ingest_source | 导入外部文档: mcp_smoke_src_a (md) |
| 2026-07-28T13:09:37+08:00 | ingest_note | 添加笔记: MCP_TEST_BATCH_NOTE |
| 2026-07-28T13:09:37+08:00 | ingest_source | 导入外部文档: mcp_smoke_src_b (md) |
| 2026-07-28T13:09:38+08:00 | batch_ingest | 批量导入完成: 2 成功, 0 失败 |
| 2026-07-28T13:09:40+08:00 | ingest_note | 添加笔记: MCP_TEST_SMOKE_NOTE |
| 2026-07-28T13:09:51+08:00 | flag_issue | 新增问题: [orphan_page] wiki/queries/mcp_smoke_test.md |
| 2026-07-28T13:10:09+08:00 | retract_source | 撤回外部文档: mcp_smoke_src_a (mode=remove_refs) |
| 2026-07-28T13:10:10+08:00 | retract_source | 撤回外部文档: mcp_smoke_src_b (mode=remove_refs) |
| 2026-07-28T13:11:07+08:00 | write_doc_file | 创建 mcp_smoke_test.md |
| 2026-07-28T13:11:42+08:00 | edit_doc_file | 更新 mcp_smoke_test.md (str_replace) |
| 2026-07-28T13:12:40+08:00 | close_session | 会话关闭 |
| 2026-07-28T13:12:44+08:00 | lint_wiki | 检查完成: 80 个问题 |
| 2026-07-28T13:42:56+08:00 | lint_wiki | 检查完成: 1 个问题 |
| 2026-07-28T13:43:30+08:00 | edit_doc_file | 更新 _tmp_edit_test.md (str_replace) |
| 2026-07-28T13:43:31+08:00 | edit_doc_file | 更新 _tmp_edit_test.md (str_replace) |
| 2026-07-28T13:48:25+08:00 | flag_issue | 新增问题: [broken_link] wiki/modules/X.md |
| 2026-07-28T13:48:25+08:00 | flag_issue | 新增问题: [custom] p |
| 2026-07-28T14:09:25+08:00 | lint_wiki | 检查完成: 3 个问题 |
| 2026-07-28T14:09:26+08:00 | flag_issue | 新增问题: [custom] wiki/modules/_retest.md |
| 2026-07-28T14:10:00+08:00 | lint_wiki | 检查完成: 1 个问题 |
| 2026-07-28T14:10:06+08:00 | edit_doc_file | 更新 MCP_Cache.md (str_replace) |
| 2026-07-28T14:10:22+08:00 | edit_doc_file | 撤销 MCP_Cache.md |
| 2026-07-28T14:11:28+08:00 | close_session | 会话关闭 |
| 2026-07-28T14:11:33+08:00 | lint_wiki | 检查完成: 1 个问题 |
* **lint_wiki**: 检查完成: 27 个问题
* **ingest_note**: 添加笔记: MCP 工具 schema 不声明 session_id，handler 隐式读取
* **ingest_note**: 添加笔记: Entity/Concept 提取采用 WeKnora 式两阶段流程（P0：纯 prompt 协议）
* **ingest_source**: 导入外部文档: README_CN (md)
* **write_doc_file**: 创建 README_CN.md
* **write_doc_file**: 创建 WeKnora.md
* **write_doc_file**: 创建 Langfuse.md
* **write_doc_file**: 创建 微信对话开放平台.md
* **write_doc_file**: 创建 ClawHubSkill.md
* **write_doc_file**: 创建 RAG.md
* **write_doc_file**: 创建 ReActAgent.md
* **write_doc_file**: 创建 Wiki模式.md
* **write_doc_file**: 创建 文档知识图谱.md
* **write_doc_file**: 创建 空间RBAC.md
* **write_doc_file**: 创建 混合检索策略.md
* **close_session**: 会话关闭
* **close_session**: 会话关闭
* **close_session**: 会话关闭
* **analyze_repo**: 分析仓库 CodeWiki-CN，1248 个组件
* **ingest_note**: 添加笔记: 检索引擎架构说明
* **close_session**: 会话关闭
