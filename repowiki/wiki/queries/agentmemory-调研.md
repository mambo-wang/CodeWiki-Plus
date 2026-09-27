---
type: Query
title: agentmemory 调研：重运行时记忆路线的极致样本
description: "- 日期：2026-09-24"
tags: [竞品调研, agent-memory, 他山之石]
generated: { by: codewiki/5.13.0, at: 2026-09-24T12:55:13Z }
stale_after: 2026-12-23
aliases: ["agentmemory-调研"]
status: stable
metadata:
  generated_from: "51cddcf"
  resource: "repo://CodeWiki-Plus"
  code_fingerprint: sha256:f538500108deede284b99fb595d614cb4021e6c4ade0abfca3a17fc6214b9fed
---
# agentmemory 调研（rohitg00/agentmemory）

- 日期：2026-09-24
- 任务：他山之石
- 方式：克隆源码读代码（D:\repos\agentmemory，HEAD 2026-09-24，v0.9.29），非文档站
- 结论速览：**三项借鉴全部不立项**，去向 absorbed / deferred / excluded（见文末）

## 一、项目定位

给 AI 编码 agent（Claude Code / Cursor / OpenCode / Gemini CLI 等）做持久记忆的 TypeScript 项目。核心理念：**agentmemory 本身就是一个运行中的 iii 实例**——用 iii-engine 的三个原语（worker / function / trigger）组合出全部运行时，KV 状态、流、OTel 追踪由 iii 自带 worker 提供，不装 Postgres/Redis/Express/pm2（README.md:1265）。

规模：184 源文件 / ~42,200 LOC / 1,674 测试 / 264 函数 / 50 KV scopes（README.md:1302，本仓库实测 src 下 191 个 .ts、test 下 166 个测试文件）。版本 v0.9.29，Apache-2.0，作者 Rohit Ghumare。

## 二、架构

### 2.1 运行时底座：iii-engine 三原语

- **StateKV**（src/state/kv.ts:3-47）：全部状态经 `sdk.trigger({function_id: 'state::get/set/update/delete/list'})` 走 iii 的 KV worker，自建层极薄（get/set/update/delete/list 五个方法）。
- **函数注册**：`sdk.registerFunction("mem::observe", ...)` 风格，264 个函数全部这样注册（如 observe.ts:46、crystallize.ts:23、consolidation-pipeline.ts:50）。
- **引擎强绑定**：pin iii-engine v0.22.1，worker 只会说该引擎的 wire protocol，版本不匹配直接拒绝启动（README.md:139, 796）。Windows 原生需手动装 iii.exe，或 WSL2/Docker（README.md:808）。
- **端口**：REST 3111 / viewer 3113 / streams 3112 / engine WS 49134（README.md:1419-1426）。

### 2.2 采集管线（hooks → 观察）

Claude Code 等 harness 的 hook 事件全量采集：

| Hook | 采集内容 |
|---|---|
| SessionStart | 项目路径、session ID |
| UserPromptSubmit | 用户 prompt（隐私过滤后） |
| PreToolUse | 文件访问模式 + enriched context |
| PostToolUse | 工具名、输入、输出 |
| PostToolUseFailure | 错误上下文 |
| PreCompact | 压缩前重注入记忆 |
| SubagentStart/Stop | 子代理生命周期 |
| Stop / SessionEnd | 会话摘要 / 完成标记 |

（README.md:972-984）

`mem::observe`（observe.ts:46-119）处理流程：SHA-256 去重（5 分钟窗口）→ 隐私过滤（stripPrivateData 剥离 API key/secret/`<private>` 标签）→ 存 raw observation → 默认**合成压缩**（零 LLM）→ 有 embedding provider 时算向量 → BM25 索引。

### 2.3 四层记忆巩固（仿人类睡眠巩固）

| Tier | 内容 | 类比 |
|---|---|---|
| Working | 工具使用的 raw observations | 短期记忆 |
| Episodic | 压缩后的会话摘要 | "发生了什么" |
| Semantic | 提取的事实与模式 | "我知道什么" |
| Procedural | 工作流与决策模式 | "怎么做" |

（README.md:959-968）

巩固管线 `mem::consolidate-pipeline`（consolidation-pipeline.ts:50-100+）：
- **Semantic 合并**：≥5 条会话摘要才触发，取最近 20 条，LLM 用 `<fact confidence="...">` 标签格式输出事实，按小写全等去重，已存在则 accessCount++。
- **Procedural 提取**：从动作链提取工作流模式。
- **衰减**：`applyDecay`（consolidation-pipeline.ts:21-43）——超过 decayDays 后每周期 strength × 0.9，下限 0.1；访问可增强。
- **矛盾检测与解决**、**TTL 过期**、**重要性驱逐**（evict.ts:25-30 默认：30 天 stale session、90 天低重要度、每项目 10K observations 上限）。

### 2.4 检索：三流混合 + RRF

