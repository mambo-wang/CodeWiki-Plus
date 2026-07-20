## 从 nashsu/llm_wiki 和 WeKnora 到 CodeWiki-CN：LLM Wiki 知识层的借鉴与整合

### 背景：为什么代码文档需要"知识层"

CodeWiki 解决了代码仓库文档"从零生成"的问题——通过 AST 解析、依赖图构建和 LLM 驱动，一次性产出结构化的模块文档。但文档生成只是起点，不是终点。一个真正有用的代码知识库需要持续演进：团队做出架构决策时需要记录"为什么选 A 不选 B"，踩到坑时需要归档"下次别再这样"，引入第三方 SDK 时需要把外部文档也纳入检索范围，随着代码迭代还需要知道哪些文档已经过期、哪些页面成了孤岛。

这些需求已经超出了"文档生成"的范畴，进入了**知识管理**的领域。两个开源项目在这个方向上做了有价值的探索：nashsu 的 llm_wiki 和腾讯的 WeKnora。我们在 CodeWiki-CN 的 LLM Wiki 扩展中，从这两个项目中借鉴了核心设计模式，并将它们整合进了 CodeWiki-CN 的 MCP 工具链架构。

### nashsu/llm_wiki：面向个人知识管理的 Tauri 桌面应用

nashsu/llm_wiki 是一个基于 Tauri 的桌面应用，定位是"用 LLM 驱动的个人 Wiki"。它的核心业务逻辑围绕**页面类型分类**展开：每一篇 Wiki 页面都属于一个预定义的类型——Entity（实体，如类、接口）、Concept（概念，如设计模式）、Source（外部来源文档）、Comparison（对比分析）、Synthesis（综合）、Thesis（论点）、Methodology（方法论）、Finding（发现），共 9 种。每种类型有专属的目录和结构化模板，Agent 生成文档时按类型路由到不同位置。

这种"按类型分目录"的组织方式看似简单，实际上解决了一个核心问题：当知识库规模增长后，扁平的文档列表会变成一堆无法导航的噪音。通过类型分区，Agent 可以精准地回答"项目里有哪些实体页面？"或"所有的外部文档摘要在哪？"这类结构化查询，而不需要每次都全文检索。

llm_wiki 还引入了 `purpose.md`——一个由用户和 Agent 共同维护的项目意图文档。它描述项目的核心目标、技术栈和设计哲学，在后续所有文档生成和知识提取中作为上下文注入到 LLM 提示词里，确保生成的内容与项目方向一致。此外，它的 Review 系统允许标记知识库中的质量问题（断链、孤立页面、缺失引用等），形成持续的质量反馈循环。

在存储层面，llm_wiki 使用文件系统 + LanceDB（嵌入式向量数据库），互链语法采用简洁的 `[[wikilink]]` 格式。整体设计偏向个人使用场景，没有多用户协作和复杂的去重机制，但在页面类型体系和问题追踪方面提供了清晰的设计范式。

### Tencent/WeKnora：经 40,000 文档验证的生产级实践

WeKnora 是腾讯开源的企业级知识库系统，Go 后端 + Vue 前端，v0.7.0 版本。与 llm_wiki 的个人工具定位不同，WeKnora 面向的是大规模团队协作场景，其设计经过了 40,000 篇文档的实战验证。这意味着它的每一个特性都不是"听起来不错"的理论设计，而是在真实生产环境中被压力测试过的。

WeKnora 最值得借鉴的几个设计模式：

**Aliases（别名系统）**。每个页面在 frontmatter 中维护一个别名列表。"UserService"、"用户服务"、"USvc"指向同一个页面，搜索和交叉引用时自动解析。这解决了知识库中最常见的"同义词断裂"问题——不同人对同一概念使用不同称呼，导致检索命中率下降。WeKnora 在搜索时对 aliases 字段给予额外权重提升，实测显著提高了召回率。

**Chunk-level 引用（chunk_refs）**。传统文档引用只到文档级别（"参考了 RFC 7519"），WeKnora 将引用精度提升到"块级别"——精确到源文件的行号范围。这让知识的来源完全可追溯：当你质疑某段描述是否准确时，可以直接跳转到原始文档的具体段落核实。在 40K 文档规模下，这种精确引用对防止"知识漂移"（文档内容逐渐偏离原始来源）至关重要。

