---
okf_version: "0.2"
aliases:
- 项目文档索引
- 文档索引
- 知识笔记索引
---

<!-- 自动生成于 2026-08-25T00:39:17+08:00 | Health Score: 0/100 | 本文件由系统自动维护 -->

# 项目文档索引

## 入门指引

* [Team Operating Doctrine](doctrine.md) - type: Doctrine
* [阅读指南](reading-guide.md) - > 基于 PageRank 依赖分析自动生成。排名越靠前的组件被越多模块依赖，建议优先阅读。

## 模块文档

* [AnalysisPipeline](modules/AnalysisPipeline.md) - AnalysisPipeline 是 DependencyAnalyzer 下负责**仓库分析编排**的叶子模块，位于 `codewiki/src/be/dependency_analyzer/analysis/`。它串起「克隆 → 结构扫
* [AnalyzerModels](modules/AnalyzerModels.md) - AnalyzerModels 是依赖分析子系统（`DependencyAnalyzer`）的纯数据层，定义了从单仓库静态分析到多仓库跨服务调用链匹配所需的全部 Pydantic 模型。它不包含业务逻辑，仅作为各分析阶段之间传递、聚合与持久化
* [AnalyzerUtils](modules/AnalyzerUtils.md) - `AnalyzerUtils` 是 `DependencyAnalyzer` 的叶子工具模块，集中存放依赖分析过程中跨语言、跨分析器复用的纯函数与配置表。它不持有状态，不发起网络调用，只提供：符号去外部化判定、彩色日志、URL/路由键规范化
* [CLI](modules/CLI.md) - CLI 是 CodeWiki 的顶层用户入口模块，建立在 Click 框架之上，负责把用户输入的命令转化为对后端 `LLM_Backend` 引擎的调用。它并不直接实现代码分析或文档生成逻辑，而是承担"胶水层"职责：解析命令行参数、持久化用
* [CLI_Adapter](modules/CLI_Adapter.md) - `CLI_Adapter` 是命令行入口与后端文档生成引擎之间的适配层。它唯一的核心组件 `CLIDocumentationGenerator` 包裹了后端 `[[LLM_Backend]]` 中的 `DocumentationGenera
* [CLI_Commands](modules/CLI_Commands.md) - CLI_Commands 是 CodeWiki 的命令行入口层，基于 Click 框架构建。它把用户意图转化为对底层生成管线、配置管理与 MCP 服务的调用。
* [CLI_Config](modules/CLI_Config.md) - `CLI_Config` 是 CodeWiki CLI 的「配置与作业状态」叶子模块，负责持久化用户设置、安全存储凭据、管理 Git 仓库操作、生成 GitHub Pages 静态查看器，以及定义文档生成作业的数据模型。它是连接命令行层（[
* [CLI_Utils](modules/CLI_Utils.md) - `CLI_Utils` 是 CodeWiki 命令行工具的底层实用模块集合，位于 `codewiki/cli/utils/` 目录下，为上层命令（[[CLI_Commands]]、[[CLI_Adapter]]）提供错误处理、文件系统操作、
* [DependencyAnalyzer](modules/DependencyAnalyzer.md) - DependencyAnalyzer 是 CodeWiki 后端的顶层依赖分析模块，负责将任意（多语言）代码仓库转换为可供 LLM 文档生成消费的「节点—调用关系—路由—拓扑」结构化数据。它覆盖从仓库克隆/校验、多语言 AST 调用图分析、
* [DocVisualizer](modules/DocVisualizer.md) - DocVisualizer（位于 `codewiki/src/fe/`）是 CodeWiki 的轻量级文档可视化前端叶子模块，负责将 LLM 生成的 Markdown 文档（`overview.md`、各模块的 `.
* [Frontend](modules/Frontend.md) - Frontend 是 CodeWiki 的前端呈现层，负责把 [[LLM_Backend]]（DocumentationGenerator）与 [[MCP_Server]] 生成的 Wiki 产物（Markdown 文档、`module_t
* [GraphAndSort](modules/GraphAndSort.md) - GraphAndSort 是 DependencyAnalyzer 的叶子模块，负责把多语言代码仓库解析出的代码组件（函数/类/接口/结构体）及其依赖关系，转换为可遍历的**依赖图**，再经**拓扑排序**与**叶节点提取**产出「叶优先（
* [LLM_Backend](modules/LLM_Backend.md) - `LLM_Backend` 是 CodeWiki 的文档生成后端引擎（位于 `codewiki/src/be/`），是整个工具的核心能力提供方。它把「依赖分析 → 模块聚类 → 逐模块 LLM 文档生成 → 缓存/落盘」串成可复用的能力，被
* [LanguageAnalyzers](modules/LanguageAnalyzers.md) - LanguageAnalyzers 是 DependencyAnalyzer 的叶子模块，包含针对 10 种编程语言的源码分析器。每个分析器接收一个文件路径与源码内容（外加可选的 `repo_path`），解析后产出两类标准对象：`Node
* [MCP_Cache](modules/MCP_Cache.md) - `MCP_Cache` 是 [[MCP_Server]] 的持久化与检索核心，位于 `codewiki/mcp/cache.py`。
* [MCP_Core](modules/MCP_Core.md) - MCP_Core 是 CodeWiki MCP Server（`codewiki.mcp.
* [MCP_Prompts](modules/MCP_Prompts.md) - MCP_Prompts 是 CodeWiki MCP Server 的**提示词（Prompt）叶子模块**，17 个构建器实现于 `codewiki/mcp/prompts.py`。
* [MCP_Server](modules/MCP_Server.md) - MCP_Server 是 CodeWiki 的 MCP（Model Context Protocol）协议服务端，基于 stdio 传输，把后端的代码分析、文档生成、知识库管理与 Wiki 质量校验能力以「工具（tool）」形式暴露给 ID
* [MCP_Tools_Analysis](modules/MCP_Tools_Analysis.md) - 本模块是 [[MCP_Server]] 的"分析类"工具集合，提供仓库级与多仓库工作区级的结构解析入口。核心是 `analyze_repo`（单仓分析）与 `analyze_workspace`（多仓工作区分析）两个 MCP 工具，二者均为
* [MCP_Tools_Dependency](modules/MCP_Tools_Dependency.md) - `MCP_Tools_Dependency` 是 CodeWiki 的 MCP 工具集中负责**依赖关系分析**的叶子模块，包含 18 个组件（3 个公开 handler + 15 个私有辅助函数），分布在 4 个源文件中：
* [MCP_Tools_DocWriter](modules/MCP_Tools_DocWriter.md) - `MCP_Tools_DocWriter` 是 CodeWiki 的文档写入与骨架生成层，负责把 [[MCP_Tools_Analysis]] 与 [[DependencyAnalyzer]] 产出的分析结果，转化为可落盘的 Wiki Ma
* [MCP_Tools_Knowledge](modules/MCP_Tools_Knowledge.md) - `MCP_Tools_Knowledge` 是 CodeWiki MCP 服务的知识库工具集（leaf 模块），聚焦于**离线知识沉淀与检索闭环**：从源码/AGENTS.md 生成结构化文档，录入笔记要点，并提供多模式的 Wiki 查询能
* [MCP_Tools_Quality](modules/MCP_Tools_Quality.md) - `MCP_Tools_Quality` 是 CodeWiki MCP 工具层中的质量与索引子模块，负责对生成的 Wiki 文档进行健康检查（lint）、全文检索（search）、索引重建（index）、问题标记（issue）、跨服务架构追踪
* [RouteExtractors](modules/RouteExtractors.md) - RouteExtractors 是 `DependencyAnalyzer` 的叶子模块，负责从各语言源文件中**提取路由节点（`RouteNode`）**，供跨服务（cross-service）调用分析使用。它位于 AST/调用图分析之后
* [SharedConfig](modules/SharedConfig.md) - `SharedConfig` 是 CodeWiki 横跨 CLI、后端分析与 MCP 服务的**共享配置与文件管理基座**（位于 `codewiki/src/`）。它仅由两个源文件、6 个组件构成，却是各模块协同的基石：`Config` 统
* [WebApp](modules/WebApp.md) - `Frontend/WebApp` 是 CodeWiki 的 Web 入口层，基于 FastAPI 提供图形化界面，让用户提交 GitHub 仓库 URL 即可异步生成完整文档。它由 7 个源文件、15 个组件组成，核心职责是：接收仓库提交

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

## 场景方法

* [IDE-Hook采集链路方法](scenarios/IDE-Hook采集链路方法.md) - CodeBuddy IDE hook 对话采集链路的 SOP 与禁忌：transcript 索引分片读取、同步采集异步蒸馏、双副本同步、注入可靠性
* [MCP-Server薄壳架构与参数约定](scenarios/MCP-Server薄壳架构与参数约定.md) - MCP 薄壳分层、新增工具两处落点、output_dir 解析单点收敛、工具参数先读描述纪律
* [Wiki页面生成约定与数据结构](scenarios/Wiki页面生成约定与数据结构.md) - status 语义分层、OKF actor 约定、module_tree 字符串引用、实体概念提取识别与举证分离四步流程
* [任务记忆系统设计方法](scenarios/任务记忆系统设计方法.md) - 任务归属采集阶段决定、source_session_id 维度绑定、pending 确认闸门、memories 追加式原子写
* [发布与依赖治理方法](scenarios/发布与依赖治理方法.md) - Windows 下发布/CI/依赖升级的工作方法：编码坑规避、网络栈 fallback、密钥扫描、ruff 钉版本、review 工具选型、验证纪律
* [对话蒸馏管线与raw暂存区](scenarios/对话蒸馏管线与raw暂存区.md) - 蒸馏三模式共同落盘路径、raw 暂存区生命周期、Mode C 多文件蒸馏操作纪律

## 知识笔记

* [doctrine 不会自动注入 Agent 上下文：唯一通道是 query_wiki(mode='overview')](../notes/2026-08-25-doctrine-不会自动注入-agent-上下文唯一通道是-query-wikimodeoverview.md) - architecture (architecture, 2026-08-25)
* [MCP 参数长度受限时蒸馏 submit 走文件侧通道：Python 脚本直接调 handle_distill_conversation](../notes/2026-08-25-mcp-参数长度受限时蒸馏-submit-走文件侧通道python-脚本直接调-handle-distill-conve.md) - workaround (workaround, 2026-08-25)
* [移除 doctrine 备份机制：.backup 冗余且备份文件会污染检索索引](../notes/2026-08-25-移除-doctrine-备份机制backup-冗余且备份文件会污染检索索引.md) - decision (decision, 2026-08-25)
* [聚合/doctrine 阈值等运行参数通过 repowiki/schema.yaml conventions.aggregation 覆盖，不改 py 源码默认值](../notes/2026-08-25-聚合doctrine-阈值等运行参数通过-repowikischemayaml-conventionsaggregati.md) - decision (decision, 2026-08-25)
* [蒸馏时无知识密度的对话也提交空结果，否则 raw 无法归档清理](../notes/2026-08-25-蒸馏时无知识密度的对话也提交空结果否则-raw-无法归档清理.md) - architecture (architecture, 2026-08-25)
* [Agent 表述必须诚实区分「已知事实」与「推测」，不能把假设当依据](../notes/2026-08-24-agent-表述必须诚实区分已知事实与推测不能把假设当依据.md) - lesson (lesson, 2026-08-24)
* [frontmatter deep module 重构四决策：路由收进 module、原地扩展、字节级兼容、先 reader 后 writer](../notes/2026-08-24-frontmatter-deep-module-重构四决策路由收进-module原地扩展字节级兼容先-reader-后.md) - decision (decision, 2026-08-24)
* [GitHub API 直连被阻时用 PowerShell Invoke-RestMethod 走系统网络栈，token 从 git 凭据管理器提取](../notes/2026-08-24-github-api-直连被阻时用-powershell-invoke-restmethod-走系统网络栈token-从.md) - workaround (workaround, 2026-08-24)
* [health_score 为扣分制：error-10/warning-3/info-1](../notes/2026-08-24-health-score-为扣分制error-10warning-3info-1.md) - architecture (architecture, 2026-08-24)
* [install-hooks 幂等去重在 Windows 路径分隔符下失效](../notes/2026-08-24-install-hooks-幂等去重在-windows-路径分隔符下失效.md) - pitfall (pitfall, 2026-08-24)
* [lint_wiki 支持 fix=true 自愈过期索引](../notes/2026-08-24-lint-wiki-支持-fixtrue-自愈过期索引.md) - architecture (architecture, 2026-08-24)
* [MCP prompt 与 AGENTS.md 是同一约定的两个载体：静态常驻注入 vs 按需可查询](../notes/2026-08-24-mcp-prompt-与-agentsmd-是同一约定的两个载体静态常驻注入-vs-按需可查询.md) - architecture (architecture, 2026-08-24)
* [mcp 知识飞轮决策记录：L0 对话归档零索引、Phase 5 资产置信分层与 distill-worker 随包发布](../notes/2026-08-24-mcp-知识飞轮决策记录l0-对话归档零索引phase-5-资产置信分层与-distill-worker-随包发布.md) - decision (decision, 2026-08-24)
* [OpenViking 借鉴三原则：借分层不借 LLM、借模式不借 hook、借粒度不借无闸门](../notes/2026-08-24-openviking-借鉴三原则借分层不借-llm借模式不借-hook借粒度不借无闸门.md) - decision (decision, 2026-08-24)
* [patch 已有 frontmatter 路径缺 aliases 默认键](../notes/2026-08-24-patch-已有-frontmatter-路径缺-aliases-默认键.md) - pitfall (pitfall, 2026-08-24)
* [raw 索引 .index.json 的 task_id 带字面引号导致按任务过滤漏检](../notes/2026-08-24-raw-索引-indexjson-的-task-id-带字面引号导致按任务过滤漏检.md) - pitfall (pitfall, 2026-08-24)
* [retrieval_stats.db 放 repowiki/.meta 而非 .codewiki 的四个理由](../notes/2026-08-24-retrieval-statsdb-放-repowikimeta-而非-codewiki-的四个理由.md) - architecture (architecture, 2026-08-24)
* [ruff 升级规则集变宽导致 CI 大面积红：显式 select 钉住窄默认，不顺风修宽规则](../notes/2026-08-24-ruff-升级规则集变宽导致-ci-大面积红显式-select-钉住窄默认不顺风修宽规则.md) - decision (decision, 2026-08-24)
* [smoke test 用临时 output_dir 污染真实仓库缓存导致落盘错位](../notes/2026-08-24-smoke-test-用临时-output-dir-污染真实仓库缓存导致落盘错位.md) - pitfall (pitfall, 2026-08-24)
* [TAM L0-L3 记忆管线对照：CodeWiki 已有 L0/L1，空白在 L2 场景聚合与 L3 Doctrine](../notes/2026-08-24-tam-l0-l3-记忆管线对照codewiki-已有-l0l1空白在-l2-场景聚合与-l3-doctrine.md) - architecture (architecture, 2026-08-24)
* [task_bindings 绑定文件改为一次性消费凭证：成功落盘后删除 + supersede 继承旧 task_id](../notes/2026-08-24-task-bindings-绑定文件改为一次性消费凭证成功落盘后删除-supersede-继承旧-task-id.md) - decision (decision, 2026-08-24)
* [telemetry 采用 per-user jsonl 文件：零冲突设计的承重墙](../notes/2026-08-24-telemetry-采用-per-user-jsonl-文件零冲突设计的承重墙.md) - decision (decision, 2026-08-24)
* [Windows GBK 控制台编码导致 CLI 输出与 twine 发布崩溃](../notes/2026-08-24-windows-gbk-控制台编码导致-cli-输出与-twine-发布崩溃.md) - pitfall (pitfall, 2026-08-24)
* [修复顺序类 bug 先看数据流时序：fix 块后置导致 broken_links 基于旧索引计算](../notes/2026-08-24-修复顺序类-bug-先看数据流时序fix-块后置导致-broken-links-基于旧索引计算.md) - lesson (lesson, 2026-08-24)
* [单次 commit 业务 review 工具选型：mattpocock code-review 走 Spec 轴，需求来源可绕 setup](../notes/2026-08-24-单次-commit-业务-review-工具选型mattpocock-code-review-走-spec-轴需求来源可.md) - decision (decision, 2026-08-24)
* [多 IDE hook 支持按家族归并：31 个智能体收敛为 3 家族 schema](../notes/2026-08-24-多-ide-hook-支持按家族归并31-个智能体收敛为-3-家族-schema.md) - architecture (architecture, 2026-08-24)
* [子代理报告「全绿」不可信：lastfailed 缓存空 ≠ 真全绿，须自己实跑验证](../notes/2026-08-24-子代理报告全绿不可信lastfailed-缓存空-真全绿须自己实跑验证.md) - lesson (lesson, 2026-08-24)
* [孤儿分支不是「部分文件单独分支」，.codewiki 二进制缓存救不了冲突](../notes/2026-08-24-孤儿分支不是部分文件单独分支codewiki-二进制缓存救不了冲突.md) - lesson (lesson, 2026-08-24)
* [对话归档原样保留用户消息密钥导致 push 被 GitHub 密钥扫描拦截](../notes/2026-08-24-对话归档原样保留用户消息密钥导致-push-被-github-密钥扫描拦截.md) - pitfall (pitfall, 2026-08-24)
* [测试多 helper 各写一次 jsonl 会互相全量覆盖，须 append-merge 且不依赖固定 user 文件名](../notes/2026-08-24-测试多-helper-各写一次-jsonl-会互相全量覆盖须-append-merge-且不依赖固定-user-文件名.md) - pitfall (pitfall, 2026-08-24)
* [配置合并的 Python 坑：dict 浅拷贝污染原配置 + hooks.get(event, []) 未写回](../notes/2026-08-24-配置合并的-python-坑dict-浅拷贝污染原配置-hooksgetevent-未写回.md) - pitfall (pitfall, 2026-08-24)
* [distill-worker subagent 定义随包发布，hook 启用时自动拷贝到项目 .codebuddy/agents/](../notes/2026-08-23-distill-worker-subagent-定义随包发布hook-启用时自动拷贝到项目-codebuddyagent.md) - decision (decision, 2026-08-23)
* [hook 采集机制仅正式接线 CodeBuddy，README 措辞用「仅接线支持」](../notes/2026-08-23-hook-采集机制仅正式接线-codebuddyreadme-措辞用仅接线支持.md) - architecture (architecture, 2026-08-23)
* [会话启动时的 query_wiki/蒸馏等重操作委托 subagent 执行，避免阻塞用户正常使用](../notes/2026-08-23-会话启动时的-query-wiki蒸馏等重操作委托-subagent-执行避免阻塞用户正常使用.md) - decision (decision, 2026-08-23)
* [多 IDE hook 自动检测接线：IDE 注册表驱动 + codewiki install-hooks](../notes/2026-08-23-多-ide-hook-自动检测接线ide-注册表驱动-codewiki-install-hooks.md) - decision (decision, 2026-08-23)
* [下一期方向：资产置信分层与负反馈闭环（Roadmap Phase 5）](../notes/2026-08-21-下一期方向资产置信分层与负反馈闭环roadmap-phase-5.md) - decision (decision, 2026-08-21)
* [L0 对话归档采用链接优先、零索引设计](../notes/2026-08-19-l0-对话归档采用链接优先零索引设计.md) - decision (decision, 2026-08-19)
* [技术文章面向业务读者时应削减实现细节、增补业务梳理与开发思路](../notes/2026-08-16-技术文章面向业务读者时应削减实现细节增补业务梳理与开发思路.md) - lesson (lesson, 2026-08-16)
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
