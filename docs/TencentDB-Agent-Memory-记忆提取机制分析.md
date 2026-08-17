## TencentDB Agent Memory：对话记忆提取与经验沉淀机制分析（code/work 模式）

> 分析对象：`TencentCloud/TencentDB-Agent-Memory` 仓库（分支 `feat/server_team`，版本 v2.0.1-beta.2，提交 `97f9465`）
> 分析日期：2026-08-16
> 范围说明：系统的记忆提取分 chat（个人助理）与 code/work（团队协作）两种 prompt 模式，本文**只分析 code/work 模式**——即面向团队群聊/工作场景，从对话记录中提取 L0–L3 分层记忆并沉淀 Skill 经验的完整机制。

---

## 1. 项目概览与记忆架构

### 1.1 组件构成

仓库由四个服务组件和一套 SDK 构成：

| 组件 | 职责 |
| :--- | :--- |
| **MemoryCore** | 核心记忆引擎。负责对话捕获、L0→L3 分层提取管线、Skill 沉淀、记忆召回注入，以 OpenClaw/Hermes 插件或独立 Gateway 服务形式运行 |
| **MemoryKnowledge** | 知识引擎。将文档构建为 Wiki（结构化页面 + 链接图谱）、将代码库索引为 CodeGraph（符号/调用关系/影响路径） |
| **MemoryPanel** | Memory Hub 管理面板。团队/Agent 管理、资产审核、配装（Loadout）、权限控制 |
| **MemoryProxy** | 协议代理。Agent 把 base URL 指向 Proxy 即可零代码接入，协议不变 |
| **sdk/memory-core** | Python / TypeScript 双语言 SDK，封装 v3 API（skill、memory-prompt、memory-generation-log、metadata 等客户端） |

### 1.2 记忆资产分类

项目把"值得留下的信息"统一登记为 Memory Asset，共四类：

- **Chat Memory**（L0–L3 分层记忆）：在 code/work 模式下沉淀的是**团队共享工作记忆**——项目事实、任务、工作方法、决策与交付物，是本文分析的主体；
- **Skill**：从对话和工具调用中提炼的可复用经验（SOP、领域背景、操作约定），有版本、资源文件、触发边界、执行步骤和验证规则；
- **Wiki**：文档的结构化知识图谱；
- **CodeGraph**：代码的符号与调用关系图谱。

### 1.3 分层记忆模型（L0–L3，work 模式语义）

记忆不是平铺记录，而是逐层生长。code/work 模式下各层的定位（对应 prompt 中的团队版命名 L0 Work Event → L1 Work Record → L2 Project Scene Block → L3 Team Operating Memory）：

| 层级 | 保存什么 | 主要用途 | 物理形态 |
| :--- | :--- | :--- | :--- |
| **L0 Conversation** | 原始工作对话与完整上下文 | 核对原话、时间和来源 | 按天分片 JSONL + SQLite 索引副本 |
| **L1 Atom** | 团队共享工作记忆：事实、任务、方法、资产 | 精确召回可执行信息 | JSONL（事实源）+ 向量库/FTS（检索） |
| **L2 Scenario** | 围绕工作方法体系组织的场景知识块（SOP、判断逻辑、禁忌、原则、经验） | 快速恢复一个工作场景的方法论 | `scene_blocks/*.md`（≤15 个）+ 索引 |
| **L3 Team Operating Doctrine** | 团队在所有工作场合可复用的操作原则 | 让 Agent 知道如何判断、执行、避错 | 单个 `persona.md`（≤1200 字） |

设计哲学：生成和召回都分层——平时用 L2/L3 快速进入语境，需要具体事实时通过 BM25、向量检索与 RRF 融合回到 L1/L0。与 chat 模式最大的不同：**work 模式不沉淀个人画像，所有内容面向团队共享，核心产出是"方法论"而非"人物理解"**。

> **重要澄清**：代码库中还有另一套名为 L1/L1.5/L2 的流水线（`src/offload_server/`），那是面向 AI 编码助手的**上下文压缩子系统**（压缩工具调用结果、维护 Mermaid 任务图），与记忆分层无关，只是复用了同一套队列/定时器/Worker 调度基础设施。本文不涉及该子系统。

---

## 2. 端到端数据流总览

```text
【捕获链】
用户消息
  → before_prompt_build Hook（缓存原始 prompt；执行 auto-recall 注入记忆）
  → Agent 执行
  → agent_end Hook（仅成功回合）
  → performAutoCapture：
      ① 原子写 L0（读游标 → 写 JSONL/COS → 推进游标，文件锁保护）
      ② 写 SQLite l0_conversations（FTS 即时；embedding 后台补写）
      ③ notifyConversation 通知调度器

【提取链（异步）】
notifyConversation（计数 +1）
  → 达阈值（warmup 1→2→4→8…→5）→ 入队 L1 任务
    未达阈值 → 设 L1_idle 定时器（默认 600s 兜底）
  → TimerScanner 每 500ms 扫描定时器分片 → 到期转任务入队列
  → PipelineWorker 竞争消费 → 抢分布式锁 → executeL1：
      按游标增量读 L0（过取20/处理10）→ 单次 LLM 调用完成
      「工作情境切分 + 团队工作记忆提取」→ 解析 → 两阶段去重 → 双写落库
  → L1 完成级联：计数清零 + L2 定时器提前到 max(now+10s, lastL2+900s)
  → L2 到期执行：agent 级锁下，沙箱化 LLM agent 增量改写 scene_blocks/*.md
      （把碎片工作记忆整合为工作方法场景块）
  → L2 完成级联：直接入队 L3 检查
  → L3：PersonaTrigger 五级条件判断（含累计 50 条记忆阈值），
      满足则 PersonaGenerator 增量重写 persona.md（Team Operating Doctrine）

【Skill 沉淀链（并行于 L0–L3）】
每轮对话 POST /v3/skill/conversation/add 推增量消息
  → 会话级缓冲累计（tool_call ≥10 或 ≥40KB 或显式触发）
  → 归档 archive + Redis 入队
  → SkillConversationExtractWorker 异步消费
  → SkillExtractor：LLM Review Agent 携带 6 个 skill 工具
      自主查库、判重、create/update/patch 直接落库（乐观锁）

【召回链（每次构建 prompt 前）】
before_prompt_build → performAutoRecall（5s 超时预算）：
  L3 Team Operating Doctrine 正文（稳定注入 system）
  + L2 场景导航（稳定注入 system）
  + L1 hybrid 检索结果（BM25+向量+RRF，动态前缀进 user prompt）
  + MEMORY_TOOLS_GUIDE（引导 Agent 按需深挖 L1/L0，每轮限 3 次）
```