- **BM25**（自实现，search-index.ts:12-49，k1=1.2 b=0.75）：词干化 + 同义词扩展 + CJK 分词（可选 @node-rs/jieba / tiny-segmenter，无则整段 token 化并 stderr 提示一次，schema.ts:95-100 注释解释 CJK 无空格导致去重失效的坑）。
- **Vector**：cosine 相似度，embedding provider 可插拔（本地 all-MiniLM-L6-v2 免费 / Gemini / OpenAI / Voyage / Cohere / OpenRouter，README.md:1034-1041）。keyless 模式自动禁用向量。
- **Graph**：知识图谱实体抽取 + BFS 遍历（graph.ts 39KB、graph-retrieval.ts 11.6KB）。
- **融合**：RRF（k=60）+ 会话多样性（每 session 最多 3 条）（README.md:1018）。
- **smart-search**：BM25 + 向量 + 图结构匹配三流融合，keyless 也能用图数据。
- **召回卫生**：被 supersede 的记忆版本从所有检索路径剔除，版本链保留全史（README.md:993）。

### 2.5 高层能力（264 函数中的代表）

- **crystallize**（crystallize.ts:23-80）：把已完成动作链（done/cancelled）LLM 摘要成 crystal digest（narrative/keyOutcomes/filesAffected/lessons），lessons 自动转存 lesson-save。
- **reflect / lessons / skill-extract**：会话反思、教训保存、技能提取（与 CodeWiki 的 ingest_note/技能提取任务同构）。
- **slots**（slots.ts:14-70）：固定槽位记忆（persona/user_preferences/tool_guidelines/project_context/guidance/pending_items），带 sizeLimit、pinned、project/global scope——本质是结构化的 CLAUDE.md/MEMORY.md。
- **routines / sentinels / mesh**：例程编排、哨兵触发器（webhook/timer/threshold/pattern/approval）、多节点记忆共享（mesh.ts:19-55 有 SSRF 防护：禁 localhost/私网 IP/DNS 解析到私网）。
- **team memory**：团队命名空间共享+私有记忆。
- **Claude bridge**：与 MEMORY.md 双向同步。
- **Git snapshots**：记忆状态版本/回滚/diff。
- **eval**：LongMemEval 基准 + 自建 coding-life 基准，grep/vector/agentmemory 三 adapter 对比（eval/runner/longmemeval.ts:11-15）。

### 2.6 MCP 面

54 tools / 6 resources / 3 prompts / 17 skills（README.md:1047）。MCP 包是薄 shim：能连上 server 走代理模式暴露全部 54 工具；连不上降级为 7 工具本地集（README.md:1049）。`AGENTMEMORY_TOOLS=core` 可裁剪到 8 个核心工具。

## 三、与 CodeWiki 的对照

| 维度 | agentmemory | CodeWiki-Plus |
|---|---|---|
| 定位 | agent 持久记忆（观察→巩固→检索） | LLM Wiki + 知识飞轮（笔记/任务记忆/蒸馏） |
| 存储 | iii-engine KV（SQLite 底座）+ BM25/向量/图索引 | Markdown 文件 + SQLite（BM25 索引） |
| 采集 | hooks 全量自动采集，零手动 | 显式 ingest_note / 任务记忆直写 |
| 确认闸门 | 无（自动巩固） | draft→confirm 显式确认（ADR-0002） |
| LLM 依赖 | 合成压缩默认零 LLM，LLM 巩固可选 | prepare→推理→submit，LLM 外置 |
| 检索 | BM25+向量+图 RRF 融合 | BM25 + wikilink 图 |
| 规模 | 42K LOC / 264 函数 / 54 MCP 工具 | 轻量 Python |

共同点：都信奉「工具做确定性簿记、推理在调用方」；都有四层/多类记忆分层（working/episodic/semantic/procedural vs raw/笔记/任务记忆/doctrine）；都重视召回卫生（supersede 剔除索引 vs supersedes 链）。

## 四、可借鉴点评估（四问过滤）

### 候选 1：合成压缩（零 LLM 压缩）→ **absorbed（认知）**

`compress-synthetic.ts:7-10`：默认路径不调 LLM，纯启发式（工具名→类型推断、文件路径抽取、截断拼接）把 raw observation 压成 CompressedObservation。0.8.8 起默认（#138）。

**评估**：CodeWiki 的蒸馏走 prepare→LLM→submit，无零 LLM 路径。但 CodeWiki 的 raw 是对话文本，启发式压缩收益低；且 CodeWiki 有「确认闸门」原则，自动压缩产物未经确认不可入检索语料。**不立项，吸收为认知**：若未来 raw 积压严重且蒸馏 subagent 不可用，可考虑启发式预压缩降低 read_file 成本——但需过确认闸门。

### 候选 2：记忆衰减/驱逐（Ebbinghaus 曲线 + strength 衰减）→ **deferred**

`consolidation-pipeline.ts:21-43` 的 applyDecay + evict.ts 的三策略驱逐（stale session / 低重要度 / 容量上限）。

