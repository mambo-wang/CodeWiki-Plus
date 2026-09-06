# DeepWiki 类开源项目对比调研报告

> 调研日期：2026-09-06 ｜ 调研对象：langchain-ai/openwiki、AsyncFuncAI/deepwiki-open、AIDotNet/OpenDeepWiki、sopaco/deepwiki-rs（Litho） ｜ 视角：与 CodeWiki-CN（mambo-wang/CodeWiki-Plus）的对比与借鉴
>
> **方法论**：四个项目均克隆源码通读实现（commit 时点 2026-08-15 ~ 2026-09-04），所有代码事实标注 `文件:行号`；GitHub 元数据取自 api.github.com（2026-09-06）。已遵循本仓既有教训——"竞品调研必须克隆源码读代码，文档站可能系统性滞后"，本次调研再次验证了该教训（多个项目的 README 与代码存在实质性出入，见 §1）。
>
> 详细源码调研笔记存档于 `.research-competitors/notes/`（openwiki-notes.md、deepwiki-open-notes.md、OpenDeepWiki-notes.md、deepwiki-rs-notes.md）。

---

## 一、五项目全景定位

| 项目 | Stars | 技术栈 | 产品形态 | 一句话定位 |
|---|---|---|---|---|
| **CodeWiki-CN** | （本仓） | Python + Vue | MCP 服务端（47 工具）+ CLI | 本地优先的 LLM Wiki 生成与知识飞轮，嵌入 IDE Agent 工作流 |
| **openwiki** | 16.2k | TypeScript + LangChain/deepagents | npm CLI（Ink UI）+ 内部 MCP + 宿主集成 | "自维护 wiki"：planner→逐页 worker 的 agentic 生成 + 事实治理（Claims） |
| **deepwiki-open** | 17.9k | Next.js 前端 + **Python FastAPI 后端**（AdalFlow） | Web 服务（单 Docker 容器双进程） | Devin DeepWiki 的开源复刻：输入仓库 URL → 生成 wiki + 网页问答 |
| **OpenDeepWiki** | 3.6k | ASP.NET Core（.NET 10）+ Next.js | 自托管多仓库 SaaS 平台 | 多仓/多分支/多语言托管的知识库平台，组织权限 + Admin 后台 + MCP 商业化接口 |
| **deepwiki-rs (Litho)** | 1.7k | Rust（tokio + rig-core） | 纯 CLI | 一次性 C4 架构文档生成器，四阶段声明式 agent 流水线 |

**代码规模与活跃度**（2026-09-06）：

| 项目 | 首次创建 | 最近推送 | 开放 Issue | 语言 | 协议 |
|---|---|---|---|---|---|
| openwiki | 2026-06-22 | 2026-09-05 | 145 | TypeScript | MIT |
| deepwiki-open | 2025-04-30 | 2026-09-03 | 267 | Python* | MIT |
| OpenDeepWiki | 2025-04-27 | 2026-08-27 | 22 | C# | MIT |
| deepwiki-rs | 2025-09-05 | 2026-08-14 | 2 | Rust | MIT |

*deepwiki-open 的 GitHub 主语言标记为 Python，但 Next.js 前端 + FastAPI 后端的组合常被误认为纯 TS 项目——核心逻辑全在 Python 侧（`api/main.py:50-72`）。

**关键背景注记**：deepwiki-rs 已宣布演进为后继项目 Terrain（README.md:31-40），Litho 收缩为维护态 C4 文档生成器，主理人开发重心已转移；借鉴其机制需考虑该项目的生命周期风险。

### README 与代码不符的"宣传水分"（调研发现）

源码核对发现以下宣称与实现存在实质出入，提示我们任何竞品借鉴前必须读代码：

