# OpenViking 调研与借鉴分析

> 调研日期：2026-08-21
> 调研对象：
> - **volcengine/OpenViking**（`github.com/volcengine/OpenViking`，0.3.x，setuptools-scm 动态版本）：火山引擎开源的「AI Agent 上下文数据库」，AGPLv3（crates/ov_cli 为 Apache 2.0）。把 memories / resources / skills 统一存入 `viking://` 虚拟文件系统，写入时分层生成 L0/L1 摘要，检索走目录递归 + 向量混合。有 VLDB 2026 论文（VikingMem）背书与火山引擎 SaaS/私有化商业版。
> - **CodeWiki-CN / CodeWiki-Plus**（本仓库，v5.3.0）：Python MCP 服务器，AI IDE 驱动的代码文档生成 + 知识管理引擎。
>
> 资料来源：OpenViking 仓库完整浅克隆（3942 个文件；核心 Python 包 `openviking/` + `openviking_cli/` 约 2.9 万行，另有 Rust ragfs crates、C++ 向量引擎、TS SDK；tests/ 626 个测试文件，约 25 个 GitHub workflows）。README / docs/design 全部 20 篇设计文档 / 关键源码（storage、retrieve、session、parse、integrations）逐模块阅读；CodeWiki 侧基于本仓库源码与既有设计文档。所有实现细节均落到源码文件名，不含猜测。

---

## 一、执行摘要（TL;DR）

| 维度 | CodeWiki-CN | OpenViking |
|------|-------------|-----------|
| 一句话定位 | 单仓**代码**知识引擎：AST 级代码理解 + 人读 Wiki + 知识飞轮 | 通用 Agent **上下文数据库**：记忆/资源/技能的运行时存储与检索 |
| 服务对象 | 编码 Agent（IDE 内 MCP 工具消费） | 任意 LLM Agent（15+ 客户端集成，横跨多项目/多会话/多用户） |
| 交付形态 | MCP Server（40+ 工具）+ CLI | Server + `ov` CLI + MCP（streamable HTTP）+ hooks/plugins + SaaS |
| 知识结构 | `repowiki/` 人读文档 + notes，OKF v0.2 frontmatter | `viking://` 虚拟文件系统，L0/L1 sidecar 也是**OKF frontmatter**（RFC 明确升级） |
| 分层加载 | 渐进式阅读（reading_guide，按需展开） | **L0（~100 token 摘要）/ L1（~2k token 概览）/ L2（原文）三层写时生成**，目录级 sidecar |
| 检索 | BM25 + jieba + wikilink 多跳 + authority 权重（**零 embedding、零 LLM 依赖**） | dense + sparse 混合 + **目录递归下钻**（alpha 加权父分传播），trajectory 全程可观测 |
| 代码理解 | tree-sitter 依赖图/调用图/影响分析，10 语言，模块级文档 | Aider RepoMap 式 tree-sitter tags 骨架（`parse/parsers/code/ast/aider_repomap.py`），仅做识别符排名，无依赖图 |
| 新鲜度 | `stale_after` 类型感知窗口（45–365 天）+ lint 复核 | `freshness_policy`（NOOP/MARK_PENDING/REFRESH_NOW）+ 父目录新鲜度冒泡（L0 未变即停止传播） |
| 使用信号 | `adoption_events`（referenced-docs 声明注释）+ `retrieval_stats.db` 热度 | usage-reporter sink + 检索 Prometheus 指标 + 用量审计（SQLite） |
| 会话→记忆 | capture → distill（Mode A/B/C）→ **confirm 闸门** → note；task memory 分轨 | 会话两阶段 commit → **ReAct 式提取循环** → 12 类记忆 schema → 字段级 `merge_op` 合并直接落盘（**无人工闸门**） |
| 质量治理 | 18 项 lint + health score + OKF 合规 + draft→confirm | 提取质量靠 prompt + merge 策略 + dedup 签名；无等价的 lint 体系 |
| 遥测 | 本机 `retrieval_stats.db`（gitignore，单机） | span 全链路打点 + Prometheus + usage audit + web-studio 轨迹可视化 |
| 工程规模 | 个人项目，266 测试，PyPI 发布 | 公司级投入：Python 2.9 万行 + Rust + C++（自研嵌入式向量库）+ 626 测试文件 + 多语言 SDK |
| 许可证 | MIT（可自由借鉴/集成） | **AGPLv3**（只可借鉴思想，不可抄代码） |

