# OpenDeepWiki 调研笔记（AIDotNet/OpenDeepWiki）

调研对象：本地克隆 `D:\repos\CodeWiki-CN\.research-competitors\OpenDeepWiki`。所有论断均核对源码，标注 `文件:行号`（相对于 `src/` 根，均实际读取验证）。README 用于交叉参考，未作为事实来源。

## 1. 整体架构与定位

定位为**多仓库托管的 SaaS 式代码知识库平台**（自部署版 DeepWiki）：后台导入 Git/ZIP/本地目录 → AI 生成 wiki → Next.js 公共站点 `/{owner}/{repo}` 阅读并提供聊天、嵌入对话、MCP 服务。

- 后端：ASP.NET Core（.NET 10）单体应用，`src/OpenDeepWiki/Program.cs` 为唯一入口；自研轻量 API 框架 MiniApis（`Program.cs:73` `AddMiniApis`）+ Endpoints 模式（`src/OpenDeepWiki/Endpoints/`，含 Admin/Auth/Organization/Embed 等 17 组）。
- 数据库：EF Core，SQLite / PostgreSQL 双提供程序（`src/EFCore/OpenDeepWiki.Sqlite`、`src/EFCore/OpenDeepWiki.Postgresql`），`Program.cs:76` `AddDatabase` 按配置切换。
- 前端：Next.js 16 + React 19 App Router（`web/package.json:44,48`），含 admin 后台、i18n、分享页。
- 多仓库模型：`Repository`（OrgName/RepoName）→ `RepositoryBranch`（每分支独立 wiki）→ `BranchLanguage`（每语言一套目录+文档），实体在 `src/OpenDeepWiki.Entities/Repositories/`。组织/部门/角色做权限隔离（`Services/Organizations/OrganizationService.cs:9`、`Program.cs:234` AdminDepartmentService），属"企业多租户"雏形而非硬隔离租户。
- 认证：JWT + 角色（`Program.cs:99-118`，AdminOnly 策略:117）、Google OAuth、API Key、MCP 专用 OAuth（`Program.cs:130-136`）。
- 额外有 IM 接入层：飞书/QQ/微信/Slack webhook（`src/OpenDeepWiki/Chat/Providers/`）。

## 2. 代码分析阶段

- 克隆/更新用 **LibGit2Sharp**（`Services/Repositories/RepositoryAnalyzer.cs:4` 引用，`:200-212` clone/pull 分支），工作区固定布局 `{data}/{org}/{repo}/branches/{branch}/tree`（`:352-360`）。ZIP 导入解压（`PrepareArchiveWorkspaceAsync` `:362-381`），本地目录导入有白名单根（`Program.cs:499-501` LOCAL_IMPORT_ROOT）。
- **无语言特定解析器**（无 tree-sitter/AST/LSP）。对代码的"理解"完全下放给 LLM agent + 通用工具：`Agents/Tools/GitTool.cs:770-781` 只提供 ReadFile/ListFiles/Grep 三个函数。所谓"多语言代码分析"实为 (a) LLM 泛化能力 + (b) **输出文档多语言**（BranchLanguage 每语言独立生成/翻译）。
- 目录树采集有自适应预算：`RepositoryScanPlan.cs:5-19`（`ResolvedRepositoryScanPlan` 按仓库规模动态决定树深度/节点上限）。
- 任务队列：**DB 轮询的 BackgroundService**，非消息队列。`RepositoryProcessingWorker.cs:18-51` 每 30s 扫 Pending/Processing 状态的 Repository（`:85-94`），同类 worker 还有 Branch/Translation/MindMap/Graphify（`Program.cs:254-258`）。

## 3. 文档生成流程

Pipeline（`WikiGenerator.cs`，2884 行核心类）：**PrepareWorkspace → GenerateCatalogAsync → GenerateDocumentsAsync（并行）→ TranslateWikiAsync → GenerateMindMapAsync → SkillMarkdown**。

- 目录生成：`GenerateCatalogAsync`（`WikiGenerator.cs:245`）预采集目录树(TOON)/README/入口点拼进 user message（`:263,293-319`），agent 用 `CatalogTool.WriteCatalog` 写出 JSON 目录（title/path/order/children）。源码探索工具有**调用预算**（`DocumentSourceToolBudget`，`WikiGenerator.cs:276`、`Agents/Tools/DocumentSourceToolBudget.cs:9-16`，超限返回 BUDGET_REACHED 迫使 agent 立即产出）。
- 单篇文档：`GenerateDocumentsAsync`（`:366`）只给 leaf 节点生成正文；`Parallel.ForEachAsync` 控并发（`:561-568`），每篇独立硬超时（`:466-468`）；单篇失败不中断（部分失败容忍 `:605-608`）；已落盘的 path 跳过实现断点续跑（`:414-420`）。首篇先串行"预热 prompt cache"再开并行（`:545-559`）。
- Prompt 策略：提示词是外置资产 `src/OpenDeepWiki/prompts/{catalog,content,mindmap}-generator.md + incremental-updater.md`，由 `FilePromptPlugin` 加载（`Program.cs:199-211`），系统 prompt 跨仓库固定、运行时上下文进 user message（catalog-generator.md `<context>` 段）。content prompt 硬编码极详细的反幻觉约束（代码块必须带源文件 blockquote 链接）和 Mermaid 语法规则（`WikiGenerator.cs:818-899` + content-generator.md constraints 段）。
- 多语言：`TranslateWikiAsync`（`WikiGenerator.cs:1757`）创建目标 BranchLanguage 后**翻译已有目录与文档**（LLM 翻译，非从源码重新生成）；`TranslationWorker.cs:17` 定时扫描 Completed 仓库按配置语言自动建翻译任务。
- 增量更新：`IncrementalUpdateWorker.cs:13` 轮询手动任务 + 定时扫描（`CheckScheduledUpdatesAsync` 约 `:318-350`，按仓库级 `UpdateIntervalMinutes` 到期检查远程 HEAD commit，差异则建任务）；changed files 由 `RepositoryAnalyzer.GetChangedFilesAsync`（`:297`）从 git diff 得出；增量 prompt 明确禁用 WriteCatalog 防止整树重写（`WikiGenerator.cs:704-707`），agent 用 EditDoc/WriteDoc 精准修改。