| 项目 | 宣称 | 实际 |
|---|---|---|
| deepwiki-rs | 支持 Go（README.md:102） | 语言处理器仅 12 个，无 Go（`src/generator/preprocess/extractors/language_processors/mod.rs:44-57`） |
| deepwiki-rs | "research agents in parallel"（README.md:417） | `do_parallel_with_limit` 仅用于两处，agent 间与目录总结均为串行 for 循环（`src/generator/preprocess/mod.rs:146`） |
| deepwiki-rs | `--skip-*` 旗标可跳过阶段（README.md:495） | 三个旗标是死代码，全库无消费点（`src/cli.rs:36-44`） |
| deepwiki-rs | 缓存省 token | `CacheEntry` 存了 `model_name` 但 `get()` 不比对（`cache/mod.rs:88-109`），换模型命中旧答案 |
| OpenDeepWiki | "多语言代码分析" | 无 AST/语言解析器，代码理解全靠 LLM + ReadFile/ListFiles/Grep（`Agents/Tools/GitTool.cs:770-781`）；"多语言"实为输出文档多语言 |
| deepwiki-open | LiteLLM 支持 | LiteLLM 只是自研 10 客户端注册表中的一个可选 provider（`api/clients/litellm.py:8-49`），并非核心抽象 |

---

## 二、实现逻辑对比（六维度）

### 2.1 架构定位与代码分析方式

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| 代码分析 | 多语言 AST（Python）+ tree-sitter，调用图 + 服务边界检测 + 跨服务路由匹配（`AnalysisPipeline`） | **零静态分析**，LLM agent 用 ls/glob/grep/read_file 读代码 | **零静态分析**，纯文本文件树 + README + 向量检索 | **零静态分析**，LLM + ReadFile/ListFiles/Grep 三件套 | **正则/关键词匹配冒充 AST**，12 语言处理器用 `content.matches("fn ")` 计数复杂度 |
| 依赖结构 | 组件依赖图 + 拓扑排序驱动生成顺序 | planner prompt 要求按 "owned systems / cross-system workflows" 组织，无机械提取 | 无 | 无 | import 语句正则匹配 |
| 分析产物 | SQLite 缓存（components + relationships + module_tree） | 无持久化分析产物，planner 探索结果即弃 | FAISS 向量库 + LocalDB pickle | 目录树 JSON（LLM 写出） | 进程内 HashMap Memory（作用域隔离） |

**这是五个项目最根本的分水岭**：CodeWiki 是唯一做精确代码分析（AST/tree-sitter 调用图）的项目。四个竞品全部走"LLM 直接读文件"路线——openwiki 和 OpenDeepWiki 是有意的架构选择（相信 agent 的泛化能力），deepwiki-open 用向量检索替代，deepwiki-rs 的正则匹配介于两者之间但精度最低。四家的代码事实正确性完全依赖 LLM，重构后行号引用易漂移；CodeWiki 的分析图谱是天然更强的重定位预言机（`docs/OpenWiki-借鉴详细设计方案.md` §1.3 的判断依然成立）。

### 2.2 文档生成流程

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| 结构生成 | 依赖图聚类模块树 → 拓扑排序处理顺序 | LLM planner 出 plan（pages[] + deletePages），有界 agent 只能 `submit_plan` | LLM 生成 XML 结构（4-6 页或 8-12 页） | LLM agent 用 `WriteCatalog` 写 JSON 目录 | C4 层级：Preprocess → Research（7 agent 按 C1-C4 组织）→ Compose（6 editor）→ Output |
| 逐页生成 | LLM 按模块树逐模块生成，`[[...]]` 交叉链接 | 每页独立 worker agent，docsOnly 沙箱只能写自己那页 | 复用 RAG 聊天管线逐页生成（向量检索驱动） | `Parallel.ForEachAsync` 并行 + 每篇硬超时 + 断点续跑 | 6 editor 顺序执行，KeyModulesInsight 与 Deep Dive 两处并行 |
| 生成可靠性 | lint_wiki 20 项检查兜底 | 提交校验失败以"可纠正的 tool 错误"回给 worker 重试；崩溃则回滚快照跳页 | 每页 2 次重试 + 失败占位页 | 单篇失败不中断 + 已落盘 path 跳过 | ReAct 迭代耗尽后 summary reasoning 降级兜底 |
| 收尾 | frontmatter 注入 + 交叉链接 + schema 校验 | **确定性收尾（非 LLM）**：mermaid 校验→索引→内链→Claims 投影→provenance 盖章 | 空括号引用后处理成真实带行锚链接 | Skill 包打包（SKILL.md + 文档 zip） | 删除整个输出目录全量重写（`src/generator/outlet/mod.rs:79-82`） |