**三级提取粒度（extraction_granularity）**。控制 Agent 从源码或文档中提取实体/概念的密度：`focused`（3-7 个关键项，适合快速概览）、`standard`（适度提取）、`exhaustive`（全面提取，适合深度文档化）。没有这个控制，Agent 在面对大型代码库时要么提取过少（遗漏关键实体），要么提取过多（产生大量低价值页面）。WeKnora 的实践表明，`standard` 级别在大多数项目中取得了最佳的知识密度平衡。

**统一分类规划（taxonomy planning）**。在批量提取实体/概念之前，先让 Agent 规划整体分类体系——哪些页面归入哪个目录、各类型之间的层次关系是什么。如果不做这一步，Agent 每次独立决定页面存放位置，随着页面数量增长，目录结构会变成一团混乱。WeKnora 采用"先规划后提取"的两阶段工作流，确保知识库的分类体系始终一致。

**源文件撤回（retraction）**。当导入的第三方文档过期或被替换时，需要精确移除所有源自该文档的知识。WeKnora 的做法是：标记文档为 retracted，然后扫描所有引用了该文档的页面，移除仅来源于此的内容（如果一个页面的所有知识都来自被撤回的文档，则整个页面标记为 stale）。这在引入外部 SDK 文档、API 规范等场景中非常实用——版本升级时，旧文档撤回，新文档导入，知识库自动清理。

**Issue 追踪 + Health Score**。WeKnora 维护一个结构化的问题列表（`wiki_page_issues`），每个问题有类型（断链、缺失文档、内容不一致等）、严重级别和关联页面。基于问题列表计算 0-100 的 Health Score（`100 - Σ(error×10 + warning×3 + info×1)`），作为知识库整体健康度的量化指标。这让"Wiki 需要维护了"从一个模糊的感觉变成一个可度量的信号。

**`[[slug|display]]` 互链语法**。比 llm_wiki 的 `[[wikilink]]` 更健壮——slug 是页面的唯一标识（URL-safe），display 是人类可读的显示文本。这种分离允许页面重命名（改 display）而不破坏链接（slug 不变），也允许不同页面使用相同的显示文本但指向不同的 slug。WeKnora 还定义了"禁止区间"（fenced code blocks、inline code、现有链接内部）来防止误替换。

在存储层面，WeKnora 使用 PostgreSQL + Redis，去重采用 Jaccard bigram 预过滤 + LLM 确认的两阶段策略——先用计算成本低的相似度算法筛出候选对，再用 LLM 做精确判断，避免在大规模知识库上直接调用 LLM 去重导致的成本和延迟问题。

### 整合到 CodeWiki-CN：取舍与适配

借鉴不是照搬。CodeWiki-CN 有一个根本性的架构约束：它是纯 MCP 工具服务器，不内置 LLM——所有智能推理由 AI IDE 的 Agent 完成。这意味着 llm_wiki 和 WeKnora 中"内置 LLM 调用"的部分不能直接移植，需要将它们的业务逻辑转化为 Agent 可调用的工具接口。

以下是我们在整合过程中的核心取舍：

**页面类型：9 种缩减为 6 种**。llm_wiki 的 Thesis、Methodology、Finding 类型面向学术研究场景，与代码文档的语境不匹配。WeKnora 的 7 种类型中也有一些偏企业知识管理。我们保留了与代码文档最相关的 6 种：module（模块文档，CodeWiki 原有）、entity（实体：类/接口/数据模型）、concept（概念：设计模式/业务概念）、source（外部文档摘要）、comparison（对比分析）、query（研究查询）。每种类型通过 `schema.yaml` 中的 `page_types` 路由表映射到 `wiki/` 下的子目录，Agent 写入时指定 `page_type` 参数即可自动路由。

**别名系统：直接采用**。WeKnora 的 aliases 设计非常成熟，我们在 frontmatter 中直接支持 `aliases` 列表，并在 BM25 搜索索引中对 aliases 字段给予 3× 权重提升。这个提升倍率来自 WeKnora 的实践经验——3× 足以让别名命中优先，同时不会完全压制正文匹配。

**来源引用：从 UUID 改为 Markdown 脚注语法**。WeKnora 用 UUID 标识 chunk_refs，这在数据库系统中很自然，但在纯文件系统中 UUID 对人不可读。我们改用 `[^src:name:line_range]` 的 Markdown 脚注语法——例如 `[^src:rfc-7519:L23-L45]`——既保持了精确到行号的追溯能力，又让文档在普通 Markdown 渲染器中也能阅读。

