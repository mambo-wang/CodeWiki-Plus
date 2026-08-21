# CodeWiki-CN 优化 Roadmap

> 综合来源：
> - 高德技术《CodeWiki: 为 LLM 自动生成代码知识库的工程实践》(2026-07-22)
> - 阿里技术《分解一座冰山：后端系统「AI 知识库体系」建设实践》
>
> 编制日期：2026-07-26
> 状态：规划中

---

## 战略定位演进

CodeWiki-CN 当前定位是"代码文档生成器"——从 AST 自动生成模块化 Wiki。两篇文章共同指向一个更大的目标：**AI Coding 知识平台**——不仅让 LLM 看懂代码，还要让它在修改代码前理解并遵守业务约束、做出正确的工程判断。

演进路径：代码文档生成器 → 可信知识生成器 → AI Coding 知识平台

---

## Phase 1：知识表达与消费优化（Prompt & Schema 层）

> 目标：零/低代码改动，通过 prompt 工程和 schema 调整立即提升知识质量和 LLM 消费效率。
> 预计周期：1-2 周
> 涉及文件：prompt_template.py, schema.yaml, wiki_search.py, knowledge_loop.py

### 1.1 Evidence-Based 业务断言（反幻觉）

**问题：** 当前 prompt 是通用"生成文档"指令，LLM 输出的业务描述无法区分"有代码依据的事实"和"推测"。

**方案：**
- 在 prompt_template.py 中新增 `BUSINESS_RULES_EXTRACTION` 指令块
- 要求每条业务规则附带 evidence（quote + reason）和 confidence 评分
- 无证据的断言标记为 `[candidate]`
- 在 Wiki 页面中用结构化区块呈现证据

**验收标准：**
- 生成的模块文档中，业务约束段落包含代码引用和置信度
- lint_wiki 新增检查：无证据断言比例超过 30% 报 warning

**来源：** 高德 CodeWiki §3.4

---

### 1.2 组件约束目录表（交叉索引格式）

**问题：** Wiki 页面面向人类阅读优化，LLM 消费时要么读整页（浪费 token），要么只看 snippet（遗漏关键约束）。

**方案：**
- schema.yaml 的 required_sections 新增 `component_constraint_index` 为必选章节
- prompt 要求每个模块页面在架构概述之后、详情之前，输出"组件约束目录表"：

```markdown
## 组件约束目录
| 组件 | 约束数 | 风险点 | 摘要 |
|------|--------|--------|------|
| OrderService.createOrder | 6 | 2 | 库存校验、金额校验、幂等 |
| OrderService.cancel | 4 | 1 | 状态机流转、退款触发 |
```

- 按约束密度降序排列
- 每组件限额：最多 3 条约束 + 2 条风险（超出标注"还有 N 条"）

**验收标准：**
- 新生成的模块文档包含目录表章节
- 目录表控制在 30 行以内

**来源：** 高德 CodeWiki §3.5

---

### 1.3 渐进式消费协议（Wiki-Reading Mode）

**问题：** query_wiki 是单次搜索返回 snippet，没有"先概览→再定位→后精读"的渐进结构。LLM Agent 使用 CodeWiki 时 token 效率低。

**方案：**
- query_wiki 新增 `mode` 参数：
  - `mode=overview`：返回 overview.md 摘要 + 匹配页面的 frontmatter（title/type/tags）
  - `mode=directory`：返回匹配页面的"组件约束目录表"章节
  - `mode=detail`：返回指定页面的指定章节完整内容（需传 page + section 参数）
  - 默认（不传 mode）：保持现有 BM25 snippet 行为，向后兼容
- 在 MCP instructions 中写入消费协议提示
- 新增 wiki-reading skill 或在 codewiki-wiki-generator skill 中增加消费协议章节

**验收标准：**
- query_wiki(mode=overview) 返回 < 500 token
- query_wiki(mode=directory) 返回 < 800 token
- 消费协议文档化在 skill 或 instructions 中

**来源：** 高德 CodeWiki §4.3

---

### 1.4 知识来源标注（Source Type）

**问题：** query_wiki 混合返回自动生成文档和人工笔记，LLM 无法判断信息的可信度和时效性。

**方案：**
- query_wiki 返回结果中为每条添加 `source_type` 字段：
  - `auto_generated`：来自 wiki/ 目录
  - `developer_note`：来自 notes/ 目录
  - `ingested_source`：来自 ingest_source 摄入的外部文档
- Wiki 页面 frontmatter 中记录 `generated_from`（代码版本 SHA）和 `last_verified`
- 消费协议中指导 LLM：auto_generated 可直接引用；developer_note 需检查时效性

