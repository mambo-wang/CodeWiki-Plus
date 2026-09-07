---
type: Conversation
title: "conversation 20260901T113456Z"
status: distilled
stale_after: 2026-11-30
generated: { by: codewiki/5.5.0, at: 2026-09-01T11:34:56Z }
captured_at: "2026-09-01T11:34:56Z"
content_hash: "sha256:35fad8dd59db8ff767034f063ce2c1738b790f31ffc75a09d8eb973e798414f1"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=7"
keep_raw: false
link_to: ""
source_session: "qwenwork-mthdj7p67xm7gxa0"
turn_count: 14
---

# Conversation Transcript

user: 调研一下，如果 CodeWiki 项目要做成团队级工具，在保持现有部署形态（本地 MCP + repowiki 目录 + git 同步）的情况下，有什么可以优化的，减少或避免文件冲突。
assistant: 调研完成（代码探索 + Wiki 既有笔记核对）。项目已有一轮团队化设计"文件级隔离 + 每用户独占文件"（memories/<user_id>.md、telemetry per-user jsonl、统一存储层 codewiki/src/store.py 提供跨进程 .lck 锁 + os.replace 原子写，KnowledgeStore 落地见提交 557efcf；.gitignore 已排除 raw/、telemetry-local/、.codewiki/、*.lck），但只覆盖部分写路径。按 repowiki/ 全部写点清单归纳三类：

【天然无冲突（不用动）】memories/<user_id>.md（per-user 追加 + 锁内原子写，全项目做得最好）；telemetry per-user jsonl；.meta/task_bindings/<session_id>.json（文件名即会话 id）；raw/ 与 conversations/（每文件独立，raw 已 gitignore）；analysis_cache.db 与 .codewiki/（gitignore 本机缓存）；ontology.yaml（init 后只读）。