**观察**：openwiki 的"确定性收尾"与 CodeWiki 的 lint 后置校验理念一致但更彻底——它把 mermaid 校验、索引同步、内链校验全部做成代码而非 LLM 判断，`index.md` 由代码确定性生成、禁止模型手写（`src/agent/prompts/code.ts:31`）。CodeWiki 的对应收敛点是 lint_wiki，但索引与内链目前部分依赖生成时注入而非收尾时机械统一。

### 2.3 检索与问答

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| 检索方式 | BM25×authority×heat 排序（`cache.py::_doc_authority`） | **无检索**，agent wiki-first 翻文件 | FAISS 向量单路召回 top_k=20，无 rerank | **无 RAG**，目录注入工具描述 + agent 翻文档 | **无检索**（问答在外部姊妹项目） |
| 问答链路 | IDE Agent 经 MCP 调 query_wiki | agent 聊天（wiki-first prompt） | WebSocket 流式 + SSE 回退 | 网页聊天（SSE 流式含 tool_call 事件） | 无 |
| 会话管理 | 任务记忆（分片追加式，多用户 git 隔离） | SQLite checkpointer 持久化 + 裁剪防膨胀 | 前端带全量历史，后端内存重建，重启即失 | 前端带全量历史，服务端仅审计日志 | 无 |
| 多语言 | — | 确定性翻译 pass + 模型只写新增 | prompt 指令 + 每语言独立缓存全量重生成 | LLM 翻译已有目录与文档（不重新生成） | 8 种语言 prompt 指令 |

**有趣的反差**：star 数最高的两个项目（deepwiki-open 17.9k、openwiki 16.2k）在检索上走了完全相反的极端——deepwiki-open 是五家中唯一有向量 RAG 的，openwiki 干脆放弃检索靠 agent 翻文件。而检索质量上限：deepwiki-open 的纯 FAISS 单路召回（无 rerank、按词数切分跨块语义割裂）其实在工程上是五家中最弱的检索实现，只是"有"而已。CodeWiki 的 BM25×authority×heat 是中间路线，且唯一带采纳反馈闭环（adopted_count 反哺排序）。

### 2.4 MCP / Agent 集成

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| MCP | 核心形态：47 工具，覆盖分析/文档/知识/质量/任务/工作区 | 内部 MCP：6 个生命周期工具（begin/submit_plan/next_page/inspect_claims/submit_page/finish） | **无 MCP** | HTTP MCP：全局 + 仓库级两端点，7 工具，**API Key + OAuth 2.1 + 用量统计** | **无 MCP** |
| 分发方式 | stdio MCP 接入 IDE | npm 包 + 四宿主安装器（Codex/Claude Code/OpenCode/Cursor） | Docker 镜像 | Docker Compose 自托管 | cargo / Smithery 分发 skill |
| 面向 Agent 的输出 | wiki 即 Agent 记忆（query_wiki 按需取用） | wiki 首先写给 Agent 当记忆用 | 无 Agent 出口 | SKILL.md + 文档 zip 打包下载 | `.ai-context/` 分层知识库（Tier0-3 按稳定性） + 纯 Agent 平行实现 skill |