**验收标准：**
- query_wiki 每条结果包含 source_type
- 新生成的 Wiki 页面 frontmatter 包含 generated_from

**来源：** 高德 CodeWiki §4.3 + 阿里知识库 §6

---

## Phase 2：生成引擎增强（Engine 层）

> 目标：降低生成成本、提升增量效率、改善上下文精度。
> 预计周期：3-4 周
> 涉及文件：analysis.py, cache.py, cluster_modules.py, dependency_analyzer/

### 2.1 规则引擎路由（Boilerplate vs Business）

**问题：** 所有代码组件一视同仁进入 LLM 流程，DTO/VO/Config/Mapper 消耗大量 token 生成低价值描述。

**方案：**
- 在组件解析阶段为每个组件添加 `code_category` 标签：
  - `boilerplate`：DTO, VO, Entity, Config, Mapper, Repository（类名后缀 + 注解）
  - `business`：Service, Controller, Job, Consumer, Handler, Manager
  - `infra`：Util, Helper, Factory, Builder, Interceptor, Filter
- schema.yaml 新增 `code_routing` 配置节，支持用户自定义路由规则
- boilerplate 组件不注入完整源码，只注入签名+字段列表，由模板生成描述
- business 组件走完整 LLM 流程

**验收标准：**
- 典型 Java/Spring 仓库 LLM 调用量减少 30%+
- boilerplate 组件文档质量稳定（模板化输出）
- 用户可通过 schema.yaml 自定义路由规则

**来源：** 高德 CodeWiki §3.4

---

### 2.2 知识飞轮与状态流转（[suggest-wiki] 机制）

**问题：** ingest_note 无门槛，LLM 自主决定沉淀内容，可能写入错误或重复知识。缺乏"研发确认"环节。

**方案：**
- notes/ 目录引入状态机制（frontmatter 中 `status` 字段）：
  - `candidate`：LLM 自动沉淀，待研发确认
  - `confirmed`：研发确认后升级为正式领域知识
  - `rejected`：研发否决，保留记录但不再被 query_wiki 返回
- 新增 MCP 工具：`confirm_note(note_id)` / `reject_note(note_id, reason)`
- query_wiki 默认只返回 confirmed 笔记；candidate 标注"[未确认]"
- Agent 工作流中，LLM 发现的跨功能约束写入 candidate + [suggest-wiki] 标注
- 与 health_score 联动：candidate 笔记 severity=info（扣 1 分），confirmed 后不扣分

**验收标准：**
- ingest_note 写入的笔记默认为 candidate 状态
- query_wiki 结果中 candidate 笔记有明确标注
- confirm/reject 工具可用

**来源：** 高德 CodeWiki §4.4 + 阿里知识库 §6

---

### 2.3 BFS 调用图上下文组装

**问题：** prompt 中注入的"core components"基于模块聚类，可能包含同模块无关组件，遗漏跨模块强依赖方法。

**方案：**
- 在 get_prompt / generate_docs 流程中增加"调用图上下文扩展"步骤：
  1. 确定目标组件集合
  2. 在 SQLite 依赖图上做 1-2 跳 BFS
  3. 关联组件只注入签名+摘要（控制 token）
  4. 在 prompt 中标注为 `<CALL_CONTEXT>`，与 `<CORE_COMPONENTS>` 区分
- 新增配置项控制 BFS 深度和 token 预算

**验收标准：**
- 生成的文档中跨模块关系描述准确性提升（人工抽检）
- CALL_CONTEXT 不超过总 prompt token 的 20%

**来源：** 高德 CodeWiki §3.4

---

### 2.4 方法级增量检测（Merkle 思路）

**问题：** 当前增量检测是文件级（Git diff + SHA256），改一个方法整个文件重新处理；上层摘要刷新依赖 Agent 手动判断。

**方案：**
- SQLite cache 新增 `code_unit_hash` 列，存储每个组件的内容哈希
- detect_changes 增加第二层：文件变化后逐组件比较哈希，只标记真正变化的组件为 stale
- 级联失效：组件 stale → 标记所属模块 Wiki 页面为 `needs_refresh`
- query_wiki 返回结果时可标注"此页面可能已过期（N 个组件已变更）"

**验收标准：**
- 单方法修改不触发整个文件的组件重新处理
- 受影响的 Wiki 页面被自动标记为 needs_refresh
- 大仓库（1000+ 文件）增量分析时间减少 50%+

**来源：** 高德 CodeWiki §3.2

---

## Phase 3：知识内容扩展（Content 层）

