---
okf_version: "0.2"
---

<!-- 自动生成于 2026-08-15T23:07:54+08:00 | Health Score: 0/100 | 本文件由系统自动维护 -->

# 项目文档索引

## 模块文档

* [AnalysisPipeline](modules/AnalysisPipeline.md) - title: AnalysisPipeline
* [AnalyzerModels](modules/AnalyzerModels.md) - title: AnalyzerModels
* [AnalyzerUtils](modules/AnalyzerUtils.md) - title: AnalyzerUtils
* [CLI](modules/CLI.md) - title: CLI
* [CLI_Adapter](modules/CLI_Adapter.md) - title: CLI_Adapter
* [CLI_Commands](modules/CLI_Commands.md) - title: CLI_Commands
* [CLI_Config](modules/CLI_Config.md) - title: CLI_Config
* [CLI_Utils 模块文档](modules/CLI_Utils.md) - title: CLI_Utils
* [DependencyAnalyzer](modules/DependencyAnalyzer.md) - title: DependencyAnalyzer
* [DocVisualizer](modules/DocVisualizer.md) - title: DocVisualizer
* [Frontend](modules/Frontend.md) - title: Frontend
* [GraphAndSort](modules/GraphAndSort.md) - title: GraphAndSort
* [LLM_Backend 模块文档](modules/LLM_Backend.md) - title: LLM_Backend
* [LanguageAnalyzers](modules/LanguageAnalyzers.md) - title: LanguageAnalyzers
* [MCP_Cache](modules/MCP_Cache.md) - title: MCP_Cache
* [MCP_Core](modules/MCP_Core.md) - title: MCP_Core
* [MCP_Prompts](modules/MCP_Prompts.md) - title: MCP_Prompts
* [MCP_Server](modules/MCP_Server.md) - title: MCP_Server
* [MCP_Tools_Analysis](modules/MCP_Tools_Analysis.md) - title: MCP_Tools_Analysis
* [MCP_Tools_Dependency](modules/MCP_Tools_Dependency.md) - title: MCP_Tools_Dependency
* [MCP_Tools_DocWriter 模块文档](modules/MCP_Tools_DocWriter.md) - title: MCP_Tools_DocWriter
* [MCP_Tools_Knowledge](modules/MCP_Tools_Knowledge.md) - title: MCP_Tools_Knowledge
* [MCP_Tools_Quality 模块文档](modules/MCP_Tools_Quality.md) - title: MCP_Tools_Quality
* [RouteExtractors 模块文档](modules/RouteExtractors.md) - title: RouteExtractors
* [SharedConfig](modules/SharedConfig.md) - title: SharedConfig
* [WebApp](modules/WebApp.md) - title: WebApp

## 实体

* [ClawHubSkill](entities/ClawHubSkill.md) - WeKnora 发布在 ClawHub 平台上的技能：文档导入、混合检索与知识管理
* [Langfuse](entities/Langfuse.md) - WeKnora 集成的全链路可观测性追踪后端，追踪 ReAct 循环、Token 消耗与任务流水线
* [WeKnora](entities/WeKnora.md) - 腾讯开源的企业级 LLM 知识管理框架：RAG 问答 + ReAct 推理 + 自动 Wiki 一体化
* [微信对话开放平台](entities/微信对话开放平台.md) - 微信生态智能问答平台，以 WeKnora 为核心技术框架，支持零代码部署与公众号/小程序集成

## 概念

* [RAG](concepts/RAG.md) - 检索增强生成：WeKnora 基于知识库的快速问答能力
* [ReActAgent](concepts/ReActAgent.md) - WeKnora 的 ReAct 多步推理能力：自主编排知识检索、MCP 工具与网络搜索
* [Wiki模式](concepts/Wiki模式.md) - WeKnora 的 Agent 驱动自动 Wiki 能力：从原始文档自治生成相互链接的 Markdown 知识页面
* [文档知识图谱](concepts/文档知识图谱.md) - WeKnora 将文档转化为段落关联知识图谱，为索引与检索提供结构化支撑
* [混合检索策略](concepts/混合检索策略.md) - WeKnora 检索策略组合：BM25 / Dense / GraphRAG / 父子分块 / 多维度索引
* [空间Rbac](concepts/空间RBAC.md) - WeKnora 多空间权限控制：四级角色矩阵 + 资源归属 + 空间审计日志

## 外部文档

* [README_CN](sources/README_CN.md) - WeKnora 中文 README（v0.7.0）源文档摘要：三大核心能力、部署方式、功能矩阵与集成生态