**关键差异**：OpenDeepWiki 的 MCP 是五家中唯一做了**商业化基建**的——OAuth 2.1 完整流程 + Protected Resource Metadata + 用量统计中间件（`Program.cs:388-392,383`），把"知识库对外服务"当产品能力做。CodeWiki 的 MCP 是面向自有 IDE 工作流的内部工具，openwiki 的 MCP 则是把生成队列开放给外部宿主的"协议化流水线"——三种 MCP 哲学完全不同。

### 2.5 增量更新与知识维护

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| 增量更新 | git diff → affected/cascade 模块 + 页面级 manifest（`page_manifest.py`，D2 已落地） | **四层机制**：git HEAD no-op 检测 + sha256 源指纹 + 页级 checkpoint fast-forward + Claims preflight | **无**（缓存键无 commit hash，上游更新即全 stale） | 仓库级定时检查远程 HEAD，changed files 走 git diff，增量 prompt 禁用 WriteCatalog 防整树重写 | **无**（删目录全量重写） |
| 事实新鲜度 | `stale_after` 时间窗 + `stale_evidence` 证据哈希（D1 已落地） | Grounded Claims：`repo://path#L20-L48` 证据 URI + 行范围重锚 + stale/unresolved preflight | 无 | 无 | 无 |
| 质量治理 | lint_wiki 20 项 + 确认闸门（draft→confirm） + Doctrine 共识 | Claims 账本稀疏 reconciliation（confirm/revise/retract） | 无 | 无 | 无 |
| 评测 | 无（lint 仅结构检查） | **LEDGER 纵向漂移 eval**（supported/stale/invented/unverified 四态 + judge 元评估 ≥0.90）+ DeepSWE 配对实验 | 无 | 无 | 无 |

**这一维度是 CodeWiki 与 openwiki 的"双雄对峙"**：两者在增量与事实治理上工程化程度远超其余三家，且走了不同的路线——openwiki 用"证据 URI + 哈希 + 重锚"把文档过时变成可机械验证的状态机；CodeWiki 用"分析图谱 + 确认闸门 + 采纳计数"把知识质量变成有人负责的资产。CodeWiki 已在 2026-08-31 借鉴了 openwiki 的 D1-D5（evidence.py、page_manifest.py、stale_evidence 均已落地），本次对比确认那轮借鉴选点准确。

### 2.6 工程底座

| 维度 | CodeWiki-CN | openwiki | deepwiki-open | OpenDeepWiki | deepwiki-rs |
|---|---|---|---|---|---|
| 并发控制 | 生成走 LLM 后端并发配置 | 页队列严格串行（成本/一致性取舍） | 三层信号量（RAG 索引 4 / 任务池 CPU/2 / 页级 1） | **DB 租约 + 槽位 + 心跳 + 崩溃恢复**（集群级，单体内实现分布式调度） | tokio Semaphore 限流，仅两处使用 |
| 任务恢复 | 增量锚点（commit_id）复用 | 持久化队列 `.run.json`，CI 挂了重跑即续 | get-or-create 幂等提交 + 终端态 TTL 300s | DB 轮询 + 已落盘 path 跳过（断点续跑） | 无（无增量即无恢复需求） |
| LLM 提供商抽象 | llm_services.py 单层 | LangChain 生态 | 自研 10 客户端注册表 | 预设目录 + DB 覆盖，模型按"目录模型/内容模型"分角色绑定 | rig-core 8 provider + **双模型 efficient/powerful fallover** |
| 缓存 | SQLite 分析缓存 | — | FAISS pickle + wiki JSON（无版本键） | 内存缓存抽象框架 | **MD5(prompt) 文件缓存带 token 统计 + 命中率监控** |

---

## 三、综合评估：各项目的真正差异化

用一句话概括五家的"护城河"：