> 目标：从"代码即事实"扩展到业务约束、系统策略、验证标准等代码外的知识。
> 预计周期：4-6 周
> 涉及文件：page_router.py, schema.yaml, 新增 MCP 工具

### 3.1 系统约束 / Policy

**问题：** CodeWiki-CN 能描述"API 做了什么"，但无法表达"API 的 field X 绝对不能删除"。缺乏行为约束层。

**方案：**
- schema.yaml 新增 `policies` 配置节，支持结构化约束规则（YAML 格式）：
  ```yaml
  policies:
    - scope: "api/public_api"
      rules:
        - field: "order_id"
          constraint: "never_remove"
          reason: "下游离线对账依赖"
    - scope: "infrastructure/database"
      rules:
        - table: "orders"
          constraint: "add_column_only"
  ```
- 新增 MCP 工具 `ingest_policy` / `query_policy`
- page_router 新增 `wiki/policies/` 目录
- lint_wiki 新增检查：高风险模块是否有对应 policy
- 消费协议中：policy 作为"红线"优先注入 Agent 上下文

**验收标准：**
- 支持 YAML 格式定义系统约束
- query_wiki(mode=overview) 时自动返回相关 policy 摘要
- lint_wiki 报告缺少 policy 的高风险模块

**来源：** 阿里知识库 §2

---

### 3.2 业务层知识（Business Layer）

**问题：** CodeWiki-CN 完全没有业务层，无法回答"退款体验优化涉及哪些服务"这类业务驱动的问题。

**方案：**
- repowiki 目录新增 `wiki/business/` 子目录，包含：
  - `meta/`：业务元语（概念定义、领域术语）
  - `scenarios/`：业务场景→技术链路映射
  - `practices/`：历史设计决策（为什么这样做）
  - `principles/`：跨场景设计原则
- 新增 MCP 工具 `ingest_business(type, content, relations)`
- page_router 新增 `type: business_meta / business_scenario / business_practice` 路由
- query_wiki 支持 `type_filter=business_*`
- aliases 3x 权重机制复用于业务元语别名

**验收标准：**
- 支持录入业务元语和场景链路
- query_wiki(type_filter=business_scenario) 可按业务维度检索
- 场景文件包含从用户操作到后端服务的完整链路

**来源：** 阿里知识库 §1 + §8

---

### 3.3 任务路由（Task Routes）

**问题：** Agent 接到任务后需自行判断"改数据库应该看哪些页面"，缺乏主动的知识预加载机制。

**方案：**
- schema.yaml 新增 `task_routes` 配置：
  ```yaml
  task_routes:
    add_api:
      required: [type=entity, type=concept, scope=wiki/policies/]
    modify_database:
      required: [scope=wiki/infrastructure/, scope=wiki/policies/]
    fix_bug:
      required: [scope=wiki/flow/, type=business_scenario]
  ```
- 新增 MCP 工具 `get_task_context(task_type, scope)`：根据任务类型自动聚合相关知识片段
- 消费协议 Stage 1 中：Agent 先识别任务类型，再按路由加载知识

**验收标准：**
- get_task_context 返回指定任务类型的必读知识清单
- 支持用户在 schema.yaml 中自定义路由规则

**来源：** 阿里知识库 §3

---

### 3.4 验证策略（Verification Matrix）

**问题：** CodeWiki-CN 不会告诉 AI"改了这个模块后需要跑哪些测试"。

**方案：**
- schema.yaml 或独立 `verification.yaml` 定义验证矩阵：
  ```yaml
  verification:
    add_api:
      - contract_test: "tests/contract/"
      - compatibility: "新字段必须有默认值"
    modify_state_machine:
      - flow_test: "tests/flow/"
      - coverage: "正向+逆向+异常分支"
  ```
- write_doc_file 生成模块文档时，检测到状态机/API 定义时自动追加"验证建议"章节
- 消费协议 Stage 4（自查）中：Agent 检查验证策略是否满足

**验收标准：**
- 支持按变更类型定义验证规则
- 模块文档中包含验证建议章节

**来源：** 阿里知识库 §4

---

## Phase 4：生态与高级能力（Ecosystem 层）

> 目标：覆盖运行时语义、跨仓库知识、风险治理等高级场景。
> 预计周期：持续迭代
> 涉及文件：新增模块

### 4.1 运行时配置语义注入

**问题：** 大量业务逻辑依赖配置（application.yml、@Value、Nacos/Apollo），CodeWiki-CN 只能说"读取了某项配置"，无法说明配置的业务含义。