**核心结论：**

1. **两者是互补关系，但重叠区正在快速扩大。** OpenViking 解决"Agent 运行时缺上下文"（跨项目、跨会话的记忆/资源/技能库），CodeWiki 解决"Agent 读不懂这个仓库"（AST 级代码文档 + 领域知识）。OpenViking 对代码仓的理解深度只有 RepoMap 骨架级，远不及 CodeWiki 的依赖图/调用图/影响分析；反过来，CodeWiki 没有运行时记忆层。但双方都在向对方的地盘走：OpenViking 加了 OKF frontmatter、freshness、usage 信号、code 仓 ingest；CodeWiki 加了 capture/distill、采纳信号、新鲜度、任务记忆。

2. **最值得注意的发现：六个核心机制独立收敛。** OKF frontmatter（OpenViking 有专门 RFC 升级 L0/L1 sidecar 为 OKF 格式）、类型感知新鲜度窗口（双方都是"何时该重新摘要/复核"的 pragmatic 方案）、采纳/使用信号驱动生命周期（adoption_events vs usage-reporter）、检索轨迹可观测（P0-T 线 vs retrieval trajectory）、会话→知识蒸馏（distill_conversation vs session memory extraction）、渐进式加载（渐进阅读 vs L0/L1/L2）。CodeWiki P0/P1 选的方向被一个 VLDB 论文级、公司级投入的项目独立验证了——这不是巧合，是这类系统的共性需求。

3. **OpenViking 的真正护城河是"写时分层 + 混合检索"，CodeWiki 的护城河是"AST 理解 + 评审闸门"。** 前者用 LLM 在写入时把成本花在摘要生成上（自底向上 DAG 聚合，L0 未变不冒泡），换来检索时极低的 token 开销（LoCoMo 基准 input token 降 34%–91%）；后者把成本花在代码结构化理解与人工确认上，换来知识的可信度。OpenViking 的记忆提取**直接 upsert 无闸门**，靠 merge_op 字段级合并与 dedup 兜底——这与 CodeWiki 的 draft→confirm 哲学是两种流派，各有代价（前者规模化好但噪声风险高，后者可信但依赖人）。

4. **对 CodeWiki 最直接的借鉴不是检索（那是架构级决策），而是三个低成本高回报的机制**：目录级 L0 摘要 sidecar（渐进式阅读的"预展开层"）、字段级 merge_op（note 整合从整条覆盖升级为字段策略）、超预算降级为"URI+score"的注入模式（AGENTS.md 上下文注入的预算控制）。详见第五节。

---

## 二、OpenViking 项目概览

### 2.1 定位与背景

OpenViking 自称"The Context Database for AI Agents"。核心主张：Agent 的上下文（记忆、资源、技能）不应存进黑盒向量库，而应是一个 Agent 可以用 `ls` / `tree` / `find` / `grep` 直接浏览的虚拟文件系统（`viking://` 协议）。每个条目写入时被处理成三层：

- **L0（abstract）**：一句话摘要，约 100 token，用于快速相关性判断（也是向量检索单元）；
- **L1（overview）**：约 2k token 的结构与要点，用于规划与 rerank；
- **L2（details）**：原始全文，按需加载。

关键设计：**目录本身也带 L0/L1 sidecar**（`.abstract.md` / `.overview.md`），所以相关性判断可以在不读任何文件全文的情况下逐层进行。这本质上是把"文件系统树"当成天然的层级索引结构，而不是把所有内容拍平进向量库。

学术背书：VikingMem 论文（arXiv:2605.29640，VLDB 2026）。README 公布的基准：LoCoMo 长对话记忆上，OpenClaw 24.20%→82.08%、Hermes 33.38%→82.86%、Claude Code 57.21%→80.32%，同时 input token 降 34.3%–91.0%、查询延迟降 58.45%–66.10%；tau2-bench 上经验记忆使任务成功率 +6.87pp（retail）/ +11.87pp（airline）。

### 2.2 工程形态