1. **CodeWiki-CN**：唯一做精确代码分析 + 唯一有知识飞轮（对话→蒸馏→确认→采纳反哺）的项目。牺牲了"开箱即用 Web 服务"的传播性，换取知识资产的可信治理与 IDE 深度集成。
2. **openwiki**：事实治理工程化最彻底（Claims + 多层增量 + LEDGER eval），且是唯一认真做"wiki 作为 Agent 记忆"叙事的——OKF frontmatter 明确 description "optimized for search & retrieval"（`src/agent/prompts/code.ts:63-88`）。弱在检索与静态分析全空白。
3. **deepwiki-open**：唯一有向量 RAG 与 Web 问答体验的（这是它 star 最高的直接原因——Demo 效应），但工程上缓存无版本、无增量、无 MCP，是"演示优先"的形态。
4. **OpenDeepWiki**：唯一做"平台化"——多租户、组织权限、Admin 后台、MCP 商业化（OAuth+用量统计）、集群调度。它解决的是"企业内 wiki 服务怎么运营"的问题，与 CodeWiki 解决的"个人/团队知识怎么可信"是不同问题域。
5. **deepwiki-rs (Litho)**：声明式 agent 流水线框架（StepForwardAgent trait）是漂亮的抽象，prompt 压缩/双模型 fallover/缓存监控等细节扎实，但无检索、无增量、无 MCP，且项目已转向后继 Terrain。

**CodeWiki-CN 的相对位置**：在"事实正确性"（AST 分析）与"知识治理"（确认闸门+飞轮）两个维度上是五家最强；在"传播性"（无 Web Demo）、"平台化"（无多租户）、"评测体系"（无 LEDGER 类纵向 eval）三个维度上存在结构性缺位——前两者是定位取舍，第三者是真实短板。

---

## 四、可借鉴点（按优先级）

> 排除已落地的 D1-D5（证据哈希/页面 manifest/Mermaid 降级/no-op 防扰/评测框架——2026-08-31 那轮借鉴，`codewiki/src/evidence.py`、`mcp/tools/page_manifest.py`、`stale_evidence` 检查均已存在）。以下按「价值 × 落地成本」排序，每项给出对标机制与 CodeWiki 落点。

### P0（高价值、与现有架构同构、可直接落地）

**B1. 确定性收尾管线（对标 openwiki `wiki-finalizer.ts:248-285`）**
openwiki 在每次生成/更新后跑一段纯代码收尾：mermaid 校验 → 索引同步 → 内链校验 → provenance 盖章，`index.md` 禁止模型手写。CodeWiki 现状是生成时注入交叉链接 + lint 后置检查，但索引与内链缺少"生成后机械统一"这一步。落点：`analyze_repo` 生成流程末尾增加 `finalize_wiki_artifacts` 阶段，复用 lint_wiki 已有的内链/mermaid 检查逻辑做"检查+修复"而非仅"检查"。成本约 2-3 人日。

**B2. LLM 调用文件缓存带 token 统计（对标 deepwiki-rs `cache/mod.rs:43-67,127-180`）**
MD5(prompt) 为 key 的 JSON 文件缓存，带 token 用量统计与命中率监控（`cache/performance_monitor.rs`）。CodeWiki 的全量 `analyze_repo` 重跑（幂等重跑自动沿用）目前每模块都重新调 LLM；加 prompt 哈希缓存后，未变模块的生成可零成本命中。注意 deepwiki-rs 的教训：**缓存键必须校验 model_name**（它没做，`cache/mod.rs:88-109`，换模型命中旧答案）。落点：`llm_services.py` 加可选缓存层，key = hash(prompt + model + model 参数)。

**B3. 生成并发三层闸门（对标 deepwiki-open `api/rag/rag.py:27-34`、`api/services/wiki/tasks.py:62-66`）**
RAG 索引并发、任务池并发、页级并发三个独立信号量，各自可配置。CodeWiki 的生成并发目前是单一配置；分析（CPU 密集 AST）与生成（IO 密集 LLM 调用）性质不同应分开限流。成本约 1 人日。

### P1（高价值、需要一定设计工作）