---

## 3. L0 层：对话记录

**核心文件**：`MemoryCore/src/core/conversation/l0-recorder.ts`、`core/hooks/auto-capture.ts`、`utils/checkpoint.ts`

### 3.1 触发与记录

`recordConversation()`（l0-recorder.ts:93）由 `agent_end` hook 触发，直接接收 hook 上下文中的整段会话消息数组。每轮记录的消息字段为：`sessionKey, sessionId, userId, agentId, recordedAt, id, role, content, timestamp`。

### 3.2 双存储

- **主存储为按天分片的 JSONL**：`conversations/YYYY-MM-DD.jsonl`，所有 session 合并写入同一天的文件，`sessionKey` 是行内字段而非文件名；服务化模式经 `StorageAdapter` 写腾讯云 COS（AppendObject 原子追加）。
- **SQLite 是第二份索引副本**：`l0_conversations` 表 + `l0_vec`（vec0 向量虚表）+ `l0_fts`（FTS5 全文索引），供检索使用。为降低主路径延迟，FTS/元数据同步写入，embedding 以 fire-and-forget 后台任务补写。

### 3.3 增量捕获（防重复、防污染）

采用双重保护（l0-recorder.ts:118-169）：

1. **位置切片**：用 `before_prompt_build` 时刻缓存的 `originalUserMessageCount` 对消息数组切片，只取本轮新增消息（免疫网关重启后的时间戳漂移）；
2. **时间戳游标**：`afterTimestamp` 严格大于过滤作为兜底。

此外：用缓存的干净用户输入替换被召回注入污染的 user 消息；`sanitizeText` / `stripCodeBlocks` / `shouldCaptureL0` 过滤框架噪音与斜杠命令。

整个"读游标 → 写 L0 → 推进游标 + 计数 +1"在 `checkpoint.captureAtomically()` 的文件锁（可叠加 Redis 分布式锁）临界区内原子完成，防止并发 `agent_end` 重复记录。冷启动用进程启动时间作游标下限，避免首轮把全部历史灌入 L0。

**会话边界**：以 `sessionKey` 为单位组织；同一 sessionKey 下不同 `sessionId`（如 `/reset` 后）视为不同对话实例，L1 提取按 sessionId 分组独立处理。团队群聊场景下多人群聊消息同样经此路径落库，由 L1 的 work 模式 prompt 处理多人发言的归因问题。

---

## 4. 异步提取管线的编排

**核心文件**：`utils/pipeline-manager.ts`、`utils/stateful-pipeline-manager.ts`、`services/timer-scanner.ts`、`services/pipeline-worker.ts`、`services/worker-permit-pool.ts`、`utils/pipeline-factory.ts`、`core/state/`

系统有两套同构调度实现：单机内嵌模式 `MemoryPipelineManager`（进程内定时器 + 串行队列）与分布式服务模式 `StatefulPipelineManager`（状态全部外置到 Redis 状态后端）。

### 4.1 触发条件（`src/config.ts:555-569` 默认值）

| 参数 | 默认值 | 含义 |
| :--- | :--- | :--- |
| `pipeline.everyNConversations` | 5 | 每 5 轮对话触发一次 L1 提取 |
| `pipeline.enableWarmup` | true | 新会话阈值按 1→2→4→8→…→5 指数递增，让新会话更快建立记忆 |
| `pipeline.l1IdleTimeoutSeconds` | 600 | 未达阈值时的空闲兜底定时器 |
| `pipeline.l2DelayAfterL1Seconds` | 10 | L1 完成后延迟多久触发 L2 |
| `pipeline.l2MinIntervalSeconds` | 900 | 两次 L2 最小间隔（15 分钟） |
| `pipeline.l2MaxIntervalSeconds` | 3600 | L2 兜底轮询间隔（每小时） |
| `persona.triggerEveryN` | 50 | L3 触发的记忆累计条数阈值 |
| `persona.maxScenes` | 15 | L2 场景文件数量上限 |

L1 触发有三条路径：**阈值触发**（`notifyConversation` 中计数达到有效阈值立即入队）；**空闲兜底**（未达阈值则设/重置 L1_idle 定时器，到期入队）；**冲刷**（单会话结束 `flushSession()` 或进程关停 `destroy()` 时冲刷缓冲）。

### 4.2 调度与执行

- **TimerScanner**（timer-scanner.ts）：定时器存于 16 个全局分片 ZSET，member 格式 `{instanceId}\x00{sessionId}:{timerType}`，score 为到期时间戳。所有 pod 每 500ms 扫描全部分片，用 Lua 脚本原子 claim（ZRANGEBYSCORE+ZREM）保证跨 pod 不重复消费。timerType 决定任务优先级：L1→0、L2→1、L3→2。
- **PipelineWorker**（pipeline-worker.ts）：默认起 60 个消费协程，通过 Redis Consumer Group 竞争消费任务队列（轮询间隔 200ms）。执行流程：
  1. `permitPool.acquire()` 节点级并发限流（WorkerPermitPool 是 FIFO 信号量）；
  2. 抢分布式锁：**L1/flush 为 session 级锁，L2/L3 为 agent 级锁**（因 L2/L3 写共享 profiles 目录需互斥），锁 TTL 10 分钟、每 30s 续约，续约失败中止 LLM 调用；抢锁冲突按 200ms→600ms→1.8s→5s 指数退避，上限 15 次重入队；
  3. 分发到 `TaskExecutor.executeL1/L2/L3`；
  4. 失败重试：指数退避 5s/15s/45s，最多 3 次，超限进死信队列（并清理该会话的残留定时器）；
  5. 崩溃恢复：每 30s 扫描 XPENDING，认领空闲超 5 分钟的未 ACK 消息重新处理。