**方案（分阶段）：**
- Phase A：AST 解析阶段识别 @Value / @ConfigurationProperties，提取配置 key 为组件元数据
- Phase B：解析 application.yml，将配置值（脱敏后）注入 prompt 上下文
- Phase C：支持 Nacos/Apollo 等外部配置中心 API 拉取（需用户配置连接）
- schema.yaml 新增 `config_injection` 配置节（sources + sensitive_keys）

**验收标准：**
- Spring Boot 项目配置项覆盖率 > 85%
- 敏感配置（password/token/secret）自动脱敏

**来源：** 高德 CodeWiki §3.6

---

### 4.2 业务-架构映射（Scenario 链路追踪）

**问题：** CodeWiki-CN 从代码出发，只能回答"这个模块做了什么"，不能回答"用户点击删除按钮时后端经历了什么"。

**方案：**
- 利用现有 trace_path / cross_service 能力，支持"从 API 入口追踪完整调用链"
- 新增 `type: scenario` 页面类型，路由到 `wiki/scenarios/`
- 场景文件格式：YAML frontmatter（关联 meta + principle）+ Markdown body（完整链路）
- 半自动生成：LLM 基于调用图生成链路草稿 → 研发确认补充业务语义

**验收标准：**
- 支持从 API 入口自动生成调用链草稿
- 场景页面包含从用户操作到数据变更的完整链路

**来源：** 阿里知识库 §8

---

### 4.3 风险优先级框架

**问题：** 所有模块一视同仁生成文档，不区分"高复用/高风险/高隐性"。

**方案：**
- analyze_repo 阶段利用复杂度指标（cyclomatic/cognitive complexity）识别高风险模块
- schema.yaml 支持 `priority_modules` 配置
- overview.md 按风险等级排序模块
- lint_wiki 检查：高风险模块是否有 policy + 验证策略

**来源：** 阿里知识库 §7

---

### 4.4 多仓库知识全景

**问题：** 单仓知识库难以回答跨系统影响面。

**方案：**
- 在现有 monorepo 跨服务分析基础上，扩展到多仓库：
  - 支持 `analyze_workspace` 分析多个关联仓库
  - 跨仓库依赖引用（RPC 接口、MQ topic、共享配置）
  - 产品级知识全景 overview

**来源：** 高德 CodeWiki §5（未来方向）

---

## Phase 5：资产治理（Governance 层）

> 目标：让知识"可信且可纠错"——为资产增加置信维度与纠错通道，从"越积越多"走向"越积越准"。
> 背景：记忆分层提取（L0-L3，见系列 4）解决了知识的组织形态，authority-aware 排序（2026-08-21 落地）解决了"已验证内容排前面"，但资产仍缺少显式置信层级，错误召回也无法改变后续路由。
> 来源：腾讯技术工程《任何错误只犯一次：TencentDB Agent Memory 的团队记忆实践》——2,600 Session 数据研究显示：22,361 条关系中仅 231 条是可执行强关系，其余只能作背景参考（关联 ≠ 复用）；卡点分布中"逻辑返工"（1,350）远超"缺少上下文"（269），错误经验比缺失经验伤害更大。

### 5.1 资产置信分层（strong / weak / shadow）

**问题：** 笔记只有生命周期状态（draft/stable/deprecated），没有置信维度。检索对"验证过的经验"和"未验证的背景"一视同仁，Agent 无法区分什么可以直接执行、什么只能当参考。TAM 数据表明模型容易发现"两个任务相关"，却很难判断"经验可迁移"——不分层就会把背景当指令。

**方案：**
- frontmatter 新增 `confidence_level: strong | weak | shadow`：
  - **strong**：confirmed 且有验证证据（测试通过 / 提交引用 / 人工复核）——可进入任务计划直接执行
  - **weak**：confirmed 但未验证——提示风险，谨慎使用
  - **shadow**：未确认 / 被降权——只参与召回发现，不驱动执行
- **升级路径（验证后升级）**：shadow → weak 走 confirm_note；weak → strong 需附加验证证据（test_ref / commit_ref / reviewed_by），对齐 TAM"未经验证的轨迹只是低权重背景"
- 检索集成：扩展现有 authority 排序（已按 status/note_type 加权）纳入 confidence 维度；query_wiki 结果带 `confidence` 字段；默认上下文装配只收 strong，weak/shadow 需显式开启
- wiki_stats 输出置信分布（strong/weak/shadow 占比），作为知识库健康度指标

**验收标准：**
- 笔记与场景块携带 confidence_level 且可流转（含 weak→strong 的证据附加）
- 检索结果按置信标注与排序，shadow 资产默认不进任务上下文
- wiki_stats 可见置信分布