**B4. 双模型 efficient/powerful + 错误注入 fallover（对标 deepwiki-rs `llm/client/mod.rs:106-118`）**
主模型失败时把错误信息注入 prompt 换 fallback 模型重试 + 指数退避。对 CodeWiki 的价值：结构生成（目录/模块树描述）用便宜模型、逐页内容用强模型的分角色绑定（OpenDeepWiki 也有类似设计：ResolveCatalogModelAsync/ResolveContentModelAsync）。本机 GitHub 网络双通道不稳定（已知环境事实），LLM 端点同样可能间歇失败，fallover 提升无人值守批处理（cron 定时重建）的鲁棒性。

**B5. 持久化可恢复页队列（对标 openwiki `.run.json` + CI 挂了重跑即续）**
把"逐模块生成"从一次性循环改为持久化队列：每模块推进前状态落盘，中断后 resume 从断点继续。与 B2 缓存互补（缓存省重复调用，队列保进度不丢）。对大仓库全量生成（26+ 模块）的容错价值明显。落点参考 openwiki 的 begin → submit_plan → next_page → submit_page → finish 生命周期（`src/agent/repository-runner.ts:373-397`）。

**B6. `stale_evidence` 检查结果回灌增量决策（对标 openwiki Claims preflight 输出喂给 planner）**
openwiki 的 update 流程会把 Claims preflight 的 stale/unresolved 清单直接作为 planner 的输入，决定哪些页真正需要重写（`src/agent/repository-prompts.ts:215-231`）。CodeWiki 已有 `stale_evidence` 检查（D1 落地），但结果目前只进 lint 报告；把它接入 `_detect_doc_changes` 的输出（与 affected_modules / stale_pages 并列），成为增量重写范围的第三信号源，闭环就完整了。这是对已落地 D1/D2 的"最后一公里"集成。

### P2（有启发性、按需取用）

**B7. `.ai-context/` 按稳定性分层（对标 deepwiki-rs Tier0-3）**
知识按变更频率分层：Tier0 PROJECT-ESSENCE（几乎不变）→ Tier3 DYNAMICS（当前问题/TODO）。与 CodeWiki 的 wiki/modules（结构层，随代码变）vs notes（经验层，随认知变）天然同构，启发点是**在 schema.yaml 显式声明各页面类型的"稳定性档位"**，让 stale_after 窗口的设定有理论依据而非拍脑袋。

**B8. SSE 心跳 + shield 防代理超时（对标 deepwiki-open `api/routers/repo.py:20-57`）**
每 10s 心跳注释帧躲 undici 300s headers timeout；`asyncio.shield` 保证心跳超时不误杀索引任务。对 CodeWiki 的 MCP 长任务（analyze_repo 全量）在代理/网关环境下的可用性有参考价值。

**B9. init 备份事务含信号回滚（对标 openwiki `wiki-replacement.ts:42-80`）**
重新 init 会备份旧 wiki，失败或 SIGINT/SIGTERM 均回滚。CodeWiki 的 `init_wiki` 幂等重跑已有保护，但缺少"中断即回滚"的事务语义。

**B10. DB 租约式集群并发（对标 OpenDeepWiki `WikiGenerationConcurrencyService.cs:37-64`）**
DB 租约 + 槽位 + 心跳 + 崩溃恢复，单体内实现"每仓库单写者、集群总并发上限"。仅当 CodeWiki 未来走向多实例部署（如团队共享 wiki 服务）时才有必要，当前单机 stdio MCP 形态用不上，记录备用。

### 不建议借鉴（与既有判断一致）

| 项 | 理由 |
|---|---|
| deepwiki-open 的 FAISS 向量检索 | 纯单路召回无 rerank、词数切分跨块割裂，工程上是四家最弱检索实现；CodeWiki 的 BM25×authority×heat + 采纳反馈已更优，且向量库引入嵌入模型依赖，违背"工具无状态、跨 IDE 可移植"原则 |
| openwiki 的 personal 模式 + 9 连接器 | 前轮已明确不借鉴（偏离代码库原生定位） |
| OpenDeepWiki 的多租户平台化 | 与 CodeWiki"本地优先、嵌入 IDE"定位相反，是不同问题域 |
| deepwiki-rs 的正则"AST" | 解析精度反面教材 |
| 各家的 LLM 直读代码（无静态分析）路线 | CodeWiki 的 AST/tree-sitter 调用图是核心差异化资产，不可放弃 |