任务没有显式持久状态字段，状态隐含在队列流转中（入队 → 进 PEL 消费 → 持锁执行 → ACK/重入队/死信）。L1 幂等靠执行时检查 `conversation_count==0` 即跳过。

### 4.3 级联状态转换

- **L1 完成** → `conversation_count=0`、为每个 profile scope 置 L2 pending 标记、把 L2 定时器"只向前"推进到 `max(now+10s, lastL2+900s)`；
- **L2 完成** → 直接入队 L3 任务、重置计数、武装 `now+3600s` 的 L2 兜底定时器；
- **L3 检查** → 按触发条件决定是否生成 Team Operating Doctrine。

### 4.4 游标与 checkpoint

采用 **split-state 设计**（utils/checkpoint.ts:4-25）：`runner_states`（L0 捕获游标、L1 游标、上一情境名，CheckpointManager 独占写）与 `pipeline_states`（对话计数、warmup 阈值、L2 跟踪字段，PipelineManager 独占写）分离，互不覆盖；落盘于 `.metadata/checkpoint.json`，进程内异步锁 + tmp+rename 原子写，跨节点可注入 Redis 分布式锁。

### 4.5 Runner 构造（pipeline-factory.ts）

`createL1Runner` / `createL2Runner` / `createL3Runner` 是 standalone 运行时与 seed CLI 的共享工厂：

- **L1 Runner**：从 checkpoint 读 `last_l1_cursor`，按游标从 L0 **过取 20 行、只处理 10 行**（`L1_BATCH_QUERY=20`、`L1_BATCH_PROCESS=10`），同毫秒时间戳边界对齐防切批丢数据；返回恰好 20 行判定为积压（立即再跑一轮），10–20 行判定为还有余量（交给 idle 定时器延迟消费）；按 (userId, agentId, sessionId) 分组逐组提取。
- **L2 Runner**：以 `updatedAt` 游标增量读 L1 记录，按隔离 scope 分组后交给 `SceneExtractor`。
- **L3 Runner**：发现所有 profile scope，`PersonaTrigger.shouldGenerate()` 判断后交给 `PersonaGenerator`。

---

## 5. L1 层：团队共享工作记忆提取

**核心文件**：`core/prompts/l1-extraction.ts`（`EXTRACT_WORK_MEMORIES_SYSTEM_PROMPT`）、`core/record/l1-extractor.ts`、`core/record/l1-dedup.ts`、`core/prompts/l1-dedup.ts`、`core/record/l1-writer.ts`、`core/record/l1-reader.ts`

### 5.1 Prompt 设计：工作情境切分 + 团队记忆提取

work 模式的 system prompt 把 LLM 定义为"**专业的工作情境切分与团队共享记忆提取专家**"，分析多人工作消息、判断工作情境切换、提取可在项目团队内共享的结构化工作记忆。**单次 LLM 调用同时完成两个任务**：

**任务一：工作情境切分（Work Scene Segmentation）**

- **情境定义**：围绕同一个项目、任务、模块、需求、问题、决策、事故、客户场景或工作目标展开的一组消息；
- **继承条件**：新消息仍在延续上一个项目/任务/需求/问题/工作目标，则沿用上一情境；
- **切换条件**：讨论对象变成另一个项目/模块/需求/客户/Issue/PR/实验/事故/交付物；工作目标明显变化（如从"需求讨论"切到"上线排期"）；出现新的独立任务或问题排查线程；多个议题混排时拆分为多个情境；
- **命名规则**：围绕工作对象命名，推荐格式"**团队在围绕[项目/模块/议题]推进[目标活动]**"，约 30–50 字符、单句、全局唯一。例如"团队在围绕 Billing API 排查线上超时问题"。

**任务二：四类团队工作记忆提取**

| 类型 | 定义 | priority 分档 | metadata 建议 |
| :--- | :--- | :--- | :--- |
| `work_fact` | 项目/系统/业务/需求/决策/风险/约束/实验结果的事实性信息 | 90-100 关键决策、核心需求、长期约束、重要风险；70-89 有持续价值的一般事实；**<70 直接丢弃** | work_object、status、活动时间 |
| `work_task` | 需要后续执行/跟进/确认/交付的任务与责任分工 | 90-100 阻塞交付、有明确 deadline；70-89 有明确 owner 的一般任务；<70 丢弃 | owner、deadline、status（todo/doing/done/blocked/deferred/cancelled） |
| `work_method` | 团队形成的可复用方法、SOP、流程、原则、禁忌、设计思路、经验教训、Agent 行为规则——prompt 明确称其为"**团队长期工作记忆中最重要的类型之一**"：不只记录发生了什么，而是记录以后遇到类似任务应该怎么做 | 90-100 长期稳定、可跨任务复用、影响 Agent 行为的核心方法；70-89 有明显复用价值；<70 丢弃 | scope（project/team/module/agent/workflow）、method_type（sop/principle/constraint/anti_pattern/heuristic/evaluation_criterion） |
| `work_artifact` | 团队产生/引用/维护的工作资产：文档、PR/Issue、设计稿、实验报告、Prompt、会议纪要等 | 90-100 核心文档、关键 PR、上线相关资产；70-89 后续可能复用；<70 丢弃 | artifact_type、artifact_ref |

**Prompt 内置的七条提取原则**：

