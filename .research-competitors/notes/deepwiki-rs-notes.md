# deepwiki-rs（Litho）竞品调研笔记

> 仓库：sopaco/deepwiki-rs（本地克隆于 `.research-competitors/deepwiki-rs`），Rust，v1.5.1（`Cargo.toml:3`），MIT。所有论断均基于源码核对。

## 1. 整体架构与定位

- **形态：纯 CLI 工具，非 MCP、非服务**。入口 `src/main.rs:16-27`：`clap` 解析参数 → `generator::workflow::launch(config)`，唯一子命令是 `sync-knowledge`（`src/main.rs:31-37`）。自称 "AI-powered documentation generation engine"，产出 **C4 模型**架构文档（Context/Container/Component）。
- **"Litho" 是 deepwiki-rs 的产品名重命名**（README.md:5）。"litho-engine" 指其内置四阶段文档生成引擎（即 `workflow.rs` 的 launch 流水线），配置文件为 `litho.toml`，内部工作目录 `.litho`（`src/cli.rs:174`）。
- **重要信号：项目已宣布演进为 Terrain**（README.md:31-40），Litho 定位收缩为 "fast, focused C4 doc generator"，开发重心已转移。

## 2. 代码分析阶段（Preprocess）

- 驱动入口 `src/generator/preprocess/mod.rs:45-127`：① 提取原始文档（README 等）→ ② `StructureExtractor` 扫描目录结构（`structure_extractor.rs:45-100`，walkdir 递归 + git tracked-only 过滤 + 文件重要性打分 + LLM 目录打分加成）→ ③ **逐目录 LLM 总结生成 DirectoryDossier**（`mod.rs:135-212`，>256KB 按字典序分批，`mod.rs:133`）→ ④ 依赖关系分析。
- **解析层是正则/关键词匹配，非 AST**：12 个语言处理器（rust/js/ts/php/react/vue/svelte/kotlin/python/java/csharp/swift，`extractors/language_processors/mod.rs:44-57`），复杂度计算用 `content.matches("fn ")` 等字符串计数（`mod.rs:112-143`）。**没有 Go 处理器**（README.md:102 宣称支持 Go，代码不符）。
- **Agentic 阶段划分**：四阶段 = Preprocess → Research → Compose → Output（`workflow.rs:83-133`）。Research 按 C4 层级组织 7 个 agent：C1 SystemContextResearcher → C2 DomainModulesDetector/ArchitectureResearcher/WorkflowResearcher → C3-C4 KeyModulesInsight → BoundaryAnalyzer → DatabaseOverviewAnalyzer（条件触发）（`research/orchestrator.rs:22-54`）。
- **工作流引擎核心是 `StepForwardAgent` trait**（`step_forward_agent.rs:581-726`）：每个 agent 声明式配置 `AgentDataConfig`（required/optional `DataSource`：Memory 键、上游 agent 结果、外部知识类别）+ `PromptTemplate` + `LLMCallMode`（Extract 结构化抽取 / Prompt / PromptWithTools），默认 `execute()` 自动完成数据可用性校验（`step_forward_agent.rs:624-641`）、标准 prompt 组装、LLM 调用、结果写回 Memory。新 agent 只需实现配置钩子，是典型的声明式流水线框架。

## 3. 文档生成流程

- Compose 阶段 6 个 editor 顺序执行（Overview/Architecture/Workflow/KeyModulesInsight/Boundary/Database，`compose/mod.rs:24-52`），产出写入固定 DocTree（`outlet/mod.rs:25-47`），`DiskOutlet` **删除整个输出目录后全量重写**（`outlet/mod.rs:79-82`），最后 `SummaryOutlet` 生成详/简双版执行报告（`summary_outlet.rs:21-23`）。
- **Prompt 策略**（`step_forward_agent.rs:416-577`）：标准 user prompt = 开场指令 + 时间占位符 + 数据源格式化输出（项目结构树/代码洞察 top-25/依赖关系/README 截断 16KB）+ 收尾强调指令；目标语言指令追加到 system/user 双端（`step_forward_agent.rs:664-665`），支持 8 种语言（`cli.rs:86`）。超过 64K token 触发 LLM 智能压缩至 50%，保留函数签名/类型定义等 pattern，压缩失败降级为应急截断（`utils/prompt_compressor.rs:44-58`、`step_forward_agent.rs:314-349`），压缩结果本身有缓存（`cache/mod.rs:183-197`）。
- **并发策略（Rust 优势实际用得很节制）**：`do_parallel_with_limit`（`utils/threads.rs:6-27`，tokio Semaphore 限流 join_all）**仅用于两处**——KeyModulesInsight 按领域模块并行分析（`research/agents/key_modules_insight.rs:110-126`）和 Deep Dive 文档并行生成（`compose/agents/key_modules_insight_editor.rs:49-50`）。research/compose 各 agent 之间、目录总结（`preprocess/mod.rs:146` for 循环）均为**串行**。README.md:417 序列图宣称 "Execute multiple research agents in parallel"，与代码不符。整体是 IO 密集（LLM 调用），Rust 并发优势主要体现在 tokio 异步与低开销 CLI 分发。