## 4. 检索/问答能力

- **没有向量 RAG**（全库无 embedding/向量代码）。网页聊天 `ChatAssistantService.StreamChatAsync`（`Services/Chat/ChatAssistantService.cs:186,440+`）是 agentic 方案：给 LLM 挂三类工具——GitTool（直接 checkout 到对应分支读源码，`:477-480`）、ChatDocReaderTool（**把整棵 wiki 目录塞进工具描述**，agent 按行区间读文档，`:496-503`）、管理员配置的外部 MCP/Skill 工具（`:506-519`）。SSE 流式输出含 tool_call/tool_result 事件（`:141-149`）。
- 对话历史由前端每次全量携带（`ChatRequest.Messages` `:130-136`），服务端不维护会话状态；仅 `ChatLogService` 记审计日志。
- IM 消息链路有真正的异步基础设施：DB 消息队列 + 死信处理（`Chat/Queue/DatabaseMessageQueue.cs`、`Chat/Processing/ChatMessageProcessingWorker.cs`、`DeadLetterProcessor.cs`）。

## 5. MCP / Agent 集成

- 用官方 Model Context Protocol C# SDK 内嵌 MCP server，HTTP transport，两级端点：全局 `/api/mcp` 与仓库级 `/api/mcp/{owner}/{repo}`（`Program.cs:313-353` 注册、`:385-386` 映射，scope 从 URL 解析注入 `:316-347`）。
- 全局工具 4 个：ListRepositories / RouteQuestion（跨仓库路由）/ SearchDocs / ReadDoc（`MCP/McpGlobalTools.cs:26,127,163,262`）；仓库级 3 个：搜索文档 / 目录结构 / 读源文件（`MCP/McpRepositoryTools.cs:25,164,216`）。路由与检索是 **token 关键词评分**（`McpGlobalTools.cs:146,456-464` ScoreRepository/ScoreDocument），非语义检索。
- MCP 认证支持 API Key（`MCP/ApiKeyAuthenticationHandler.cs:12`）与完整 OAuth 2.1（`McpOAuthServer.cs` + `Program.cs:388-392` Protected Resource Metadata），且有用量统计中间件与聚合服务（`Program.cs:383,307`）。
- **没有 AGENTS.md 自动生成**（全源码无该字样）。最接近的是 Skill 包：`RepositorySkillMarkdownBuilder.cs:16-100` 生成 SKILL.md（frontmatter+文档索引）并把全部文档打包 zip 供 Claude Code 等技能系统下载。

## 6. 值得注意的工程设计

- **集群级生成并发控制**：`WikiGenerationCoordinator`（`WikiGenerationConcurrencyService.cs:37-64`）用 DB 租约表（RepositoryGenerationLock）+ 全局槽位（WikiGenerationSlot）+ 心跳（`WikiGenerationHeartbeat`，`RepositoryProcessingWorker.cs:170-175`）+ 崩溃恢复 `RecoverStaleWorkAsync`（`:82`），实现多实例部署下"每仓库单写者、集群总并发上限"。这是单体应用内做的分布式调度，成本低于引入 MQ。
- 5 个独立后台 Worker 职责分离（生成/分支/翻译/思维导图/Graphify 图谱产物，`Program.cs:254-258`），全量重生成有清理器（RepositoryFullRegenerationCleaner）。
- AI 配置完全管理后台化：Provider 预设目录 + DB 系统设置覆盖启动配置（`Program.cs:418-421`），模型可按"目录模型/内容模型"分角色绑定（`WikiGenerator.cs` ResolveCatalogModelAsync/ResolveContentModelAsync）。
- 缓存有独立抽象框架（`framework/OpenDeepWiki.Cache.*`，默认内存实现，`Program.cs:218`）。
- 部署：Docker Compose（compose.yaml，SQLite 默认/PG 可选）、Makefile、Sealos 脚本；.env 多路径加载（`Program.cs:439-490`）。

## 7. 明显短板/局限

1. **检索无语义层**：无 embedding/向量库，聊天靠"目录注入 + agent 翻文档"，跨仓库搜索靠关键词打分，大 wiki 下召回质量受限。
2. **任务队列是 30s DB 轮询**：时效性与吞吐有限，Worker 与 Web 同进程，扩容粒度粗。
3. **token 成本高**：每篇文档独立 agentic 调用（带完整系统 prompt + 工具往返），多语言靠逐篇翻译而非复用分析结果。
4. **无代码级精确解析**：无 AST，代码事实正确性完全依赖 LLM，重构后的行号引用易漂移。
5. 安全默认值偏弱：JWT 密钥有硬编码 fallback（`Program.cs:96`）、CORS 全放开 AllowAll（`Program.cs:146-153`）。
6. 会话不服务端持久化（前端带全量历史），长对话成本递增。

**对 CodeWiki 对比报告的要点**：OpenDeepWiki 的差异化在于"托管平台化"（多仓库/多分支/多语言/组织权限/Admin 后台/MCP 商业化接口）与集群租约式并发调度；弱项是无 RAG、无精确代码分析、成本控制粗放。