**提取粒度和分类规划：完整移植为提示词模板**。WeKnora 的三级粒度和 taxonomy planning 在我们的架构中不适合做成代码逻辑（因为没有内置 LLM），但它们的本质是提示词工程。因此我们把 `extraction_granularity` 作为 `schema.yaml` 的配置项，注入到所有 schema-constrained 提示词中；把 taxonomy planning 和 extraction scan 实现为 `get_prompt` 的两个新模板类型（`taxonomy_plan` 和 `extraction_scan`），Agent 需要规划分类时调用对应模板即可。

**源文件管理：工具化而非自动化**。WeKnora 的 retraction 是内置的自动化流程，我们将其拆分为两个独立的 MCP 工具：`ingest_source`（导入）和 `retract_source`（撤回）。撤回支持两种模式——`flag_stale`（标记过期但保留文件）和 `remove_refs`（删除文件并清理所有引用）。这样 Agent 可以根据场景选择合适的策略，而不是被锁定在一种行为上。

**Health Score 和 Issue 追踪：轻量化实现**。WeKnora 的 issue 系统基于数据库，我们的实现基于 `.meta/issues.json` 文件。每个 issue 使用 FNV-1a 哈希生成稳定 ID（基于 `type::page_path`），重复标记自动增加计数。Health Score 的计算公式直接采用 WeKnora 的方案（`100 - Σ(error×10 + warning×3 + info×1)`），并集成到 `lint_wiki` 工具中——原来 5 项检查扩展为 9 项，新增孤立页面、无出链、缺少别名、过期外部源 4 项 LLM Wiki 专项检查。

**互链语法：作为可选配置预留**。`[[slug|display]]` 语法虽然健壮，但会与现有 Markdown 链接共存时产生风格不一致。我们在 `schema.yaml` 中预留了 `wiki_link_syntax` 开关，默认为 `false`（使用标准 Markdown 链接）。当用户启用时，文档后处理会扫描正文中的标识符并替换为 wiki-link 格式，同时保护代码块和现有链接不被误替换。

**去重策略：降级为 BM25 预筛**。WeKnora 的 Jaccard + LLM 两阶段去重在 40K 文档规模下是必要的，但 CodeWiki-CN 面对的典型仓库文档量级是几十到几百篇，远不需要这么重的方案。我们用 BM25 搜索的相似度排序作为轻量替代——`query_wiki` 的搜索结果本身就是按相关性排序的，Agent 可以在写入前查询是否有高度相似的已有页面，避免重复。

### 最终的架构全貌

经过整合，CodeWiki-CN 的 LLM Wiki 知识层由以下部分组成：

结构化存储层——`wiki/` 下的 6 个类型子目录（modules/entities/concepts/sources/comparisons/queries），`raw/sources/` 存放第三方文档原文件，`.meta/` 存放 issue 追踪和源文件注册表。

MCP 工具层——在原有 12 个文档生成工具基础上，新增 `ingest_source`、`retract_source`、`batch_ingest`、`flag_issue` 4 个知识管理工具，扩展 `ingest_note`（新增 pitfall/known_issue/workaround 笔记类型）、`query_wiki`（新增 type_filter 和 include_sources）、`lint_wiki`（5 项扩展到 9 项 + health_score）。总计 16 个细粒度工具 + 2 个遗留工具。

提示词模板层——`get_prompt` 从原来的 4 个模板扩展到包含 10 个 Wiki 知识管理模板（entity_page/concept_page/source_summary/comparison_page/query_page/taxonomy_plan/extraction_scan 等），配合 schema.yaml 中的 page_types 路由表和 extraction_granularity 配置，为 Agent 提供完整的知识管理指导。

质量保障层——9 项 lint 检查 + 0-100 Health Score + issues.json 问题追踪，形成"发现问题 → 标记问题 → 度量健康度 → 修复问题"的闭环。

这套架构的核心原则是**CodeWiki-CN 始终做纯工具链**：不引入 LLM 依赖，不改变 Agent 驱动的工作模式。llm_wiki 和 WeKnora 中那些"内置 LLM"的业务逻辑，被转化为 Agent 可调用的工具和可消费的提示词模板。知识库的"智能"仍然来自 Agent 的推理能力，CodeWiki-CN 只负责存储、索引、检索和质量检查这些"脏活累活"。