---

## 五、结论

1. **CodeWiki-CN 的差异化定位在五家中依然成立且稀缺**：精确代码分析（唯一）+ 知识飞轮与确认闸门（唯一）+ 增量更新（与 openwiki 并列第一梯队）。四个竞品全部走 LLM 直读路线，证明了"做 AST 调用图"这条路没有直接竞争者。
2. **openwiki 仍是头号对标对象**，但两轮借鉴后剩余增量集中在工程可靠性（B1 确定性收尾、B5 可恢复队列、B9 事务回滚），其 LEDGER eval 体系（D5）框架已借鉴但尚未实际跑起来——**建议优先把 D5 从设计稿推进到实测**，这是对"文档质量"最硬核的度量。
3. **deepwiki-open 的高 star 验证了"Web Demo 传播效应"**：17.9k star 的项目工程上无增量、无 MCP、检索最弱——如果 CodeWiki 需要传播性，一个只读 Web 可视化（复用现有 Vue 前端）比补齐 RAG 更划算。这是产品决策而非技术决策。
4. **最值得马上动手的三件事**：B2（LLM 调用缓存带 token 统计，1-2 人日、直接降本）→ B6（stale_evidence 回灌增量决策，打通 D1/D2 最后一公里）→ B1（确定性收尾管线，2-3 人日）。

---

## 勘误（2026-09-06，实现期代码核对）

B 系列建议进入实现拷问时（grill-with-docs），逐项核对代码发现三处陈述偏差，勘误如下：

1. **B2 的痛点表述过重**："幂等重跑每个模块都重新调 LLM" 不准确——`analyze_repo` 已有 `no_changes` 短路（`analysis.py:110`）与 `affected_modules` 限定范围两层省钱机制。且模块生成是 agentic 多轮调用（`run_module_agent` 带 tools 走完整轨迹），deepwiki-rs 式 MD5(prompt)→response 缓存不适用，B2 若做只能是模块级指纹缓存（命中跳过整个 agent run）。实现优先级据此下调。
2. **B1 的一半已存在**："索引与内链缺少生成后机械统一" 不准确——`analyze_repo` 末尾已调 `rebuild_index + append_log`（`analysis.py:380-385`），`write_doc_file` 每次写后也调（`doc_writer.py:1577-1585`）。真实缺口仅在 `generate_docs`（`legacy_tools.py:108-179`）跑完 `doc_gen.run()` 后无任何收尾。B1 范围据此收窄为补单点缺口。
3. **B6 已于 2026-09-06 落地**：`collect_evidence_drift`（`evidence.py`）作为 lint 与增量决策的共享采集点，`_enrich_stale_evidence`（`analysis.py`）挂变更路径输出 `stale_evidence_pages` 第三信号源；no_changes 路径静默是显式决策（ADR-0005）。测试 `tests/test_stale_evidence_signal.py` 10 项，定向回归 119 过，ruff 过。

（勘误不改动正文——原表述与代码的差距本身有价值，与 §1 的宣传水分清单互为镜鉴：调研报告也要接受自己提出的"读代码才算数"标准的检验。）

---

*本报告代码事实来源：`.research-competitors/notes/` 下四份源码调研笔记（各含完整行号依据），调研基于 2026-08-15 ~ 2026-09-04 的 commit 时点。CodeWiki-CN 事实来源：`repowiki/wiki/overview.md`、`repowiki/wiki/doctrine.md`、`docs/OpenWiki-借鉴详细设计方案.md` 及本次代码核对。*
