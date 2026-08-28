# Spec: 集中式 Wiki 布局（`layout=centralized`）

Status: ready-for-agent
Date: 2026-08-28
设计文档: `docs/多仓Harness工作区-集中式Wiki布局设计方案.md`（本 spec 是其实现规格，冲突时以设计文档的决策记录为准）

## Problem Statement

在多仓 harness 工作区中，各业务仓的知识分散在各自的 `repowiki/` 里：跨仓检索必须两跳（先产品级、再下钻仓库级），共享领域词汇（同名实体在各仓含义一致）被按仓撕成碎片，产品级经验（编码规范、踩坑、决策）无法一跳命中。部分产品线并不看重"wiki 与代码同仓演进"，更愿意要一个统一、集中、可一跳检索的知识库——但现有工具只支持同仓布局，没有任何布局选择入口。

## Solution

`init_workspace` 新增 `layout` 参数，提供两种知识布局：`colocated`（默认，与现状逐字节一致）与 `centralized`（全部知识汇入工作区唯一 `repowiki/`）。选择一次、落盘为机器可读配置，此后登记、建仓、分析、检索、写入全部按布局自动路由；对单库场景（无工作区）与未登记目录零影响。

## User Stories

1. As a 产品线维护者, I want 在 `init_workspace` 时选择 `centralized` 布局, so that 整个产品线的知识集中在一个可检索库里。
2. As a 产品线维护者, I want 不传 `layout` 时行为与现版本完全一致, so that 存量工作区与使用习惯零迁移成本。
3. As a 产品线维护者, I want 布局选择落盘为机器可读配置（`repowiki/.meta/workspace.json`）, so that 任何会话、任何 Agent 的路由行为确定，不靠记性。
4. As a 工作区操作者, I want `add_workspace_repo` 在集中模式下建 `wiki/modules/<仓名>/` 骨架且不建仓内 `repowiki/`, so that 业务仓保持纯代码、知识归属唯一。
5. As a 工作区操作者, I want `add_workspace_repo` 在集中模式下移除业务仓 AGENTS.md 的 CodeWiki 引用块, so that 不残留指向不存在目录的死引用。
6. As a 工作区操作者, I want `analyze_workspace` 在集中模式下从 `wiki/modules/<仓名>/` 读取各仓知识（而非硬编码 `<仓>/repowiki`）, so that 跨服务拓扑分析在集中模式下可用。
7. As a 工作区操作者, I want `analyze_workspace` 提供 `generate_repo_wikis`（默认 false）并由工作流 Prompt 显式询问, so that 逐仓深度生成这类重活不会被意外触发。
8. As a 编排 Agent, I want 为每个业务仓 spawn 一个 subagent 并行调用 `analyze_repo`, so that 多仓 wiki 生成耗时从串行总和降为最慢一仓。
9. As a 编排 Agent, I want 并行建仓时共享池同名页的 `repos:` 累积不丢数据, so that 并发不会静默破坏来源记录。
10. As a 检索者, I want 集中模式下 `query_wiki` 不传过滤时一跳覆盖产品级 + 全部业务仓, so that 产品级知识一次命中。
11. As a 检索者, I want `query_wiki(repo=<仓名>)` 返回"适用于该仓的知识"＝该仓 modules 分区 + 带该仓标的共享页 + 无范围标的全局页, so that 改某个仓时自动带上产品线级编码规范与决策，不漏约定。
12. As a 检索者, I want `output_dir` 仍可按目录定位（如指向 `wiki/modules/<仓名>/`）, so that 轻量场景沿用既有机制、无需新参数。
13. As a 知识沉淀者, I want `ingest_note`/`write_doc_file` 在集中模式下按页型自动路由（module → 仓分区，其余 → 共享池）, so that 写入方不必关心布局细节。
14. As a 知识沉淀者, I want 共享池页面用 frontmatter `repo:`/`repos:` 标注适用范围（无标＝产品线全局）, so that 单仓、多仓、全局知识同池共存且可过滤。
15. As a 任务记忆使用者, I want 集中模式下 `tasks/`、`raw/`、`conversations/`、`.meta/task_bindings/` 落在工作区根共享区, so that 横跨多仓的任务与会话有唯一归属，不必回答"这条对话算哪个仓"。
16. As a lint 使用者, I want `lint_wiki` 在集中模式下对"业务仓目录出现 `repowiki/`"与"共享池页缺失 `repo:` 来源标"告警, so that 布局纪律可被持续校验。
17. As a 工作区操作者, I want `remove_workspace_repo` 在集中模式下同时清理 `wiki/modules/<仓名>/` 分区与共享池中该仓的来源标, so that 移除业务仓不留知识孤儿。
18. As a 单库用户（无工作区）, I want 所有工具行为与现版本一致, so that 独立仓库使用 `init_wiki`/`analyze_repo` 不受本特性任何影响。
19. As a 用户, I want 手动 clone 进工作区目录但未登记的仓库不被集中路由劫持, so that 无关仓库的 wiki 不会被写进别人的工作区。
20. As a 用户, I want 探测结果进程内缓存、到文件系统根即止, so that 深嵌套目录不付反复向上遍历的性能税。
21. As a 用户, I want `workspace.json` 丢失时回退 `colocated` 行为, so that 配置意外损失不破坏既有工作区。
22. As a 实体知识使用者, I want 共享实体池直写、后写覆盖、`repos:` 来源累积（只增不减）, so that 实体自动化不被人工闸门吃掉，覆盖风险由新鲜度机制暴露。