1. **面向工作协作**：提取的记忆应能帮助团队成员或 Agent 理解项目背景、接续任务、复用经验、避免重复错误；不提取寒暄、闲聊、临时情绪、一次性工具请求；
2. **面向团队共享**：内容默认会在团队内共享，不提取与工作无关的个人偏好、私人生活或敏感信息；
3. **独立完整**：每条记忆必须跳出当前对话仍能理解，包含清晰主体、工作对象、结论、状态或方法，禁用"这个、那个、上面说的"等依赖上下文的表达；
4. **准确归因**：某人提出的建议/担忧/判断 ≠ 团队决策；只有明确确认、拍板、采纳、执行安排才能写成确定结论；未确认内容应表达为"团队正在讨论…"、"某方案仍待确认…"；
5. **归纳合并**：强关联的多条消息合并为一条完整记忆，不把同一工作结论拆成碎片；但不同工作对象/任务/方法论分开提取；
6. **只从新消息提取**：背景消息只用于理解上下文、指代和时间，严禁从中新增记忆；`source_message_ids` 只能包含新消息 ID；
7. **AI/Agent 输出处理**：不把 AI 建议自动当成团队事实或决策；只有人类采纳/确认，或输出本身是明确的工具执行结果、交付物、实验结果时才可提取；被采纳为工作资产的 AI 草案可提取为 work_artifact 或 work_method。

**明确不提取**：问候寒暄玩笑、临时一次性请求（"这次帮我改下格式"）、未被采纳的 AI 建议、无后续价值的细节、个人私人信息。

**输出格式**：返回且仅返回 JSON 数组，每项是一个工作情境 `{scene_name, message_ids, memories:[{content, type, priority, source_message_ids, metadata}]}`；即使没有值得提取的记忆也要输出情境结构（memories 为空数组）。

**User prompt 构造**（`formatExtractionPrompt`）注入：【上一个情境】（跨批连续性）、【背景对话】（默认前 5 条，标注"严禁从中提取记忆"）、【待提取的新消息】（默认 10 条），每条消息格式 `[id] [role] [ISO时间戳]: content`——消息 ID 是后续溯源与归因的关键。

### 5.2 提取流程（l1-extractor.ts `extractL1Memories`）

1. **质量门**：`shouldExtractL1` 过滤纯符号、纯问号等低质消息（L0 宽进、L1 严进）；
2. **LLM 调用**：system prompt 可经 `composeMemorySystemPrompt` 叠加租户自定义记忆策略 prompt；timeout 180s；
3. **解析容错**：剥代码块、正则取数组、字段缺省、`repairExtractionJson` 修复弱模型的非法输出后重试，`normalizeType` 兼容旧枚举；
4. **限流**：每次每 session 最多 10 条；
5. **批量去重**（见 5.3），按 team/user/agent/session 隔离过滤防跨租户误判；
6. **写入 + 溯源**：逐条 `writeMemory`；同时记录 generation provenance 日志（input_refs=L0 消息 ID → output_refs=L1 记录 ID，即 `memory-generation-log` 模块）与提取率/延迟指标。

### 5.3 两阶段去重机制

既不是纯 LLM 判重，也不是纯向量相似度，而是**"向量/关键词粗召回 + 一次批量 LLM 精判"**：

**阶段一：候选召回（无 LLM）**，三级降级：

- Tier 1 向量召回：新记忆批量 embed，逐条取 topK=5 相似旧记忆；
- Tier 2 FTS5 BM25 关键词召回（取前 5）；
- 两者都不可用则跳过去重、全部直接 store。

**阶段二：批量 LLM 判定**（work 模式有专用判重 prompt）：把全部新记忆 + 跨新记忆去重后的统一候选池一次调用交给 LLM，任一环失败都 fallback 为全部 store。判重定义四种操作：

| 操作 | 语义 |
| :--- | :--- |
| `store` | 新增 |
| `skip` | 已有更好的旧记忆，丢弃新的 |
| `update` | 同一事实、新的更优，以新覆旧（版本号 +1） |
| `merge` | 信息互补不矛盾，合并为一条更完整记忆 |

支持**跨类型合并**和**多对多合并**（`target_ids` 是数组）；merge 后酌情提升 priority，`merged_timestamps` 取新旧时间戳并集保留完整时间线。解析层对 LLM 输出做多级防御（剥 fence、正则提取、清理控制字符、空 ID 视为幻觉丢弃、缺失决策补 store）。

### 5.4 存储与版本

- **双写策略**：JSONL（`records/YYYY-MM-DD.jsonl` 按日分片、append-only）是备份恢复的 source of truth；向量库（SQLite/腾讯云 VDB）是检索引擎。update/merge 时旧记录实时从向量库删除，JSONL 旧行由 cleaner 周期清理；向量写失败不阻塞 JSONL。
- **应用层 Schema**（`MemoryRecord`）：`id`、`content`、`type`、`priority`（0-100）、`scene_name`、`source_message_ids`、`metadata`、`timestamps[]`（merge 历史时间线）、`version`（update/merge 递增）、租户三维隔离 `teamId/userId/agentId`。
- **SQLite Schema**：`l1_records` 表 + `l1_vec`（vec0，cosine）+ `l1_fts`（FTS5，结巴分词），大量复合索引（如 `(session_id, updated_time)` 供 L2 增量聚合查询）。

---

## 6. L2 层：工作方法场景块

**核心文件**：`core/scene/scene-extractor.ts`、`scene-format.ts`、`scene-index.ts`、`scene-navigation.ts`、`filename-normalizer.ts`、`core/prompts/scene-extraction.ts`（`buildWorkSceneSystemPrompt`）

### 6.1 输入与触发

- **输入**：`createL2Runner` 以 `updatedAt` 游标增量读 L1 记录（无新记录则 skip），整批以 `{content, created_at, id}` JSON 交给 LLM。**L1 的 scene_name 不参与 L2 聚合**——场景归属完全由 L2 的 LLM 自主决定；checkpoint 里的 `last_scene_name` 只用于 L1 抽取的跨批连续性。
- **触发**：L1 完成后级联推进 L2 定时器，`max(now+10s, lastL2+900s)`；另有每小时兜底轮询；定时器采用"只可提前"策略。

### 6.2 Prompt 设计：团队工作方法记忆整合架构师