**来源：** TAM 实践 §3.2（强关系/Shadow 分层）、§6.1 原则五（资产生命周期）

---

### 5.2 负反馈闭环（检索纠错）

**问题：** 错误召回目前只能靠 reject_note 人工事后处理，且不影响后续路由——同一条过期/错误知识会反复命中。TAM 六条设计原则明确："人的负反馈必须改变后续路由"。新鲜度问题同样无解：历史上正确的结论会因接口升级、配置迁移而失效，现有 stale_notes 只按时间粗判。

**方案：**
- **误召回标记**：新增 `flag_misrecall` 工具（或扩展 flag_issue），记录"资产 X 在任务 Y 中被误用"，累计 misrecall_count 与场景描述
- **自动降权**：misrecall_count 达阈值 → 自动降为 weak/shadow + 进入待复核清单（lint 新增 `disputed_assets` 检查）；降权事实写回 authority 排序
- **新鲜度字段**：frontmatter 增加 `valid_from` / `valid_to` / `last_verified_at` / 关联代码版本；stale_notes 升级为基于这些字段判定，而非仅按天龄
- **负例学习**：误召回记录沉淀为负例库，蒸馏/聚合时相似触发条件给出提示（"此模式曾被判为不适用"）

**验收标准：**
- 负反馈可改变资产置信与检索权重（同查询不再优先命中被降权资产）
- 过期资产基于 valid_to / last_verified_at 被自动标记
- 误召回历史可追溯（哪个任务、什么原因、何时降权）

**来源：** TAM 实践 §6.1 原则五（负反馈改变路由）、§6.2 六类工程问题（冲突/新鲜度/负反馈）

---

## 依赖关系图

```
Phase 1 (Prompt/Schema)
  1.1 Evidence-Based ──┐
  1.2 目录表格式 ──────┼──→ Phase 2 (Engine)
  1.3 渐进消费协议 ────┤      2.1 规则引擎路由
  1.4 来源标注 ────────┘      2.2 知识飞轮 ──→ Phase 3 (Content)
                              2.3 BFS 上下文       3.1 Policy
                              2.4 方法级增量       3.2 业务层
                                                   3.3 任务路由 ← 依赖 3.1 + 3.2
                                                   3.4 验证策略
                                                        │
                                                        ▼
                                                   Phase 4 (Ecosystem)
                                                   4.1 配置注入
                                                   4.2 Scenario
                                                   4.3 风险优先级 ← 依赖 3.1
                                                   4.4 多仓库
                                                        │
                                                        ▼
                                                   Phase 5 (Governance)
                                                   5.1 置信分层 ← 依赖 L0-L3 分层 + authority 排序（已落地）
                                                   5.2 负反馈闭环 ← 依赖 5.1
```

---

## 成功指标

| 阶段 | 核心指标 | 目标值 |
|------|---------|--------|
| Phase 1 | LLM 消费 Wiki 的平均 token 数 | 减少 40%（渐进读取 vs 全量） |
| Phase 1 | 业务断言有证据比例 | > 70% |
| Phase 2 | 典型 Java 仓库 LLM 调用量 | 减少 30%（规则引擎路由） |
| Phase 2 | 大仓库增量分析时间 | 减少 50%（方法级增量） |
| Phase 3 | 约束发现覆盖率（对标高德案例） | proposal 得分从 baseline 提升 3x |
| Phase 4 | Spring Boot 配置项覆盖率 | > 85% |
| Phase 5 | 检索结果中 strong 资产占比 | > 60%（置信分布可观测） |
| Phase 5 | 被负反馈资产的重复误召回率 | 降权后同查询命中下降 ≥ 50% |

---

## 参考文档

- [高德CodeWiki文章-工程借鉴分析](./高德CodeWiki文章-工程借鉴分析.md)
- [阿里AI知识库文章-对CodeWiki-CN的借鉴分析](./阿里AI知识库文章-对CodeWiki-CN的借鉴分析.md)
- [LLM-Wiki-扩展方案](./LLM-Wiki-扩展方案.md)
- [跨服务调用分析-实现计划](./跨服务调用分析-实现计划.md)
- [CodeWiki-Plus系列4：记忆分层提取——从经验碎片到团队Doctrine](./articles/CodeWiki-Plus系列4：记忆分层提取-从经验碎片到团队Doctrine.md)
- TAM 团队记忆实践原文（已 ingest 至 `repowiki/raw/sources/tam-team-memory-practice.md`，见 source_registry）