## Implementation Decisions

- **两种布局、一个入口**：`init_workspace` 增可选参数 `layout`，枚举 `colocated | centralized`，默认 `colocated`。`colocated` 的产物与现版本逐字节一致。
- **配置契约**：集中模式写 `repowiki/.meta/workspace.json`，形状 `{ "wiki_layout": "centralized" }`。仓清单不进此文件——bootstrap 脚本登记表仍是唯一事实源，其结构与正则锚点不动；因无逐仓覆盖，配置只有这一个标量字段。
- **唯一新增接缝——工作区解析模块**：全部新路由逻辑收敛进一个纯函数式模块，对外提供两件事：① 给定目录，解析出（工作区根 | 非成员 | 无工作区）三态 + 布局值；② 给定布局 + 仓名 + 页型，返回目标落点。解析必须实现四条护栏：
  1. 探测信号只认 `workspace.json`（自目录向上找到文件系统根；bootstrap 登记表不作为探测信号）；
  2. 命中后成员校验：仓目录名须在登记表内，未登记视为非成员；
  3. 三态回退：未找到 / 非成员 / `colocated` → 现状路径（`repo_path/repowiki`）；
  4. 结果进程内缓存。
  所有调用方（output_dir 解析链、analyze_workspace、query_wiki、ingest_note、lint）一律经由此模块，不得各自实现目录遍历。
- **集中模式目录结构**：唯一知识库在工作区根 `repowiki/`。切线规则一句话：**只有 modules 按仓分区**（`wiki/modules/<仓名>/`），其余页型（sources、entities、concepts、notes、comparisons、queries）一律进共享池，用 `repo:`/`repos:` frontmatter 标范围。运行时数据（任务记忆、对话原料、蒸馏归档、会话绑定）落在 `repowiki/` 根，不按仓分片。
- **页型路由扩展**：frontmatter module 的页型路由需感知布局——集中模式下 `module` 页路由到仓分区（需要仓名上下文），其余页型路由到共享池目录。`page_types` 的 schema 映射保持目录级、布局无关，分区是路由层职责。
- **`repo=` 过滤语义**：`query_wiki` 增可选参数 `repo`。返回＝该仓 modules 分区 ∪ `repo:`/`repos:` 包含该仓的共享页 ∪ 无范围标的全局页。与 `output_dir` 的关系：`output_dir` 是目录级定位（单一路径），`repo` 是仓身份聚合（跨目录），二者不冗余。
- **`analyze_workspace` 契约**：增可选参数 `generate_repo_wikis: bool`，默认 `false`；拓扑分析总是执行，逐仓 modules 生成仅在显式开启时执行；`colocated` 下忽略。子仓读取路径改由布局决定。
- **AGENTS.md 变体**：约定块生成接受布局参数，集中模式产出"一跳检索 + 平铺路径"的写入路由表变体；同时在集中模式建仓时移除业务仓 AGENTS.md 的 CodeWiki 块（块锚点机制与 refresh 语义不变）。
- **共享池写入策略**：直写、后写覆盖、`repos:` 累积只增不减；薄覆盖厚的风险交给新鲜度机制暴露，不做写入时拦截，不设晋升闸门。
- **并发保障**：共享池页的读改写（`repos:` 累积）用跨平台文件锁（复用现有 fcntl/msvcrt 追加锁范式，泛化为读改写锁）。锁只包集中模式共享池路径；单库与 `colocated` 写入路径不经过锁。分析缓存已是 WAL，不动。
- **lint 扩展**：新增 layout-violation 检查，仅集中模式生效（业务仓目录出现 `repowiki/`、共享池页缺失来源标）。
- **须尊重的既有决策**：任务记忆保持 Markdown、追加式原子写（ADR-0001）；任务记忆蒸馏直写落盘、无确认闸门（ADR-0002）——本特性只改运行时数据的 `output_dir` 根，不改其写入语义与相对路径常量。
- **参数默认值**：`layout=colocated`、`generate_repo_wikis=false`——所有默认值都指向现状行为。