- **核心包**：`openviking/`（server、storage、retrieve、ingest、session、parse、prompts、telemetry、web_studio 等 30+ 子模块）+ `openviking_cli/`（`ov` 客户端、`openviking-server` 引导、setup wizard、doctor）。
- **Rust crates/**：`ragfs`（RAG 文件系统本体）+ 三个 cache 后端（mooncake / redis / yuanrong，yuanrong 含 sys 绑定）+ `ov_cli`（Apache 2.0 许可的 CLI）+ `ragfs-python`（绑定）。
- **C++ 引擎**：`src/index`、`src/store`，abi3 绑定给 Python，是自研嵌入式向量库的底层。
- **周边**：`web-studio/`（浏览器控制台）、`agent-plugins/`（Agent Plugins 1.0 规范插件）、`integrations/`、`sdk/`（TS）、`benchmark/`（LoCoMo/tau2 复现脚本）。
- **文档体系**：`docs/design/` 20 篇设计文档（RFC + 设计草案 + implementation plan 分离），质量相当高，且大量记录"首版不做什么"。

---

## 三、关键机制详解

### 3.1 存储与索引：自研嵌入式向量库

`openviking/storage/vectordb/`（VikingVectorIndex）是自研嵌入式向量库，核心引擎在 C++（`src/index/`、`src/store/`），采用 **C/D/T 三表模型**：Candidate 表存向量+标量、Delta 表记变更日志、TTL 表管过期；支持 Volatile/Persistent 双模式与多版本快照恢复。云端可通过 `vectordb_adapters/` 接 Volcengine VikingDB 或任意 HTTP 向量服务。

Embedding 默认**本地**跑 `bge-small-zh-v1.5-f16`（另有 llama-cpp 本地方案，见 `docs/design/local-embedding-llama-cpp-design.md`），同时支持 openai/volcengine/jina/ollama 等 12 种 provider。检索是 dense + sparse 混合。

**与 CodeWiki 的根本差异**：CodeWiki 检索是纯 BM25 + jieba + wikilink 多跳，零 embedding 依赖（离线可用、无模型成本），这是刻意的设计取舍。OpenViking 则认为混合检索是刚需，为此维护了 C++ 引擎 + 本地模型两条路。

### 3.2 语义分层管线：写时成本，读时收益

核心在 `openviking/storage/queuefs/`：

1. 写入进 EmbeddingQueue / SemanticQueue；
2. `semantic_processor.py` + `semantic_dag.py` **自底向上**沿目录 DAG 用 LLM 生成目录级 `.abstract.md`（L0）与 `.overview.md`（L1）——先子目录，后父目录聚合；
3. `abstract_overview.py` 负责 OKF frontmatter 元数据与原子写回。

**新鲜度策略**（`semantic_ops/freshness_policy.py` + `docs/design/freshness-aware-parent-bubbling-design.md`）是纯函数决策：NOOP / MARK_PENDING / REFRESH_NOW 三态，按 pending 比例与样本上限决定父目录何时聚合刷新。冒泡规则很务实：父目录摘要消费的是直接子目录的 **L0 正文**，L0 没变就停止向上传播；宽目录只累计 `pending_child_changes`，达到阈值再刷。设计文档明确写了四个"首版不做什么"：不做最长陈旧时间兜底、不持久化唯一变化子项集合（容忍事件计数近似）、采样不形成持久化成员概念、不做严格实时一致性——**是成本控制策略，不是一致性协议**。这份"容忍近似"的取舍清单对 CodeWiki 的新鲜度机制演进有直接参考价值。

### 3.3 目录递归检索：结构化检索的另一种答案

`openviking/retrieve/hierarchical_retriever.py` 的 `_recursive_search`（L396–563）：

1. 初始向量搜索，高分条目按目录入最大堆；
2. 每轮并行（`MAX_PARALLEL_CHILD_SEARCHES`）展开 top 目录的子项搜索（混合向量 + 过滤 DSL）；
3. 子项得分与父得分按 alpha 加权传播：`alpha*score + (1-alpha)*parent`；
4. 只有 L0/L1 目录继续入队，L2 文件是终态命中；
5. 连续多轮 top-k 不变或池停滞即收敛退出。

全程 logger.debug + telemetry 计数，每次查询的"目录浏览轨迹"被保留——结果错了可以看到是哪条路径导致的。这与 CodeWiki P0-T 线（检索透明）解决同一个问题，但载体不同：OpenViking 靠树结构天然有序，CodeWiki 靠 BM25 评分明细 + wikilink 路径。

### 3.4 会话→记忆：ReAct 式提取 + 字段级合并

`openviking/session/session.py` 的 `commit_async()` 归档消息后，后台跑两阶段：先生成 Working Memory 摘要（写 session 的 `.overview.md`/`.abstract.md`），再做长期记忆提取。

提取引擎 `session/memory/extract_loop.py` 是**简化版 ReAct 循环**：LLM 带 memory 工具集（`MEMORY_TOOLS_REGISTRY`）多轮调用（默认最多 3 迭代），最终输出结构化操作（upsert/delete），由 `memory_updater.py` / `streaming_memory_updater.py` 落盘。

**记忆 schema** 声明在 `openviking/prompts/templates/memory/*.yaml`，12 类：preferences / profile / entities / events / identity / soul / cases / experiences / skills / tools / trajectories。每类定义 `viking://` 目录位置、文件名模板、字段及**每字段的 `merge_op`**。

**去重/合并/冲突**是亮点：`memory/merge_op/` 提供 patch / replace / immutable / sum 四种字段级策略 + search-replace diff 算法；`skill/dedup.py` 对技能候选做签名去重。即"同一条偏好被第二次提取"不是覆盖整条记忆，而是按字段策略合并。

**注意：提取结果直接 upsert，没有人工确认闸门**——质量全靠 prompt + merge 策略 + dedup 兜底。这是与 CodeWiki draft→confirm 流派的根本分歧。

### 3.5 Agent 集成：hook 注入 + 预算降级

- **hook 路线**（Claude Code / Codex / Cursor / TRAE 等）：`examples/claude-code-memory-plugin/hooks/hooks.json` 注册 SessionStart / UserPromptSubmit / Stop / PreCompact 等 hook。**recall** 由 `scripts/auto-recall.mjs` 在每次用户提交 prompt 前检索，以 `hookSpecificOutput.additionalContext` 注入 `<openviking-context>` 块——**超 token 预算的条目降级为 URI + score**（不丢线索，只降信息量）。**capture** 由 `scripts/auto-capture.mjs`（Stop hook）读 Claude Code transcript，增量推送到持久 OV session，`auto_commit_threshold` 触发归档 + 提取。
- **plugin 路线**：`agent-plugins/`（Agent Plugins 1.0 规范）+ `.claude-plugin/marketplace.json`，给无 hook 能力的客户端用 skill 教模型主动调工具。
- **MCP**：`openviking/server/mcp_endpoint.py` 用 FastMCP 挂在 `/mcp`（streamable HTTP），15 个工具：`find/search/read/list/tree/remember/write/edit/add_resource/list_watches/cancel_watch/grep/glob/forget/health`。`search(mode="context")` 走 `retrieve/context_assembler` 直接组装注入就绪的 token 预算上下文块；另有 stdio 代理 `agent-plugins/servers/mcp-proxy.mjs`。

### 3.6 观测与代码解析

遥测体系分三层：`openviking/telemetry/`（span 模型，errors.stage 分阶段）、`openviking/metrics/`（retrieval.completed 事件 → Prometheus：requests/results/zero_result/latency/rerank）、`observability/usage_audit/`（SQLite 用量审计）。web-studio 可视化检索轨迹。

代码解析：`openviking/parse/parsers/` 覆盖 pdf/word/excel/powerpoint/html/epub/markdown/zip/媒体等，代码走 `parsers/code/ast/aider_repomap.py`——Aider RepoMap 式 tree-sitter tags 查询（vendored `.scm` 文件），做识别符骨架提取与排名。**没有依赖图、调用图、影响分析**，代码理解深度不及 CodeWiki 的 tree-sitter 管线。

---

## 四、与 CodeWiki-CN 的系统对比

### 4.1 知识模型对比

| 概念 | CodeWiki | OpenViking | 评价 |
|------|----------|-----------|------|
| 基本单元 | Markdown 文档 + note（OKF frontmatter） | `viking://` 路径下的文件/目录 + L0/L1 sidecar（OKF frontmatter） | OpenViking 的单元天然带层级，CodeWiki 靠 wikilink 显式织网 |
| 摘要分层 | 文档内 H 段落 + 渐进式阅读 | 写时生成 L0/L1/L2 三层，目录级 sidecar | OpenViking 把分层做成了**一等公民**，CodeWiki 是阅读策略 |
| 知识类型 | note_type 9 类（workaround/known_issue/lesson/pitfall/decision/architecture/…） | 记忆 12 类 YAML schema（含 soul/identity 这类"人格"记忆） | 两者粒度近似；OpenViking 每字段带 merge_op 更细 |
| 生命周期 | draft→confirm→stable + stale_after 窗口 + promotion 候选 | freshness_policy 三态 + 冒泡 + merge_op 字段合并 | **同一问题的两种答案**：CodeWiki 靠人复核，OpenViking 靠策略自动 |
| 信任模型 | 评审闸门是硬约束（confirm_note/confirm_task_memories） | 无闸门，dedup+merge 兜底 | 分歧最大之处，见 4.3 |

### 4.2 检索与信号闭环对比

| 环节 | CodeWiki | OpenViking |
|------|----------|-----------|
| 召回 | BM25 + jieba + wikilink 多跳，authority 权重，dedup 豁免 | dense+sparse 混合 + 目录递归 + alpha 父分传播 |
| 透明度 | P0-T 线检索透明（评分明细可解释） | retrieval trajectory + web-studio 可视化 |
| 热度信号 | retrieval_stats.db（三元组 hit/last/adopted） | RetrievalStatsDataSource → Prometheus |
| 采纳信号 | adoption_events（referenced-docs 声明注释，adopted_weight=0.06） | usage-reporter sink + usage audit |
| 信号消费 | 排序 authority 权重 + lint low_adoption + promotion 候选 | 排序 + 指标面板（未见等价的 low_adoption 治理） |

信号闭环上两者方向一致，CodeWiki 甚至走得更远（low_adoption lint、promotion 是 OpenViking 没有的治理动作）；OpenViking 的优势在遥测基建成熟度（Prometheus、span、审计存储）。

### 4.3 哲学分歧：闸门 vs 合并

这是本次调研最值得记录的对照。同样面对"会话里提取的知识不可靠"：

- **CodeWiki**：蒸馏产出一律 draft，人确认才转正（note 和 task memory 双轨都是）。代价是规模化瓶颈，收益是库内知识可信、lint/health score 有意义。
- **OpenViking**：ReAct 提取直接 upsert，靠 12 类 schema 的字段级 merge_op（patch/replace/immutable/sum）+ 签名 dedup 控制质量。代价是噪声记忆可能长期留存，收益是零人工成本、记忆库随使用自动生长。

OpenViking 的 merge_op 设计对 CodeWiki 的 `consolidate_notes` 有直接借鉴价值：目前 CodeWiki 的 note 整合是整条级别的（合并/覆盖），如果 note frontmatter 增加字段级合并策略，同一主题的多条 draft 可以自动预合并后再走一次 confirm，闸门压力会小很多。

### 4.4 规模与成熟度对比

OpenViking 是公司级投入：多语言技术栈（Python 2.9 万行 + Rust + C++ + TS SDK）、626 测试文件、约 25 个 CI workflow、多 SDK 发布管线、SaaS + 私有化商业版、VLDB 论文。CodeWiki 是个人项目：单语言、266 测试、PyPI 发布。**但这不构成能力劣势的判断依据**——两者深耕的层不同，OpenViking 至今没有（按其设计文档判断也不打算做）AST 级代码结构理解，而这正是 CodeWiki 的核心资产。

---

## 五、借鉴清单（按优先级）

> 许可证提醒：OpenViking 主项目为 **AGPLv3**。以下均为**思想借鉴**（机制/策略/schema 设计），不涉及代码复制；若未来做集成互操作，也应以协议/数据格式为界面而非源码。

### P1：低成本、可直接落地

1. **目录级 L0 摘要 sidecar**。给 `repowiki/wiki/` 的每个目录（或每个 module 文档）生成一个 `index.abstract`（一句话 + 100 token 内），渐进式阅读入口先读全部 L0 再决定展开谁。这是对现有 reading_guide 的自然增强，实现成本一个 ingest 步骤，收益是"预展开"阶段的 token 开销数量级下降。可与新鲜度机制联动（module 文档刷新时同步刷 L0）。
2. **注入预算降级模式**（URI + score）。AGENTS.md 注入约定段和 adoption_hint 当前是全量文本注入；借鉴 auto-recall.mjs 的做法：超过预算的条目降级为"文档路径 + 相关性分数"一行，Agent 需要时再 query。这直接控制 IDE 上下文占用，是对 P1-A 线的低成本补强。
3. **merge_op 字段级合并进 consolidate_notes**。note schema 增加字段合并策略（可先只做 replace/append 两档），多条同主题 draft 自动预合并，人只 confirm 一次。缓解闸门瓶颈。

### P2：中期演进方向

4. **记忆类型 schema 化参考**。OpenViking 用 YAML 声明 12 类记忆的目录/文件名模板/字段/merge_op，新类型即加 YAML。CodeWiki 的 note_type 目前散在 schema.yaml 配置 + handler 常量里，可参考其"声明式类型定义"收敛（注意避开 inputSchema 枚举与 handler 常量不同步的历史坑）。
5. **遥测出口标准化**。retrieval_stats.db 目前本机单机；参考其 Prometheus exporter 模式，把检索热度/zero-result/采纳事件以标准 metrics 暴露，为将来团队部署铺路。
6. **提取循环的 ReAct 化**。distill_conversation 目前是单轮 LLM 重活（Mode A/B/C 都是一次性产出）；OpenViking 的 extract_loop（带工具、限 3 迭代）在"提取过程中发现需要查已有笔记再决定 upsert 还是 patch"这类场景上更强。可作为 distill v2 的参考。

### P3：架构级决策，暂不动

7. **embedding 混合检索**。目录递归 + 向量检索在 LoCoMo/tau2 上有实证收益，但引入 embedding 意味着放弃"零模型依赖检索"这一卖点，且 BM25+wikilink 在代码知识域（术语精确、链接密集）的表现未必差。建议：保持现状，等出现"BM25 召回明显不够"的真实案例再评估。
8. **运行时记忆层**（跨项目/跨会话）。这是 OpenViking 的主场，CodeWiki 贸然进入性价比低；更好的姿态是**互操作**——CodeWiki 的 repowiki 作为 OpenViking 的 resource 被 `ov add-resource` 消费（其 ingest 已支持 git 仓库），或暴露 MCP 工具给它的 Agent 生态。OKF frontmatter 双方同源，互操作的数据格式基础已经存在。

### 明确不借鉴的

- **无闸门直写**：与 CodeWiki 的可信知识定位冲突，不采纳。
- **自研向量库 / C++ 引擎**：工程投入不在一个量级，也无必要。
- **SaaS 多租户体系**：当前阶段无此需求。

---

## 六、建议行动清单

1. 把本报告第五节 P1 三项（L0 sidecar / 注入预算降级 / merge_op 预合并）纳入 P2 阶段候选 backlog，与已实施的 P0/P1 机制（摩擦触发、采纳信号、新鲜度）同列评估。
2. 互操作验证实验（半天）：在装有 OpenViking 的环境 `ov add-resource` 一个带 repowiki 的仓库，观察其 L0/L1 生成对 CodeWiki 文档的消费效果——这能直接检验"CodeWiki 产出 = OpenViking 优质资源"的组合叙事。
3. 关注两个上游动向：`docs/design/l0-l1-okf-sidecars-rfc.md` 的 OKF 演进（双方格式是否会进一步对齐），以及 VikingMem 论文（arXiv:2605.29640）的完整版——其中 memory 生命周期管理部分与 CodeWiki 的 promotion/freshness 设计直接相关。

---

## 附：本报告涉及的关键源码索引（OpenViking）

| 机制 | 文件（相对仓库根） |
|------|-------------------|
| 向量库（C/D/T 三表） | `src/index/`、`src/store/`、`openviking/storage/vectordb/` |
| 语义分层管线 | `openviking/storage/queuefs/semantic_processor.py`、`semantic_dag.py`、`abstract_overview.py` |
| 新鲜度策略 | `openviking/storage/queuefs/semantic_ops/freshness_policy.py` + `docs/design/freshness-aware-parent-bubbling-design.md` |
| 目录递归检索 | `openviking/retrieve/hierarchical_retriever.py`（`_recursive_search`，L396–563） |
| 会话记忆提取 | `openviking/session/session.py`（`commit_async`）、`session/memory/extract_loop.py`、`memory/tools.py` |
| 记忆 schema / 合并 | `openviking/prompts/templates/memory/*.yaml`、`session/memory/merge_op/`、`session/skill/dedup.py` |
| recall/capture hook | `examples/claude-code-memory-plugin/hooks/`、`scripts/auto-recall.mjs`、`scripts/auto-capture.mjs` |
| MCP endpoint | `openviking/server/mcp_endpoint.py` |
| 上下文组装 | `openviking/retrieve/context_assembler.py` |
| 代码骨架解析 | `openviking/parse/parsers/code/ast/aider_repomap.py` |
| 遥测/指标 | `openviking/telemetry/`、`openviking/metrics/`、`openviking/observability/usage_audit/` |
| 设计文档 | `docs/design/`（20 篇，重点：`l0-l1-okf-sidecars-rfc.md`、`session-memory-extraction-flow.md`、`traj-exp-experience-learning-redesign.md`） |