**评估**：CodeWiki 的 lint_wiki 已有 low_adoption 检查（零采纳高频笔记标记），语义近似但机制不同：lint_wiki 是「提示人处理」，agentmemory 是「自动驱逐」。自动驱逐与 CodeWiki「候选必有去向、排除必填原因」的 Doctrine 冲突——驱逐即静默删除。**不立项，deferred**：等 lint_wiki 的 low_adoption 数据积累后，若确认存在大量零采纳笔记且人工处理不动，再评估带审计日志的自动降权（非删除）。

### 候选 3：slots 固定槽位记忆 → **excluded**

slots.ts:14-70：persona/user_preferences/tool_guidelines/project_context/guidance/pending_items 六个固定槽位，带 sizeLimit/pinned/scope。

**评估**：与 CodeWiki 现有机制重叠度高——MEMORY.md（用户偏好）+ AGENTS.md（项目约定）+ 任务记忆（pending 进度）已覆盖同等语义，且是纯文件、零运行时依赖。引入 slots 需要常驻 server + KV 存储，违背 CodeWiki 轻量原则。**不立项，excluded**：现有三件套已收敛该需求。

### 候选 4（顺带观察）：CJK 分词去重坑 → 已有笔记覆盖

schema.ts:95-100 注释：CJK 文本无词间空格，`split(/\s+/)` 会把整句折叠成单 token，导致去重静默失效；解法是 CJK 分词 + 字符 bigram shingles。CodeWiki 的 difflib 去重（>0.85 拒绝）作用于中文文本时无此问题（difflib 按字符序列比较），无需行动。

## 五、结论汇总

| 候选 | 去向 | 理由 |
|---|---|---|
| 合成压缩（零 LLM） | absorbed（认知） | 与确认闸门冲突，仅作未来降本备选认知 |
| 记忆衰减/自动驱逐 | deferred | 与「候选必有去向」Doctrine 冲突，等 lint_wiki 数据 |
| slots 固定槽位 | excluded | MEMORY.md+AGENTS.md+任务记忆三件套已覆盖 |
| PreCompact 重注入 | excluded | UserPromptSubmit 薄触发是超集（2026-09-21 定案再确认） |
| RRF 多路融合 | excluded | 前提是多路召回，本仓单流 BM25，为 RRF 而 RRF 是伪需求；未来加向量检索时再议 |
| related_notes 语义召回 | excluded | 注入场景要确定性（task_id 精确匹配），语义召回违背「显式优于缓存」与「工具不持模型」 |
| 会话多样性约束 | deferred | 单源霸屏未实测出现，等 lint_wiki 重复笔记数据 |
| **MCP 工具面裁剪开关** | **立项（P2）** | 真缺口：60+ 工具 schema 全量注入占上下文；registry 加 filter 成本低，与「成本可见性」Doctrine 正向 |

**总体判断**：agentmemory 是「重运行时」路线的极致——常驻 iii-engine、hooks 全量自动采集、264 函数大而全。CodeWiki 是「轻文件」路线——Markdown 即真相、显式确认、零常驻。两者哲学相反，直接移植任何组件都会破坏 CodeWiki 的架构前提（Doctrine：竞品机制价值取决于自身架构前提）。本次调研价值主要在确认边界：**自动采集/自动巩固/自动驱逐这条全自动路线，CodeWiki 明确不走**。

## 六、Round 2 小优化 grill 定案（2026-09-25）

对「存储格式/检索优化」级小候选二次过 grill，事实基础为本仓代码核对（retrieval.py / wiki_search.py / task_manager.py / capture_conversation.py）：

- **已有等价、无需行动**：同义词扩展（ontology.yaml，retrieval.py:281-345）、CJK 分词（jieba 可选+regex 降级，retrieval.py:197-238）、SHA-256 去重（capture_conversation.py:14,394-428）、BM25 参数微调（无实测数据支撑）。
- **deferred**：会话多样性约束（等 lint_wiki 重复笔记数据）；
- **excluded**：RRF 融合（单流无第二路可融）、related_notes 语义召回（注入场景要确定性）。
- **立项（P2）**：MCP 工具面裁剪开关——`CODEWIKI_TOOLS=core` 环境变量，registry 加 filter，参考 agentmemory 的 core-8 清单思路按本仓场景重定义核心集。

## 附：关键文件索引

- 采集入口：src/functions/observe.ts、src/hooks/*.ts
- 巩固管线：src/functions/consolidation-pipeline.ts、consolidate.ts、evict.ts、retention.ts
- 检索：src/state/search-index.ts（BM25）、hybrid-search.ts、vector-index.ts、src/functions/smart-search.ts
- 高层能力：crystallize.ts、reflect.ts、lessons.ts、skill-extract.ts、slots.ts、routines.ts、sentinels.ts、mesh.ts
- 存储底座：src/state/kv.ts、schema.ts（50 个 KV scope 常量表）
- 评测：eval/runner/longmemeeval.ts（grep/vector/agentmemory 三 adapter 对比）