## 知识笔记

* [capture_conversation 的 task_id 需显式传入，绑定文件曾不被自动消费（已加回退修复）](../notes/2026-08-15-capture-conversation-的-task-id-需显式传入绑定文件曾不被自动消费已加回退修复.md) - pitfall (pitfall, 2026-08-15)
* [CodeBuddy hook 有源/项目双副本，改 task_session_start.py 需同步源副本才随包分发](../notes/2026-08-15-codebuddy-hook-有源项目双副本改-task-session-startpy-需同步源副本才随包分发.md) - pitfall (pitfall, 2026-08-15)
* [CodeWiki frontmatter 修补是 additive-only：LLM 直写的 status: draft 不会被默认 stable 覆盖](../notes/2026-08-15-codewiki-frontmatter-修补是-additive-onlyllm-直写的-status-draft-不.md) - architecture (architecture, 2026-08-15)
* [get_prompt 工具参数是 prompt_type 而非 name](../notes/2026-08-15-get-prompt-工具参数是-prompt-type-而非-name.md) - pitfall (pitfall, 2026-08-15)
* [hook 注入的 additionalContext 是软约束，需硬性执行顺序 + 直接注入任务标题才可靠](../notes/2026-08-15-hook-注入的-additionalcontext-是软约束需硬性执行顺序-直接注入任务标题才可靠.md) - lesson (lesson, 2026-08-15)
* [IDE hook 的 SessionEnd envelope 须用 user 角色，system 角色会被 transcript 提取丢弃](../notes/2026-08-15-ide-hook-的-sessionend-envelope-须用-user-角色system-角色会被-transcr.md) - pitfall (pitfall, 2026-08-15)
* [MCP server 层架构摩擦点扫描结论（7 项，按严重度排序）](../notes/2026-08-15-mcp-server-层架构摩擦点扫描结论7-项按严重度排序.md) - architecture (architecture, 2026-08-15)
* [MCP server 薄壳化架构：server.py 职责拆分到 registry/prompts/resources/tools](../notes/2026-08-15-mcp-server-薄壳化架构serverpy-职责拆分到-registrypromptsresourcestools.md) - architecture (architecture, 2026-08-15)
* [migrate_okf --fold-private 改行手术折叠避免跨行 flow 值 churn；新增 repair_double_quoted_escapes 先修复坏转义再折叠](../notes/2026-08-15-migrate-okf---fold-private-改行手术折叠避免跨行-flow-值-churn新增-repair.md) - decision (decision, 2026-08-15)
* [module_tree.json 的 children 是字符串引用而非嵌套对象](../notes/2026-08-15-module-treejson-的-children-是字符串引用而非嵌套对象.md) - pitfall (pitfall, 2026-08-15)
* [no_knowledge 的 raw 由 distill 清理删除，keep_raw 是唯一保留途径](../notes/2026-08-15-no-knowledge-的-raw-由-distill-清理删除keep-raw-是唯一保留途径.md) - pitfall (pitfall, 2026-08-15)
* [OKF §7 actor 约定是 codewiki/<version>，旧格式 agent:codewiki/ 已废弃](../notes/2026-08-15-okf-7-actor-约定是-codewikiversion旧格式-agentcodewiki-已废弃.md) - architecture (architecture, 2026-08-15)
* [OKF v0.2 §7 actor 格式：agent 应写 <producer>/<version>，agent: 前缀不在规范内，消费端仅凭 human: 前缀推导信任档位](../notes/2026-08-15-okf-v02-7-actor-格式agent-应写-producerversionagent-前缀不在规范内消费端仅凭.md) - lesson (lesson, 2026-08-15)
* [ontology.yaml 的 types/relations 是未实现的 schema 骨架，只有 terms 被消费](../notes/2026-08-15-ontologyyaml-的-typesrelations-是未实现的-schema-骨架只有-terms-被消费.md) - architecture (architecture, 2026-08-15)
* [output_dir 解析收敛方案：resolve_workspace 单点 + 优先级统一](../notes/2026-08-15-output-dir-解析收敛方案resolve-workspace-单点-优先级统一.md) - decision (decision, 2026-08-15)
* [PowerShell 下中文经命令行传参（git commit -m / python -c）会被 GBK 破坏，应改用 UTF-8 文件方式](../notes/2026-08-15-powershell-下中文经命令行传参git-commit--m-python--c会被-gbk-破坏应改用-utf.md) - workaround (workaround, 2026-08-15)
* [_process_llm_output 是蒸馏三种模式的共同落盘路径，改一处全覆盖](../notes/2026-08-15-process-llm-output-是蒸馏三种模式的共同落盘路径改一处全覆盖.md) - architecture (architecture, 2026-08-15)
* [query_wiki 索引机制：frontmatter 除 6 个 boost 字段外一律剥离不进 BM25，metadata 折叠与 json.dumps 转义不影响检索](../notes/2026-08-15-query-wiki-索引机制frontmatter-除-6-个-boost-字段外一律剥离不进-bm25metadat.md) - architecture (architecture, 2026-08-15)
* [task_bindings 只与任务存在性挂钩，不校验活跃/完成状态](../notes/2026-08-15-task-bindings-只与任务存在性挂钩不校验活跃完成状态.md) - architecture (architecture, 2026-08-15)
* [wiki_lint 需豁免 raw/ 根暂存层但保留 raw/sources/，RAW_DIR 须单独处理不可塞进 _scratch_dirs](../notes/2026-08-15-wiki-lint-需豁免-raw-根暂存层但保留-rawsourcesraw-dir-须单独处理不可塞进-scratc.md) - pitfall (pitfall, 2026-08-15)
* [wiki 页出现 \x00PROTxxxx\x00 占位符残留会使文件被判为 binary 无法读取](../notes/2026-08-15-wiki-页出现-x00protxxxxx00-占位符残留会使文件被判为-binary-无法读取.md) - pitfall (pitfall, 2026-08-15)
* [write_doc_file 默认 status=stable，与笔记/蒸馏的 draft 语义分层](../notes/2026-08-15-write-doc-file-默认-statusstable与笔记蒸馏的-draft-语义分层.md) - decision (decision, 2026-08-15)
* [YAML frontmatter 裸 f-string 插值 Windows 路径产生非法转义 \c 导致整个 frontmatter 无法解析（OKF §11 违规），字符串字段一律用 json.dumps 转义](../notes/2026-08-15-yaml-frontmatter-裸-f-string-插值-windows-路径产生非法转义-c-导致整个-front.md) - pitfall (pitfall, 2026-08-15)
* [任务归属在采集阶段决定，蒸馏仅读回 task_id 不做推断](../notes/2026-08-15-任务归属在采集阶段决定蒸馏仅读回-task-id-不做推断.md) - architecture (architecture, 2026-08-15)
* [任务记忆系统 grill 决策：绑定按 source_session_id 维度，注入走起 session 引导而非 hook 自动注入](../notes/2026-08-15-任务记忆系统-grill-决策绑定按-source-session-id-维度注入走起-session-引导而非-hoo.md) - decision (decision, 2026-08-15)
* [任务记忆蒸馏改为 pending 暂存 + 确认闸门，与笔记评审对齐](../notes/2026-08-15-任务记忆蒸馏改为-pending-暂存-确认闸门与笔记评审对齐.md) - decision (decision, 2026-08-15)
* [任务记忆采用单一 memories.md 追加式原子写，非每次新建文件](../notes/2026-08-15-任务记忆采用单一-memoriesmd-追加式原子写非每次新建文件.md) - architecture (architecture, 2026-08-15)
* [生成的 wiki 页面 status 为 draft 的根因排查：prompt 模板示例会误导 LLM](../notes/2026-08-15-生成的-wiki-页面-status-为-draft-的根因排查prompt-模板示例会误导-llm.md) - lesson (lesson, 2026-08-15)
* [私有键统一折叠进 metadata:（单行 JSON 值）形成闭环，防止全量生成恢复顶层键](../notes/2026-08-15-私有键统一折叠进-metadata单行-json-值形成闭环防止全量生成恢复顶层键.md) - decision (decision, 2026-08-15)
* [蒸馏多文件时逐文件处理 + 每文件后触发上下文压缩，避免累积撑满](../notes/2026-08-15-蒸馏多文件时逐文件处理-每文件后触发上下文压缩避免累积撑满.md) - lesson (lesson, 2026-08-15)
* [CodeBuddy IDE 把系统上下文注入 user 消息，采集时必须剥离系统标签块](../notes/2026-08-12-codebuddy-ide-把系统上下文注入-user-消息采集时必须剥离系统标签块.md) - lesson (lesson, 2026-08-12)
* [confirm_note/reject_note 的 output_dir 解析顺序改为 output_dir → repo_path → session](../notes/2026-08-12-confirm-notereject-note-的-output-dir-解析顺序改为-output-dir-repo.md) - decision (decision, 2026-08-12)
* [IDE hook 采用「同步采集 + 异步蒸馏」两段式执行模型](../notes/2026-08-12-ide-hook-采用同步采集-异步蒸馏两段式执行模型.md) - architecture (architecture, 2026-08-12)
* [MCP 工具无法自动探测当前项目路径，需显式传 repo_path](../notes/2026-08-12-mcp-工具无法自动探测当前项目路径需显式传-repo-path.md) - pitfall (pitfall, 2026-08-12)
* [query_wiki 的 output_dir 非必填，解析顺序为 output_dir → session → repo_path](../notes/2026-08-12-query-wiki-的-output-dir-非必填解析顺序为-output-dir-session-repo-pat.md) - architecture (architecture, 2026-08-12)
* [repowiki/raw/ 目录堆积会使同步捕获线性变慢，逼近 60s 超时](../notes/2026-08-12-repowikiraw-目录堆积会使同步捕获线性变慢逼近-60s-超时.md) - pitfall (pitfall, 2026-08-12)
* [resolve_session 恢复的 session.output_dir 会覆盖 repo_path 推断，导致 Note not found](../notes/2026-08-12-resolve-session-恢复的-sessionoutput-dir-会覆盖-repo-path-推断导致-not.md) - pitfall (pitfall, 2026-08-12)
* [TencentDB-Agent-Memory 四层记忆金字塔：逐层蒸馏 + 触发式调度](../notes/2026-08-12-tencentdb-agent-memory-四层记忆金字塔逐层蒸馏-触发式调度.md) - architecture (architecture, 2026-08-12)
* [块剥离正则不要用 ^ 行首锚点：系统块前可能有 user: 前缀](../notes/2026-08-12-块剥离正则不要用-行首锚点系统块前可能有-user-前缀.md) - pitfall (pitfall, 2026-08-12)
* [CodeBuddy index.json transcript 是裸 JSON 数组，_load_transcript 必须支持 list 顶层展开](../notes/2026-08-09-codebuddy-indexjson-transcript-是裸-json-数组-load-transcript-必须.md) - pitfall (pitfall, 2026-08-09)
* [hook 事件信封合成时须置空 source_session_id，否则 supersede 会覆盖真实 transcript（数据丢失）](../notes/2026-08-09-hook-事件信封合成时须置空-source-session-id否则-supersede-会覆盖真实-transcri.md) - pitfall (pitfall, 2026-08-09)
* [Windows 下 hook 按 sys.stdin.read() 读取中文事件会崩溃，必须按字节读 + 显式 UTF-8 解码](../notes/2026-08-09-windows-下-hook-按-sysstdinread-读取中文事件会崩溃必须按字节读-显式-utf-8-解码.md) - pitfall (pitfall, 2026-08-09)
* [同一会话的 PreCompact/Stop 不带 transcript_path，落空信封会被 duplicate 去重，应视为 no-op](../notes/2026-08-09-同一会话的-precompactstop-不带-transcript-path落空信封会被-duplicate-去重应视.md) - lesson (lesson, 2026-08-09)
* [归档对话文件名用用户首句 slug，且与 conversation_id 必须一致（蒸馏链路依赖此约束）](../notes/2026-08-09-归档对话文件名用用户首句-slug且与-conversation-id-必须一致蒸馏链路依赖此约束.md) - decision (decision, 2026-08-09)
* [无知识的 raw 对话蒸馏后也应清理，删除条件要用 produced is not None 而非 truthy](../notes/2026-08-09-无知识的-raw-对话蒸馏后也应清理删除条件要用-produced-is-not-none-而非-truthy.md) - lesson (lesson, 2026-08-09)
* [CodeBuddy IDE transcript_path 指向的 index.json 只存元数据，真实内容在 messages/<id>.json](../notes/2026-08-08-codebuddy-ide-transcript-path-指向的-indexjson-只存元数据真实内容在-messa.md) - pitfall (pitfall, 2026-08-08)
* [Entity/Concept 提取采用 WeKnora 式两阶段流程（P0：纯 prompt 协议）](../notes/2026-08-03-entityconcept-提取采用-weknora-式两阶段流程p0纯-prompt-协议.md) - decision (decision, 2026-08-03)
* [MCP 工具 schema 不声明 session_id，handler 隐式读取](../notes/2026-08-03-mcp-工具-schema-不声明-session-idhandler-隐式读取.md) - lesson (lesson, 2026-08-03)