## Testing Decisions

- **好的测试只测外部行为**：给定临时目录树（工作区骨架 / 单库 / 未登记仓），断言文件落在哪、查询返回什么、配置缺失时回退到什么；不测目录遍历的内部实现、不测缓存何时失效。
- **首选既有接缝——MCP 工具 handler 层**：`handle_*(arguments: dict) -> str` 直接以参数字典驱动、产物落临时目录可断言。先例：`test_workspace_bootstrap.py`（init/add/remove 的事务性与幂等测试）、`test_task_manager.py`（临时 repowiki 上的行为测试）。新布局的 init/建仓/分析/移除行为全部在这一层测。
- **新接缝——工作区解析模块**：纯函数 + 临时目录 fixture，覆盖四条护栏的各分支：无 `workspace.json`（单库）、找到但未登记（防劫持，本特性的头号回归风险）、`colocated`、`centralized`、深嵌套目录的缓存命中。
- **必须覆盖的场景矩阵**：单库零影响回归；未登记目录防劫持；集中模式下 ingest 按页型分流（module 进分区、其余进共享池带标）；`repo=` 过滤的三态组成（分区 ∪ 带标 ∪ 全局）；`workspace.json` 丢失回退；并行写共享池时 `repos:` 不丢（两个进程/线程并发写同名页）。
- **运行时数据断言**：集中模式下任务/会话工具写入落工作区根，且写入格式、原子追加语义与现状逐字节一致（护住 ADR-0001/0002）。

## Out of Scope

- 布局迁移工具（`migrate_workspace_layout`）——v1 只提供手工迁移步骤（见设计文档 §13），不提供自动迁移。
- 逐仓布局覆盖——布局是工作区级单一选择，无 per-repo override。
- `query_cross_service` 的任何改动（与布局无关）。
- `colocated` 模式的任何行为变化（默认值即现状）。
- 实体两段式晋升/人工闸门、集中模式下停止自动产实体。
- 存量业务仓已有 `repowiki/` 的自动并入——转集中模式时其知识去留由人决定。

## Further Notes

- 设计文档 `docs/多仓Harness工作区-集中式Wiki布局设计方案.md` 含完整决策记录（D1–D13，每条带取舍理由）与代码改造点清单（按模块与函数定位），实现时应与其逐条对齐。
- 并行生成的推荐编排形态是 Agent 层 subagent（每仓一个），`generate_repo_wikis` 保留为小工作区/非 Agent 场景入口；工作流 Prompt（`init-workspace` 等）需把"是否逐仓生成 + 并行编排"呈现给用户。
- 规范类知识有两个载体：AGENTS.md（自动加载、始终生效）与共享池（可查可溯）；实现写入路由时不要把本该进 AGENTS.md 的产品线约定只落共享池。
- 本 spec 由 to-spec 技能自设计讨论综合生成；设计讨论中经 grilling 收敛的全部决策（含范围模型、探测护栏、单库零影响审查）已并入设计文档。