work 模式的 L2 prompt 将 LLM 定义为"**Team Work Method Memory Consolidation Architect**"，核心要求：

- **目标不是复述项目流水账**，而是把碎片化 L1 工作记忆整合成可复用的工作方法场景块，从中提炼五类内容：**SOP**（以后类似工作按什么流程做）、**判断逻辑**（团队为什么这样取舍）、**禁忌**（哪些做法不应再出现）、**原则**（哪些约束和标准应长期遵守）、**经验**（哪些方法可被 Agent 和团队复用）；
- 事实、任务、状态可以记录，但只用于说明方法的**来源、适用条件和上下文**；
- **明确禁止**：写成项目日报、聊天摘要、任务清单、个人画像；禁止简单追加列表、禁止创建 BATCH/REPORT/SUMMARY 类批处理汇总文件。

**通用工程约束**：

- **策略优先级 UPDATE > MERGE > CREATE**："默认策略是 UPDATE"；CREATE 前必须 read 至少 2 个最相似场景验证确实无法融入，且每批最多新建 1 个；
- **容量分级预警**（上限 15 个场景）：红色（≥15）强制先 MERGE 并删除被合并旧文件；橙色（=14）只准 UPDATE；黄色（≥12）优先 UPDATE/MERGE；
- **work 模式的合并优先级**：工作对象高度重叠 > 同一项目链路 > 同一方法体系 > 热度最低场景；
- **热度规则**：新建 heat=1，更新 +1，合并取和 +1；
- **冲突处理**：新旧记忆矛盾时记入"演化记录"或"待确认问题"，不直接覆盖。

**场景文件模板（work 模式）**：META 头 + 以下章节，每个文件 ≤1500 字符：

```text
-----META-START-----
created / updated / summary(30-40词, 聚焦可复用方法) / heat
-----META-END-----
## 工作场景      ← 适用于哪类项目/任务/方法体系，可复用在哪里
## 适用条件      ← 项目阶段、任务类型、风险背景、Agent 执行场景
## 核心 SOP      ← 最重要部分：可复用流程/步骤/协作方式，每条附判断依据
## 判断逻辑      ← 决策标准、优先级规则、评价口径、取舍原因
## 禁忌与反模式  ← 应避免的做法、易误判处、失败模式与正确替代
## 关键事实依据  ← 可为空；只保留支撑 SOP 与判断逻辑的关键事实
## 相关任务与资产 ← 可为空；待跟进任务（owner/deadline）与文档/PR/Prompt 资产
## 演化记录      ← 可为空；只记方法/规则/禁忌的变化，不记普通进展
## 待确认问题    ← 可为空；影响 SOP/边界/判断标准的未决问题
```

**L3 联动信号（work 模式触发条件）**：跨场景复用的 SOP/禁忌/原则形成稳定共识、项目级规则升级为团队级规则、关键决策影响多个场景、或某工作方法/Agent 行为规则应沉淀到 L3 时，LLM 在文本输出中写 `[PERSONA_UPDATE_REQUEST]reason[/...]` 标记，由工程侧解析后写入 checkpoint，成为 L3 的 P1 触发源。

### 6.3 沙箱化 LLM Agent 八阶段执行流程

L2 不是简单的"LLM 生成文本"，而是让 LLM 以**带工具的 agent 身份在 `scene_blocks/` 沙箱目录内直接读写场景文件**（LLM 物理上看不到 checkpoint、scene_index、persona.md）：

1. **备份**：本地模式备份 scene_blocks/（保留 10 份）；
2. **读索引**：构建场景摘要（含容量计数 `当前场景总数：N / 15`、热度、summary）；
3. **分级容量预警**：按红/橙/黄分级注入 prompt；
4. **LLM 执行**：timeout 300s，LLM 用 read/write/edit 工具直接改写场景文件（read 白名单只准读"已有场景文件清单"），失败则从备份恢复；
5. **软删清理**：LLM 无删除权限，删除靠写 `[DELETED]` 标记（禁止空字符串、禁止 ARCHIVE/CONSOLIDATED 等替代标记）；工程侧清理空文件、标记文件与"仅 META 无正文"文件；
6. **文件名归一化**：空白转 `-`、删标点、保留 CJK，冲突加 `-2/-3` 后缀（prompt 同时强制命名规范：仅字母/数字/CJK/`-_`，多词用 `-` 连接）；
7. **重建索引** `syncSceneIndex` + 更新 persona.md 尾部 Scene Navigation；
8. **解析带外信号**：`parsePersonaUpdateSignal` 解析 `[PERSONA_UPDATE_REQUEST]`。

### 6.4 文件格式与索引

场景文件为 **Markdown + META 头**；`scene_index.json` 由工程侧扫描全部 .md 重建（LLM 沙箱不可见）；**场景导航**按 heat 降序生成 "🗺️ Scene Navigation" 段落追加到 persona.md 末尾，每条目给绝对路径 + 热度分级（🔥 50/100/200/500/1000）+ summary，提示 Agent 按需加载——即**渐进式披露**。

---

## 7. L3 层：Team Operating Doctrine

**核心文件**：`core/persona/persona-trigger.ts`、`persona-generator.ts`、`core/prompts/persona-generation.ts`（`TEAM_MEMORY_SYSTEM_PROMPT`）、`core/profile/profile-sync.ts`

### 7.1 触发条件（事件驱动，五级优先级）

评估时机是每次 L2 完成后（L3 全局串行队列）：

| 优先级 | 条件 |
| :--- | :--- |
| P1 | L2 的 LLM 主动请求（`request_persona_update` 标记） |
| P2 | 冷启动：已处理过场景、从未生成过且存在场景文件 |
| P2.5 | 恢复：persona.md 正文丢失/为空 |
| P3 | 首次 Scene Block 提取完成 |
| P4 | **计数阈值：自上次生成后累计 50 条新记忆**（`persona.triggerEveryN`，每次 L1 抽取完成累加，生成成功后清零） |

### 7.2 生成流程（`generateLocalPersona`）