【冲突高发（按严重度）】1) wiki 文档页整页覆盖重生成（wiki/modules/*.md、overview.md，doc_writer.py 多处裸 write_text，无锁非原子）——最大冲突面；2) schema.yaml 纯时间戳 churn（每次 analyze_repo 经 ruamel round-trip 回写，generated_at、project.* 每次刷新，schema_generator.py）——最高频、最无意义的冲突源；3) .meta/ 整文件重写型 JSON（metadata/module_tree/symbol_map/edit_history/source_registry/aggregate_state，读-改-整文件重写，多数裸写；edit_history.json 无上限增长，undo 语义本可由 git 历史承担）；4) 可重建缓存却入库（tasks/.index.json、raw/.index.json 以目录扫描为真相、有自愈重建逻辑，但入 git 且读-改-写未套锁，两人各自 create_task/capture 必然 JSON 数组级冲突）；5) wiki/log.md 每次在文件顶部插入（跨进程无锁，只有进程内线程锁，两人各自 append 几乎必冲突且互丢条目）；wiki/index.md 是从全体文档重建的派生物；6) notes 全员共享可改写面——无 author/owner 字段，任何人可改写他人笔记，draft/stable 状态同文件 frontmatter 原地翻转、写点裸写（knowledge_loop.py），并发蒸馏查重靠文件扫描 + 标题 Jaccard 有 TOCTOU。

【本地并发互踩（非 git 层）】一批裸 write_text 写点（notes 状态翻转、distill 等）未套锁，同机并发会互相覆盖。
user: 要考虑单仓、多仓集中式、多仓同仓式三种情况。另外每次写文件前自动 git pull 拉取最新代码会不会好一些？
assistant: 三种形态对齐（项目自有术语）：单仓 = 独立仓跑 init_wiki；多仓同仓式 = v5.5.0 colocated 布局（harness 放产品级知识，各业务仓自己的 repowiki）；多仓集中式 = v5.6 centralized 布局（全部知识汇入 harness repowiki，只有 modules 按仓分区）。

【单仓】即上轮完整冲突面。【同仓式（colocated）】结构性冲突概率最低：冲突面按仓天然切分，各仓 repowiki 互不相交；产品级共享层（harness overview/repo-map/跨仓约定）内容少、更新低频是冷文件；剩余风险只有同一仓多人协作退化为单仓情形 + harness 仓自己的 index/log/.meta。结论：colocated 的团队冲突 ≈ 各仓独立地发生单仓冲突，天然有按仓隔离红利。【集中式（centralized）】关键 trade-off：modules 按仓分区把最大内容冲突面（模块页重生成）结构性隔离（设计方案 §10.1 subagent 并行生成吃这个红利），但代价是派生/索引文件从"每仓一份"升格为"全局单点"——wiki/index.md（rebuild 依赖全部文档，任何仓 ingest 都触发重写）、wiki/log.md、repo-map.md、overview.md、.meta/ 全局 JSON（metadata/edit_history/source_registry/aggregate_state）、schema.yaml，冲突概率变成"所有人 × 所有仓"。优化重点：全局派生文件 gitignore + 读路径/lint 触发重建（rebuild 原语已有），log.md 按仓或按月分片成纯追加；与集中式方案 §12.8 计划泛化的通用读改写锁合并落地。

【写前自动 git pull：否决】结论：不好，甚至有害——pull 不消灭冲突，只改变冲突出现的时机和地点，还会把冲突搬进无人值守的自动流程。1) 时机不成立：git 冲突发生在 merge/push 时刻不在写时刻，写前 pull 只保证写的那一瞬间基线最新，写完到 push 之间别人照样 push；全部收益只是缩小过期基线窗口，代价是每次写都付网络往返。2) 业务工作树上不可行（单仓/colocated 硬伤）：pull 是工作树变更操作，业务仓工作树混着用户未提交改动，且 repowiki 文件总是脏的（工具刚写过未提交），pull 遇脏重叠文件直接拒绝，--autostash 则 stash 用户代码再 pop、pop 冲突更糟；工具擅自改动用户工作区是红线。3) 频率与环境不划算：MCP 高频小操作，每次写前 0.5~3 秒网络延迟、离线不可用、凭据弹窗风险。4) 方向反了：降冲突概率的是 push 频率——高频小步 push 缩小分歧窗口，不是 pull。5) 孤儿分支 lesson 同构结论：pull 只是挪冲突时机，冲突面"只挪不消"。替代方案：写前 fetch 校验（advisory，只读告警）+ 仅集中式会话边界 --ff-only pull + 高频小步 push，按形态门控。
user: 生成详细设计方案。
assistant: 设计方案已写入 D:\repos\CodeWiki-CN\docs\团队化文件冲突治理与同步策略设计方案.md。动手前核实了关键代码事实（一个重要发现：codewiki/src/evidence.py 的证据锚定刻意用内容哈希而非 git SHA，约束了同步方案的设计取向）。

方案要点：一个核心原则——git 只存"内容"，一切索引/派生/运行态本地可重建（把 search_index.json 的 T3 先例扩展为通则）。在此之上四层设计：① 布局去噪（11 个文件移出跟踪 + log 按月分片）；② churn 抑制（schema.yaml 实质变更才回写）；③ 并发收口（裸写点统一接入 store.locked()+atomic_write，与集中式方案 §12.8 的读改写锁合并实现）；④ 新鲜度与归属（内容哈希指纹 + notes author，沿用 evidence.py 不用 git SHA 的取向）。同步策略按三重门控：业务代码所在仓永不自动 pull/push；只有集中式的 harness 仓可开启会话边界 --ff-only 拉取和写后小步推送；"写前自动 pull"在 §6.3 留了完整五条否决论证。文末附三种形态冲突面矩阵、12 项改造点清单、9 条决策记录（D1–D9）、四期计划（建议 Phase 1 布局去噪先行：改动小且不依赖其他项）。

两处衔接点：#6 通用读改写锁与集中式方案 §12.8 是同一件事，建议合并排期；集中式专项（§5.5）以集中式布局过评审为前提，其余项可独立先行。
user: 调研一下 TEAMaI-CLI 项目（Tencent/teamai-cli）是如何处理这种情况的。
assistant: 本机无旧克隆，从 codeload 下载 main 分支源码包解压核实（v0.21.0，比 8 月初次调研 docs/teamai-cli-调研与借鉴分析.md 的 v0.20.0 新，本篇专注冲突与同步链路，逐文件核实）。一句话结论：teamai-cli 的答案是"靠划分防冲突，不靠锁"——没有分布式锁、没有服务端，核心手法是把会冲突的东西从结构上分开，剩下不可避免的 push 竞争用 fetch+rebase 重试兜底。

五层机制：1) 架构前提：永不触碰用户业务树——独立团队仓模式用一次性缓存 clone（~/.teamai/team-repo）承载全部 git 操作；单仓模式干脆不做 git pull，知识随用户自己的业务仓 pull 搭便车到达，工具只读 HEAD rev 当缓存版本号（src/pull.ts:66-88）；所有 git 写操作在两类隔离 worktree 里，源码注释："Running those on the user's active working tree would destroy their uncommitted business code"（src/utils/reports-branch.ts:9-12）。2) 双 worktree 写隔离：一次性 knowledge-wt（用完 worktree remove --force，主仓永不切分支）承载 push/contribute + 持久 reports-wt 挂在 teamai-reports 真孤儿分支（无父提交、独立历史）上，承载 members/、sessions/、votes/、stats 这类"高频噪音、must NOT pollute main"的上报数据。3) 文件级冲突靠 per-user 划分：每人只写自己的 <user>.yaml / sessions/<user>/ 子目录，源码论证"因此 rebase 冲突实际不可能发生"；learnings 直推用文件名 6 位随机后缀防撞名。4) push 竞争：孤儿分支路径 push 失败 → fetch + rebase origin/teamai-reports 重试 ≤5 次（reports-branch.ts:188-250），rebase 失败即 abort 进下一轮，耗尽不抛异常不阻塞，数据留本机随下次提交搭载；投票用 deltas 正增量模型（幂等，失败不清增量）；本机多进程 PID 文件锁自述"protective hint, not a hard barrier"；注意 git 模式直推（pushRepoDirectly）没有重试——设计文档写 3 次、代码实为 5 次且只在 reports 路径，以代码为准。5) 索引不入库：search-index.json local-only，pull 时重建、contribute 后立即重建（不用等 pull 就能召回），设计文档 Key Design Decision 原文"Rebuilt at pull time, no sync conflicts"。降级模型：数据不丢，延迟到达——失败只降级为"待搭载"，本地盘恒为真相，幂等是搭载前提，唯一状态变化点是成功的 push。

薄弱点（对我们的镜鉴）：graph-index.json（整文件 JSON）入库，跨机器并发写无锁，靠"必须经 MR 单点合入"+ 本机建议性锁 + 批处理末尾统一聚合兜底——自认的软肋；0.4.5 CHANGELOG 自曝 reportUsageToTeam 并发 push 互相覆盖导致数据丢失，修复方式是"先 pull 拿远端再合并"，印证整文件覆盖式同步必然踩坑、正增量合并才是解。结论：整文件派生物只有两条出路——不入库（我们的 D1），或入库但强制 MR 单点写入；不能两头都不做。
user: 把三点修订合入设计方案。
assistant: 三点修订已全部合入，文档升级为 Rev. 2（docs\团队化文件冲突治理与同步策略设计方案.md）：

1) §6.1 auto_push 失败处理改为：自动 fetch+rebase 重试 ≤5 次（rebase 失败即 --abort 进下一轮），耗尽才保留本地提交、报告人工、下次成功推送搭载；永不 force、不回滚本地提交——决策记录 D10。
2) §6.2 新增"搭便车语义"门控条目：同仓式/单仓默认工具零 git 动作，知识随业务仓自身同步节奏到达，advisory 为 opt-in 只读告警（§5.5 形态专章同步更新）——决策记录 D11。
3) 新增 §6.4"数据不丢，延迟到达"降级不变量：任何失败只降级为待搭载、不抛错不阻塞不中断工具调用；本地盘恒为真相（滞留 auto_push 提交保留、永不 reset）；幂等是搭载前提（含 deltas 正增量模型约束）；唯一状态变化点是成功的 push——决策记录 D12。

D10–D12 均标注来自 teamai-cli v0.21.0 对照。顺手修正初稿三处章节引用错误（§8.1→§6.3、§8.2→§6.2、§8→§6）。另提议：把 teamai-cli 冲突机制调研沉淀为 Wiki 笔记（素材完整、带文件级出处，其"整文件 JSON 入库只经 MR"薄弱点与我们 D1 的对照有复用价值），确认后起草。
user: 起草这篇 teamai-cli 调研笔记。
assistant: 草稿如下（确认后才写入，写入后仍是 draft 状态，需要 confirm_note 才转正）：
标题：teamai-cli 多人文件冲突处理全景：靠划分防冲突，不靠锁（v0.21.0 源码核实）；类型 architecture；别名：git-native 团队知识同步、per-user 文件隔离、孤儿分支上报、延迟到达、搭便车同步；关联模块：git、团队协作、MCP 存储。
正文结构：背景（CodeWiki 团队化设计需要一份经验证的 git-native 参照，teamai-cli 48 个版本迭代的试错史是最完整样本，2026-09-01 经 v0.21.0 源码逐文件核实，与 8 月初次调研 v0.20.0 docs/teamai-cli-调研与借鉴分析.md 互补）；核心机制带出处（永不触碰业务树/缓存 clone + 双 worktree、孤儿分支 teamai-reports、per-user 划分、fetch+rebase 重试 ≤5 与"数据不丢延迟到达"、索引不入库 pull 时重建）；薄弱点（graph-index.json 整文件 JSON 入库靠 MR 单点合入是自认软肋→整文件派生物只有两条出路；0.4.5 并发 push 覆盖丢数据教训）；对 CodeWiki 的镜鉴（印证 D1、支持 D10–D12）。
user: 写入。
assistant: 笔记已写入（draft 状态，路径 repowiki/notes/2026-09-01-teamai-cli-多人文件冲突处理全景靠划分防冲突不靠锁v0210-源码核实.md），检索时会带 [unconfirmed] 前缀，复核后跑 confirm_note 即转正。

本调研线程已收敛，产出清单：① 设计文档 docs/团队化文件冲突治理与同步策略设计方案.md（Rev. 2，核心原则"git 只存内容、索引/派生本地可重建"，四层设计，D1–D12 决策记录，四期计划，12 项改造点）；② teamai-cli 对照调研（v0.21.0 源码核实，支撑 D10–D12）；③ 上述 draft 笔记。待办：用户复核后 confirm_note 转正；Phase 1（布局去噪先行）实施待用户确认后开工。