## 4. 检索/问答能力

**无问答、无 RAG、无任何检索接口**。`src/` 中没有 query/search/embedding 模块；产物是一次性生成的静态 markdown。README.md:141-149 提到的 AI 问答在**外部姊妹项目 Litho Book**（Rust+Axum markdown 阅读器）中，不在本仓库。

## 5. MCP / Agent 集成

- **无 MCP server**。面向 AI Agent 的输出走三条路：
  1. `.agents/skills/litho-documents-skill/`（SKILL.md:7-9）：Litho 四阶段流水线的**纯 Agent 平行实现**——不依赖二进制，用 agent 工具调用复刻同一流程，含 `.litho-agent/` 中间产物持久化策略对抗上下文遗忘（SKILL.md:110-142），按项目规模分档扫描策略（SKILL.md:40-47）。已上 Smithery 分发（README.md:194）。
  2. `.agents/skills/ai-context-generator/` + `.ai-context/`：生成**分层 AI 知识库**（Tier0 PROJECT-ESSENCE → Tier3 DYNAMICS，按稳定性分层，`.ai-context/SKILL.md:33-42`），供 coding agent 会话启动时消费，与 AGENTS.md 互补（"AGENTS.md 讲怎么干活，.ai-context 讲项目是什么"）。
  3. 生成的 `docs/`（en/zh/zh_se 三语）本身面向人+Agent 阅读。

## 6. 值得注意的工程设计

- **双模型 + fallover**：efficient/powerful 双模型（`cli.rs:50-56`），主模型失败时把错误信息注入 prompt 换 fallback 模型重试（`llm/client/mod.rs:106-118`）+ 指数退避重试（`mod.rs:47-73`）。
- **LLM 层基于 rig-core 0.35**（`Cargo.toml:12`），8 个 provider（openai/moonshot/deepseek/mistral/openrouter/anthropic/gemini/ollama，`config.rs:38-47`）。
- **ReAct + summary reasoning 降级**：带工具 agent 达到最大迭代后，用无工具 agent 对 chat_history 做总结推理兜底（`llm/client/mod.rs:154-184`）；工具并发默认 4、max_turns 100（`config.rs:187-193`）。
- **文件级 prompt 缓存**：MD5(prompt) 为 key、按 category 目录存放 JSON、带 token 用量统计与过期时间（`cache/mod.rs:43-67,127-180`），并有缓存命中率性能监控（`cache/performance_monitor.rs`）——省 token 复跑利器。
- **进程内 Memory**：`HashMap<"scope:key", serde_json::Value>` 带访问计数/大小统计（`memory/mod.rs:31-84`），作用域隔离（PREPROCESS/STUDIES_RESEARCH/DOCUMENTATION 等）。
- **安全细节**：ReAct 的 file_explorer 工具做了路径逃逸防护（拒绝绝对路径与 `..` 穿越，`llm/tools/file_explorer.rs:48-71`）；LLM 输出全部走宽松反序列化（`preprocess/agents/directory_summary.rs:105-152`）。
- **外部知识集成**：PDF/MD/SQL/YAML 按语义分块（8000 字符/200 重叠，`integrations/local_docs.rs:65-88`），按 category 定向投递给指定 agent（`step_forward_agent.rs:540-555`）。

## 7. 明显短板/局限

1. **无增量**：每次运行全量重新生成并删除重写输出目录（`outlet/mod.rs:79-82`）；缓存只省 LLM 调用，不省流程。
2. **串行瓶颈**：阶段间与多数 agent 间串行，大仓库目录总结逐个 for 循环（`preprocess/mod.rs:146`），性能上限受 LLM 延迟串行叠加制约。
3. **解析精度低**：无 tree-sitter/AST，正则计数定复杂度、依赖提取靠 import 语句匹配；无 Go/C/C++ 处理器。
4. **无检索/问答/服务化**：纯一次性生成器，不能作为知识库被持续查询；无 MCP、HTTP API、watch 模式。
5. **强外部依赖**：启动即校验 `mermaid-fixer` 二进制，未安装直接 bail（`workflow.rs:51-53`）——流程性依赖外部 crate 工具。
6. **死旗标**：`--skip-preprocessing/--skip-research/--skip-documentation` 仅在 `cli.rs:36-44` 声明，全代码库无消费点，README.md:495 宣称可跳过阶段与实现不符。
7. **缓存不校验模型**：`CacheEntry` 存了 `model_name` 但 `get()` 不比对（`cache/mod.rs:88-109`），换模型后可能命中旧模型答案。
8. **项目生命周期**：主理人已转向 Terrain（README.md:31-40），本仓库大概率进入维护模式。

## 对比报告可用的一句话画像

Litho 是"声明式 StepForwardAgent 流水线 + 进程内 Memory + prompt 哈希文件缓存"的 Rust CLI 生成器，工程亮点在 prompt 组装/压缩、双模型 fallover 和 agent skill 生态（纯 Agent 平行实现 + 分层 .ai-context），但无检索问答、无增量、无 MCP，且核心维护已转向后继项目 Terrain。