读现有 persona.md（剥导航）→ 读场景索引，筛出 `updated > last_persona_time` 的**变化场景**（时间不可解析时保守视为变化）→ 预加载变化场景完整原文（含 META）→ 无变化且已有 persona 则跳过 → 判定 first/incremental 模式 → 备份（3 份）→ LLM 运行（timeout 180s，只准写 persona.md）→ 读回、转义、剥导航 → **工程侧重新追加最新 Scene Navigation** → 写回。

**输入来源是 L2 而非 L1**：变化场景全文 + 场景统计 + 既有 Doctrine。产物经 profile-sync 作为 `type:"l3"` 的 ProfileRecord 同步到 VDB/COS。隔离粒度上 L2/L3 有意忽略 userId/sessionId，按 **team+agent** 级共享，使团队记忆跨会话、跨成员累积。

### 7.3 Prompt 设计：Team Operating Doctrine Architect

work 模式的 L3 prompt 明确定位：这份文档**不是项目总结、进度记录、场景索引或事实汇总**，而是团队在各种工作场合都可复用的 Operating Doctrine——帮助 Agent 在面对新任务时知道**如何判断、如何执行、如何避免错误**。

**六大提炼维度**：

| 维度 | 含义 |
| :--- | :--- |
| SOP | 以后类似任务应该按什么流程做 |
| Principle | 团队长期遵守的工作原则 |
| Decision Logic | 遇到取舍时按什么标准判断 |
| Boundary | 哪些事不能做、哪些内容不能自动化 |
| Anti-pattern | 哪些做法会导致错误、污染记忆、降低质量 |
| Agent Rule | Agent 执行任务、更新记忆、生成结果时应遵守的规则 |

项目事实、任务状态、资产名称只作为证据来源，只有能抽象成跨场景规则时才写入。

**写入前五条过滤标准**（任一否定则优先不写入）：通用性（是否适用于多个项目/场合）、完整性（脱离原项目是否仍可理解）、可执行性（Agent 能否据此改变行为）、稳定性（是否长期有效而非一次性状态）、精炼性（能否更短/能否合并进已有原则）。

**增量更新策略**（持续压缩，保持少而准，不把每次变化追加为新条目）：**强化**（新场景佐证已有原则，压缩进原句或不改）/ **补充**（新的通用 SOP、禁忌、判断逻辑或 Agent 规则）/ **修正**（旧原则被新证据推翻或边界变清晰）/ **重构**（文档变散、变长、变项目化时整体压缩重写）/ **不改**（新增只有项目状态或低层事实时不更新 L3）。

**严格禁止清单**：超过 **1200 字**；项目化碎片（"项目 v2 要优化"这类只有特定项目上下文才懂的内容）；流水账；低层事实堆积（项目名/版本号/PR/Issue 名除非代表可复用范式否则不进 L3）；语义不完整（每条原则必须脱离原项目也能理解）；个人画像化（成员性格、个人偏好、情绪判断）；无场景证据的过度推测。

**输出模板**：

```text
# Team Operating Doctrine
> Operating Thesis: [一句话概括团队最核心的工作方法或 Agent 执行原则]
## Core Principles          ← 跨场景稳定成立的高层原则
## Reusable SOPs            ← 能被反复执行的流程（触发条件→步骤→验收标准）
## Decision Logic           ← 当[场景]时优先[A]而非[B]，因为[原因]
## Boundaries & Anti-patterns ← 不要[错误做法]；应改为[推荐做法]，因为[原因]
## Agent Rules              ← Agent 应[行为规则]，避免[风险]
> 最后更新 / 来源场景数 / 记忆总数
```

---

## 8. Skill：可复用经验的沉淀

**核心文件**：`core/skill/`（skill-extractor.ts、skill-core.ts、skill-versioning.ts、skill-tools.ts、skill-store.ts、conversation-add/、prompts/skill-review-prompt.ts 等）

### 8.1 触发路径

不在对话进行中实时抽取，而是"先缓冲、达阈值归档、异步抽取"：

**自动阈值触发（主路径）**：上层 Agent/proxy 每轮对话结束后调 `POST /v3/skill/conversation/add` 推增量消息，累计到 session 级缓冲 `data-current.jsonl`。默认阈值：

- `toolCallThreshold = 10`（只计 tool_call，不计配对的 tool_result）；
- `bytesThreshold = 40KB`；
- 单次请求 ≥40KB 走压缩路径并必然触发归档。

**显式触发（direct-trigger）**：`POST /v3/skill/extract` 由主 Agent 显式发起（对应用户命令），不做阈值判定，可携带 `reason`（抽取提示，≤500 字）和 `max_iterations`。

**归档与消费链路**：先写 archive 文件（`data-<ts>.jsonl`）→ 再在同一互斥临界区内追加任务清单并 Redis 入队（防止 worker 抢跑读到空 archive）；`SkillConversationExtractWorker` 出队后抢 agent 级 extract-lock（TTL 600s）→ 调 `extractor.extract` → 落账 → 删任务。失败分 transient（无限重试）/ permanent（累计 3 次进 DLQ）。

### 8.2 提取流程：LLM Review Agent 自主读写库

1. **Transcript 构造**：把归档消息（role ∈ user/assistant/tool_call/tool_result）串成 transcript，刻意用 `<<past-user>>` 等非自然标签包裹并以 `<<end-of-transcript>>` 收尾——打破模型把 transcript 尾部当"该我续写"的角色捕获倾向；超长时头尾截断（head 8000 / tail 32000 字符）。
2. **前缀注入已有 skill（防重复创建）**：总数 ≤20 全量铺开；否则先花一次轻量 LLM 调用生成 2-5 个 BM25 关键词，再预检索相关 skill 注入；失败退化为最近更新 top-N。
3. **Review Prompt（v2 哲学）**：`SKILL_REVIEW_PROMPT` 从 v1 的"普遍性门槛 + 四维评分"转向 **"when in doubt, capture"（宁滥勿缺）**。三类 skill 等价：**SOP 型**（可复用流程）、**Background 型**（持久领域/系统背景）、**Preference 型**（用户/团队操作约定）。
4. **输出契约**：只有两种形态——若干 tool call + 一行总结，或精确回复 `Nothing to save.`。
5. **推荐 SKILL.md 结构**：frontmatter（name、description 必填）+ When to use / When not to use / Required inputs / Workflow / Decision rules / Output format / Validation / Pitfalls / Supporting files——即**触发边界、执行步骤、验证规则**都以章节形式在 prompt 中要求。
6. **负面清单**：密钥凭据、裸日志、一次性瞬态状态、与已有 skill 完全重复的一律不抓；具体 ID/URL/分支应参数化为占位符。
7. **工作顺序**：先 `skill_list` 看全库 → `skill_view` 细读 → 决定 create / update / patch / files_write；所有写操作要求 `expected_version` 乐观锁。

Review Agent 通过 6 个工具（skill_list / skill_view / skill_create / skill_update / skill_patch / skill_files_write）**直接写库**；不提供 delete/files_remove——抽取流程不能销毁团队 skill。LLM 迭代上限默认 16。

### 8.3 存储、版本与权限

- **存储**：每个 `(skill_id, version)` 是一行不可变快照；SQLite 为 `skills` 主表 + `skill_fts`（FTS5，索引 name/description/content）+ 可选 vec0；资源文件经 `SkillResourceStore` 落 local/COS（单资源 ≤5MB，整 skill ≤50MB，默认不允许可执行文件）。skill_id 为 `skl-` + 12 位 base62 CSPRNG。
- **版本管理**：创建是跨三系统的"顺序+补偿"伪事务（先写 COS → 写 skill DB → 登记资产，任一失败反向清理）；`appendNextVersion` 先拷贝旧版本目录再 apply 变更，内容哈希未变且无资源变更时幂等返回；TTL 清理保护最近 3 个非 head 版本。
- **权限**：team 内 skill 共享；`assertOwner`（team_id + owner_agent_id 双匹配）、`assertTeamMatch`（不匹配按 404 返回防存在性侧信道）、`assertVersionFresh`（乐观锁校验）。格式校验：name ≤64 且 `^[a-z0-9][a-z0-9-]*$`，description ≤1024，body ≤50,000 字符。
- **召回配装**：skill listing 注入 Agent 上下文时按 `char_budget`（默认 8000 字符）截断、topK 默认 20；检索走 FTS5 BM25 + snippet。（`skill-fast-path.ts` 定义了名称子串命中的 <5ms 快速通道，但当前未接入。）

---

## 9. 记忆召回与注入

**核心文件**：`core/hooks/auto-recall.ts`、`core/memory-prompt/`、`store/sqlite.ts`、`store/search-utils.ts`

### 9.1 时机与分层策略

召回发生在**构建 prompt 之前**（OpenClaw `before_prompt_build` / Hermes `prefetch()` / Gateway `/recall`），整体用 `Promise.race` 限制在 **5 秒**内，超时返回结构化错误而非阻塞对话。

分层注入策略（对应 README 的设计）：

| 层 | 注入方式 | 目的 |
| :--- | :--- | :--- |
| L3 Team Operating Doctrine | 全量注入（剥导航），进 system prompt 的稳定部分 | Agent 带着团队原则开工 |
| L2 场景导航 | 完整场景目录 + 热度 + 摘要注入，由 Agent 自行判断相关性按需读取文件 | 渐进式披露工作方法 |
| L1 相关记忆 | 对当前 userText 做 hybrid 检索（默认），maxResults=5、scoreThreshold=0.3，动态前缀进 user prompt | 精确召回具体事实/任务 |
| L1/L0 深挖 | 注入块尾部附 `MEMORY_TOOLS_GUIDE`，引导 Agent 主动调 `tdai_memory_search`（L1）/ `tdai_conversation_search`（L0），**每轮合计最多 3 次** | 注入不足时按需深挖 |

为优化 prompt cache，结果拆为稳定部分 `appendSystemContext`（persona + `<scene-navigation>` + tools guide，进 system）和动态部分 `prependContext`（`<relevant-memories>`，前缀进 user prompt）。字符预算由 `applyRecallBudget` 执行（`maxCharsPerMemory` / `maxTotalRecallChars`，默认不限制），截断时提示可用工具查看详情。

### 9.2 检索底座：BM25 + 向量 + RRF

- **BM25（SQLite FTS5）**：jieba `cutForSearch` 分词 + 去中文停用词，token OR 连接；负 rank 归一到 0-1 分数。
- **向量**：sqlite-vec 的 vec0 KNN，`score = 1 - distance`，跳过零向量占位。
- **RRF 融合**：hybrid 模式并行跑 FTS5 与向量（各取 maxResults×3 候选），按 `1/(60+rank+1)` 计算、同记录跨表求和再排序（通用实现 `rrfMerge` 的 RRF_K=18，召回路径用 60）。
- **腾讯云 VDB 短路**：若后端支持 nativeHybridSearch，直接一次服务端 dense+sparse+RRF rerank 调用。
- **小语料修正**：文档集很小时绝对分不可信，信任 MATCH 排序直接返回；hybrid 路径不应用分数阈值，靠 RRF 排序。

### 9.3 自定义记忆策略 prompt

`core/memory-prompt/` 提供租户自定义记忆策略的能力：按 **agent > team > instance** 优先级解析每层（l1/l2/l3）绑定的 active prompt，由 `composeMemorySystemPrompt` 追加到提取/生成的 system prompt。守卫机制保证自定义内容**只能调整关注点与归纳策略，不得修改固定输出协议**（L1 JSON 格式、L2 Scene Markdown、L3 persona.md 协议）。SDK（sdk/memory-core 的 Python/TypeScript v3 客户端）暴露了对应的管理 API；`memory-generation-log` 则记录每条记忆从 L0 消息到 L1 记录、再到 L2/L3 的生成溯源（input_refs → output_refs），支撑"这条记忆从哪来"的审计需求。

---

## 10. 设计亮点小结（work 模式视角）

1. **从流水账到方法论的逐层抽象**：L0 全量原始对话 → L1 结构化工作记忆（四类、宁缺毋滥、<70 分丢弃）→ L2 工作方法场景块（SOP/判断逻辑/禁忌/原则/经验，≤15 个、UPDATE-first）→ L3 Team Operating Doctrine（≤1200 字、六维度、五条过滤标准），每层 token 密度递增、项目细节递减、可复用性递增。
2. **团队记忆的归因纪律**：prompt 把"个人建议 ≠ 团队决策"、"AI 输出须人类采纳"、"只提取适合团队共享的内容"写成硬规则，从源头避免群聊记忆污染。
3. **全链路事件驱动 + 多级兜底**：阈值触发 + 空闲定时器 + 定时轮询三重保障；每一处 LLM 失败都有 fallback（全部 store / 跳过去重 / 空召回），系统不会因单点 LLM 故障卡死。
4. **沙箱化 LLM Agent 做 L2**：让 LLM 带工具直接改写场景文件，但物理隔离敏感元数据、无删除权限（软删标记）、工程侧负责索引/导航/命名归一化/备份回滚——"LLM 生产、工程兜底"的分工贯穿始终。
5. **去重是记忆系统的核心难题**：两阶段设计（向量/FTS 粗召回 + 批量 LLM 精判），store/skip/update/merge 四操作支持跨类型、多对多合并，配合版本号与时间戳并集保留演化历史。
6. **L3 的"持续压缩"哲学**：不追加、求合并，强化/补充/修正/重构/不改五种增量策略，配合五条写入前过滤，保证 Doctrine 始终少而准。
7. **召回也分层**：L3 Doctrine + L2 场景导航稳定注入进 system（利于 prompt cache），L1 动态检索进 user 前缀，L0 保留工具通道按需深挖——用"少拿但拿对"对抗上下文膨胀。
8. **Skill 沉淀"宁滥勿缺 + 乐观锁"**：v2 哲学降低捕获门槛，靠版本快照、乐观锁、不可删除、team 内共享保证写安全与资产积累。

---

## 附录 A：关键配置常量速查

| 常量 | 默认值 | 位置 |
| :--- | :--- | :--- |
| L1 触发对话数阈值 | 5（warmup 1→2→4→8…） | `config.ts:563` |
| L1 空闲兜底 | 600s | `config.ts:565` |
| L1 单批处理/查询 | 10 / 20 条 | `pipeline-factory.ts:87-88` |
| L1 单会话单次上限 | 10 条记忆 | `l1-extractor.ts` |
| L1 priority 分档（work） | 90-100 / 70-89 / <70 丢弃 | `l1-extraction.ts` |
| L2 延迟/最小间隔/兜底间隔 | 10s / 900s / 3600s | `config.ts:566-568` |
| L2 场景数量上限 | 15 | `config.ts` `persona.maxScenes` |
| L2 单文件长度 | ≤1500 字符 | `scene-extraction.ts` |
| L3 触发记忆累计阈值 | 50 条 | `config.ts:555` |
| L3 Doctrine 长度 | ≤1200 字（work 模式） | `persona-generation.ts` |
| 召回超时 | 5000ms | `auto-recall.ts:108` |
| 召回条数/分数阈值 | 5 条 / 0.3 | `auto-recall.ts:458-459` |
| 记忆工具每轮限次 | 3 次 | `auto-recall.ts` MEMORY_TOOLS_GUIDE |
| Skill tool_call 阈值 | 10 次 | `add-handler.ts:101` |
| Skill 字节阈值 | 40KB | `add-handler.ts:101` |
| Skill 提取迭代上限 | 16 | `skill-extractor.ts:113` |
| Worker 并发协程 | 60 | `pipeline-worker.ts` |

## 附录 B：关键源码文件索引

| 领域 | 文件 |
| :--- | :--- |
| L0 记录 | `MemoryCore/src/core/conversation/l0-recorder.ts` |
| 捕获/召回 Hook | `MemoryCore/src/core/hooks/auto-capture.ts`、`auto-recall.ts` |
| 管线编排 | `MemoryCore/src/utils/pipeline-manager.ts`、`stateful-pipeline-manager.ts`、`pipeline-factory.ts`、`checkpoint.ts` |
| 调度执行 | `MemoryCore/src/services/pipeline-worker.ts`、`timer-scanner.ts`、`worker-permit-pool.ts` |
| L1 提取 | `MemoryCore/src/core/record/l1-extractor.ts`、`l1-writer.ts`、`l1-reader.ts`、`l1-dedup.ts` |
| L1 Prompt | `MemoryCore/src/core/prompts/l1-extraction.ts`（EXTRACT_WORK_MEMORIES_SYSTEM_PROMPT）、`l1-dedup.ts` |
| L2 场景 | `MemoryCore/src/core/scene/*.ts`、`core/prompts/scene-extraction.ts`（buildWorkSceneSystemPrompt） |
| L3 Doctrine | `MemoryCore/src/core/persona/persona-generator.ts`、`persona-trigger.ts`、`core/prompts/persona-generation.ts`（TEAM_MEMORY_SYSTEM_PROMPT） |
| L2/L3 同步 | `MemoryCore/src/core/profile/profile-sync.ts` |
| Skill | `MemoryCore/src/core/skill/`（skill-extractor.ts、skill-core.ts、skill-versioning.ts、skill-tools.ts、conversation-add/、prompts/skill-review-prompt.ts） |
| 检索底座 | `MemoryCore/src/store/sqlite.ts`、`store/search-utils.ts` |
| 状态后端 | `MemoryCore/src/core/state/`（IStateBackend、LocalStateBackend、Redis） |
| 存储路径 | `MemoryCore/src/core/storage/types.ts`（StoragePaths） |
| 溯源日志 | `MemoryCore/src/core/memory-generation-log/` |
| 自定义记忆策略 | `MemoryCore/src/core/memory-prompt/`（composer.ts、resolver.ts） |
