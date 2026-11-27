## 早期记忆（摘要）

ADR-0013 is complete: stable note ingestion requires a reason; draft/confirm is exempt. Optional test_ref/commit_ref/reviewed_by map to metadata.verification and strong confidence; unknown evidence keys are rejected. Registry schemas, docs and callers were updated. limits.py centralizes 40 entries, 24KB, keep-recent 20 and 4096-character summaries; threshold_drift guards registry/prompts. Aggregated-frontmatter line wrapping is a confirmed pitfall.

ADR-0015 converged AGENTS.md into a slim managed block plus on-demand wiki/prompt routing; product templates and prompts are implementation points. It was pushed as cb305c7; auto-sync schema churn and .codebuddy/memory were excluded. UserPromptSubmit active-settle was later implemented; PreCompact and Stop+block were rejected. The ide_config.py golden fixture remains deferred.

B4/B5 are internal modules, not new tools. B4 defaults to observe; enforce allows pending non-delete operators or the exact current target. Authorization binds routed page key, plan schema/hash and current centralized repository partition. Same-stem/other-repo pages never settle a module; keyless matches must be unique; overview is canonical. Off-plan writes are audited outside plan_hash. This is an operational host-agent gate, not a security boundary. B5 measures complete scope files; missing, unreadable or escaping paths are unmeasured rather than zero. It uses lightweight metadata and file-signature caches, degrades to unavailable without failing the saved tree, calls no LLM and never rewrites the tree. Historical tests: B4 43, B5 20, B1-B5 63, final integration 172, prompts 19; full suite 1538/2 skipped; contract 121/5 pre-existing failures. smoke_test_mcp.py is skipped because it writes the real repowiki. B4/B5 notes remain drafts; never auto-confirm. No B4/B5 commit or push was authorized.

Skills: caveman and humanizer v2.11.2 are installed. Ponytail T1/T2/T3 survey (CodeBuddy=T2) is recorded; its mechanism draft was rejected. Wikiskill turns confirmed notes/scenarios into a SKILL.md draft, then confirmation/install; no scoring gate. skill-creator uses prepare/submit/install/retire, inactive drafts and capacity 12. Ponytail/caveman fusion is unimplemented.

Research: hindsight is heavyweight; index suppression is partly covered by three-note listing; _DISTILL_SYSTEM has one reasoned literal rule (reason + NO COMPUTATION). Delta refresh and retrieval+RRF remain deferred; absorbed/deferred items need landing points/triggers. ADR-0012/draft updated. graphiti/ADR-0011 preserves malformed output as raw+parse_failed, reuses Chinese tokenization, drops invalid notes, uses weak conflict <0.8/fast path >=0.8; threshold changes need real-title tests. llm-wiki-compator contributed eval/freshness/atomic-intent/profile-as-data only. cognee was disproved 8/8; memos/supermemory/teamai-cli are deferred or covered. The 2026-09 survey: 11 projects/44 candidates, 0 adopted/15 deferred/29 excluded; reports are docs/借鉴项目整体增量调研报告-2026-09.md and docs/claude-mem-增量调研与借鉴分析-2026-09.md. Cost/scan budgets and deprecated-note revival remain gaps. CBM workspace-manifest was invalidated as a Rust Cargo manifest, not approval.

The 2026-09-20 AGENTS.md survey favors slim routing (cairn <=60 lines plus responsibility table), details on demand. Task-memory guidance duplicated AGENTS.md and SessionStart; prefer the hook hard channel plus a one-line pointer. teamai-cli golden fixtures and claude-mem native async remain candidates pending CodeBuddy validation. Reject claude-mem six-event full capture, inline-bash path parsing and letta commit-on-write. External clones belong under D:/repos. Verify subagent note status via get_task_context. The 2026-09-04 cross-Agent-skills draft is undecided. Older drafts await confirm_note; never auto-confirm. Tool-error signals come from tool_digest in _ide_hook.py/capture_conversation.py; session-end supplementary capture bypasses it, so the earlier 0% measured channel coverage, not miss rate. Early originals are archived in memories-archive/iamwangbao-163-com.md.

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-11-27，共 1 条。

### 2026-09-21 10:08 #y1a8

UserPromptSubmit active-settle 薄触发已实现（ADR-0015 后续，grill 2026-09-21 两轮）：①_ide_hook.py 加 ACTIVE_SETTLE_REMINDER 常量（混合措辞：回看补写+前瞻自查）与 _repo_has_active_tasks()（读 tasks/.index.json，fail-open）；②_handle_user_prompt 输出改为技能提示与提醒拼接（技能在前）；③test_skill_match.py 补 5 条断言（注入/无任务静默/非 active 静默/拼接顺序/索引损坏 fail-open）。全量 1131 passed。决策记录：PreCompact 不做（Q1 超集）、Stop+block 不做（无 transcript 无法验证+循环风险）、触发条件用「仓库有 active 任务」代理信号（绑定落盘方案 deferred）。待办：commit 未做。

### 2026-09-21 11:12 #iyy2

SubagentStart hook 评估定案（他山之石后续）：不做。理由：①CodeBuddy 是否支持该事件未验证；②沉淀责任应留在主 Agent——subagent 上下文窄、无任务级视野做四问过滤、跑完即销毁，直接落盘会绕过确认闸门（笔记）或灌爆任务记忆（直写）；③主 Agent 收到 subagent 返回值的那一刻就是天然停顿点，已被 active-settle 通道覆盖。正确增强点是「发起 subagent 的返回值约定」：已增补进 get_prompt(task-workflow) 的「会话进行中」节——主 Agent 派发子任务时 prompt 末尾加「返回结果时报告三件事：做了什么、关键发现、值得沉淀的经验（若有）」，过滤/查重/落盘全在主 Agent。distill-worker 是特例不冲突。全量测试 1130 passed（1 个并发测试 flaky 单独跑通过）。待办：commit 未做。

### 2026-09-21 15:18 #6txu

Workspace Conventions 模板瘦身完成（ADR-0015 同款收敛）：①两个模板（agents-md-workspace-centralized.md.tpl / agents-md-workspace.md.tpl）的「新业务仓接入清单」8→2 行——手工三步与 add_workspace_repo 工具事务式同步四处重复，收敛为工具名+get_prompt(add-workspace-repo) 指针，手工兜底三步移入该 prompt 注意事项；②分支策略 3→1 行（删解释留规则）。48→40 行。全量 1136 passed。待办：commit 未做。

### 2026-09-24 20:55 #fnyx

完成 agentmemory（rohitg00/agentmemory）源码调研并存档 repowiki/wiki/queries/agentmemory-调研.md。核心发现：重运行时路线（常驻 iii-engine、hooks 全量自动采集、264 函数、BM25+向量+图 RRF 检索、四层记忆巩固+衰减驱逐）。三项借鉴候选全部不立项：合成压缩→absorbed（与确认闸门冲突）；自动衰减驱逐→deferred（与「候选必有去向」Doctrine 冲突，等 lint_wiki low_adoption 数据）；slots 固定槽位→excluded（MEMORY.md+AGENTS.md+任务记忆三件套已覆盖）。总体判断：全自动采集/巩固/驱逐路线 CodeWiki 明确不走，本次调研价值在确认架构边界。

### 2026-09-25 21:35 #dvsa

skill hint 评估裁决（2026-09-25）：蒸馏 worker 提示笔记「hook 注册命令用 python -m 包内入口」命令密度 4 可能值得编译成技能。经 skill_creator prepare + 材料实读裁决不编译（no_action 已提交）：① 该笔记是 architecture 类型，不在 skill 素材边界内（素材只收 scenarios + stable pitfall/lesson/decision）；② 内容是结构认知（回答「hook 行为更新要不要改 settings.json」），非可触发行为指令，编译无触发场景。顺带发现：prepare 标记 worth_compiling=true 的同主题 pitfall「全局 codewiki.exe 无法 import 本地包，install-hooks 需用 python -m codewiki.cli.main」——deferred：信息量单薄（一条命令选择），单独成技能碎片化，等同类素材积累后并入。

### 2026-09-25 22:03 #o805

agentmemory Round 2 小优化 grill 定案（2026-09-25，用户裁决「按推荐」）：① MCP 工具面裁剪开关立项（P2）——CODEWIKI_TOOLS=core 环境变量，registry 加 filter，参考 agentmemory core-8 思路按本仓场景重定义核心集，归产品维护；② 会话多样性约束 deferred（等 lint_wiki 重复笔记数据）；③ RRF 融合 excluded（单流 BM25 无第二路可融，未来加向量检索时再议）；④ related_notes 语义召回 excluded（注入场景要确定性，task_id 精确匹配是特性不是缺陷）。已核对本仓等价物：同义词扩展（ontology.yaml）、CJK 分词（jieba+regex 降级）、SHA-256 去重（capture content_hash）均已有，无需行动。调研文档已更新第六节+处置表（repowiki/wiki/queries/agentmemory-调研.md）。

### 2026-11-19 15:45 #at1g

TDAM 增量调研（2026-11-19，基线 906b582 → HEAD 42d4cde，46 commits，v2.0.2→v2.0.3）：①文章《本体与 RSI》核心的三层图谱/bug_fixed/本体在开源代码零命中（grep 全仓 0 结果）——那是腾讯内部研发实践，未开源，开源仓只有四类资产（Chat Memory/Skill/Wiki/CodeGraph）。②开源增量两个真机制：Skill 按需选择（MemoryProxy/src/skill/selection/，JEV 决策服务可插拔 provider，client_tool 交付=proxy 伪造 tool_use 让客户端自己 curl 加载，MAX_CLIENT_LOADS=3/失败熔断 2 次，detect.ts:50-56 的 SYNTHETIC_USER_PATTERNS 合成用户消息识别）+ team_memory.enabled 实例级总开关（fail-open 全路径回退 true）。③本仓实测（probe_synthetic_user.py，4052 条 user 消息）：question-echo 4.6%/manually-attached-skills 0.8%/continued-session 0.6%，均低于 20% 阈值 → 噪声过滤候选 excluded（无实测缺口）。④文章可借鉴认知（非代码）：经验需带适用条件+被排除解释、失败归因到具体对象（概念/映射/检索/执行四层）、「读过但没落实」需追踪经验是否改变行为。

### 2026-11-26 09:53 #896z

完成 commit 0ac6081（fix: 续接会话时避免重复选择任务）的 code review：41 项测试全过、ruff 干净、四个 hook 副本哈希一致。核心逻辑为三级恢复（binding > transcript > raw 索引）+ 跳过终态 + 绑定失败重试，实现与测试匹配。发现 2 个 Low（raw 索引回退可能返回过时归属；异步弹框后任意用户文本被当作答案）与 2 个 Info，结论 Approve 不阻塞。

### 2026-11-27 01:07 #7hpa

B4 计划写入门禁与 B5 聚类质量 validator 已实施并完成最终验证，均作为内部模块接入既有 MCP handler、不新增工具。B4 默认 observe，enforce 仅放行 pending 页面或精确 target；按实际 routed page key、计划 schema/hash 身份与当前 centralized 仓分区判定，delete-only 不授权重建；计划外写入落审计且不污染 plan_hash。最终审查修复同 stem 跨仓归因：plan 构建/delete/replan/manifest 查询、删除执行、mark_op_done 与 job ledger 均按当前分区及实际 page key 结算；query/entity/他仓模块页只计 other_written，不误关缺页 job，overview 保留明确例外。旧计划兼容边界已收口：overview 只选 canonical 页；无 key 删除拒绝 query 路径；无 key update 仅唯一安全匹配时授权/结算，显式路径优先、bare stem 歧义保持 pending，并覆盖 notes；canonical overview 可由默认 module 类型正确结算。B5 按完整 scope 文件分块估算 token，父模块聚合后代并集；缺测/逃逸/不可读显式进入 unmeasured，部分缺测不判微页；使用轻量组件元数据与会话签名缓存，异常降级 unavailable，不自动改树。验证：B4 专项 43、B5 专项 20、B1-B5 联合 63、最终 plan/job/guard/centralized/写入路由联合 172、提示词 19；最终全量 1538 passed/2 skipped/1 warning；MCP 契约 121 passed/5 failed（既有 OKF/frontmatter/confirm gate 基线，无新增）；核心文件与新增专项测试 mypy、ruff、diff check 通过；未运行 smoke。已更新后续借鉴清单并保留 B4/B5 两篇 decision draft（待用户 confirm，未自动确认）。本轮未提交、未推送。下一步仅在明确需求下启动 C1/C2/C3，不自动展开。

### 2026-11-27 05:31 #6px5

C3 artifact facts 已实施并验证（2026-11-27）：新增 codewiki/mcp/tools/artifact_facts.py 并接入 analyze_repo，artifact: 事实不进入源码 components/依赖边/module tree；支持纯 artifact 改动增量、centralized per-repo 元数据、失败/截断/遗漏显式化，不执行工程命令或导出环境值/命令正文。独立审查修复 Make 泄漏、路径正则、FIFO 阻塞、CI 误报、TOML 行号等边界。验证：专项 39、相邻联合 76、全量 1577 passed/2 skipped/1 warning；MCP 契约 121/5 与既有基线一致；正式 stdio 工具仍 53 个，临时仓实测 artifact-only 变更且源码 component ID 不变。决策草稿 2026-11-27-artifact-facts-应作为源码图外的确定性事实层.md 保持 draft。下一步按用户授权进入 C2：先 grammar preflight，再 Rust；Rust 已被扩展名/白名单收集但缺 analyzer 分派，拟用独立 tree-sitter-rust wheel 避免首用下载。B1-B5/C3 均未提交推送，C1 继续条件项。

### 2026-11-27 06:34 #obim

C2 Rust 薄适配已完成并验收：CallGraphAnalyzer 解析前 grammar preflight，独立 tree-sitter-rust wheel 与 analyzers/rust.py；保留 src 模块路径、trait impl 唯一方法身份、调用路径和接收者，禁止未知/外部调用尾名误绑。两轮独立审查反例均有回归，专项 25 passed，正式 stdio MCP 新鲜仓 10 组件，MCP 契约 121/5 与基线一致；最终全量 1602 passed, 2 skipped。当前继续 C2 第二语言 Ruby；Rust 决策草稿仍 draft，未提交推送。

### 2026-11-27 07:09 #sdc2

C2 第二语言 Ruby 薄适配已完成并验收：独立 tree-sitter-ruby 0.23.1 + grammar preflight，保留完整 namespace、#/. 方法身份、词法常量/继承作用域与保守接收者推断；跨文件裸调用延迟解析且不做尾名猜测。两轮审查反例已修复。验证：Ruby 专项 43 passed、Ruby/Rust 68 passed、加入 correctness/latest compat 联合 81 passed；真实 Ruby 标准库 19 样本得到 956 组件/2823 关系；正式 stdio MCP 首次 16 组件。增量复测发现并修复 AnalysisCache._SRC_EXTS 缺 .rb/.rs，导致无改动全量误报；修复后 no_changes=true，单文件新增只报 support.rb 与 #report。OKF 契约 121/5 与基线一致。最终全量回归（已纳入缓存修复和两项指纹回归）为 1645 passed, 2 skipped, 1 warning。backlog 已更新，Ruby 决策草稿保持 draft。任务记忆早期摘要已压缩 1 条并保留 20 条。本轮未提交、未推送、未确认草稿；下一语言候选为 Vue SFC，但本轮停在 Ruby 收尾，不自动扩项。

### 2026-11-27 08:47 #xc95

本轮 9 篇决策草稿已由用户明确确认，全部转为 stable/strong：上游借鉴总稿、B1 反向索引、B2 ownership、B3 tree repair、B4 write guard、B5 clustering validator、C3 artifact facts、C2 Rust、C2 Ruby。confirm_note 返回 consolidation_due，但用户未授权聚合，按闸门不执行。最终全量回归为 1645 passed, 2 skipped, 1 warning。已按用户授权新建分支 feat/codewiki-upstream-b1-b5-c2-c3，准备只提交本轮相关代码、测试、清单、确认笔记与当前用户任务记忆，rebase 到最新 origin/develop 后推送。下一语言为 Vue SFC。

### 2026-09-10

teamai-cli 增量调研完成并存档：基线 docs/teamai-cli-调研与借鉴分析.md（2026-08-21 v0.20.0）→ 现 HEAD 9e7adc7（2026-09-10，v0.23.1/v0.24.0-beta.5），250 个新提交。存档为 docs/teamai-cli-增量调研与借鉴分析-2026-09.md。

两个最值得借鉴的合入：①#374 数据分区——~/.teamai/projects/<slug(anchor)>/，slug=basename+sha256 前 16 hex（8hex 不安全有论证），projectAnchor（worktree list 首项，共享身份）与 workspaceRoot（当前检出，资源落点）分离，明确否决 git-common-dir 方案，锁改 O_EXCL+owner token+回收哨兵；②#336 摩擦信号从 CodeBuddy transcript 确定性提取（interrupt/toolReject/toolError 三类，CodeBuddy 需读 messages/*.json blob，'User rejected this command' 只计人拒，isError 只计真失败），可直接移植补 CodeWiki friction_score 恒为 0 的缺口。次要：#375 role×project 正交+learnings 根层共享子目录私有、#304 WASM tree-sitter 可选降级+PARSE_SKIP gap、#368 KB Health 报告。

下一步待用户拍板：①摩擦信号移植 ②分区+锁 ③先立 ADR；以及是否把可复用机制沉淀为 repowiki note。借用项目统一克隆到 D:\repos 的动作只完成 teamai-cli（其余 20 个未克隆，上次批量克隆命令被取消）。

### 2026-09-10

grill 拷问后拍板 teamai-cli 借鉴处置（判据=只有实测缺口才做，Doctrine 归因调优 SOP）：8 个候选 0 个直接做、7 个 excluded、1 个待实测。

初稿两个判断被证伪：①「friction_score 恒为 0 是缺口」——实际 friction.py 已有打分（correction×20+interrupt×20+repeat×15+规模档，min_user_turns=4），且 [tool-error:] 行已由 tool_digest.py:213-237 写进 raw，只是没计数；②「锁缺 owner token」——store.py:166-189 用 OS flock，比 teamai 的 O_EXCL+owner token+陈旧回收更强（后者是无 flock 的替代品）。

#336 探测结果：repowiki/raw 仅剩 8 条、含 tool-error 的仅 1 条，漏检率 0%（阈值 20%），但该会话 score=5 已被覆盖 → excluded，原因「实测无缺口」；附样本量警告：n=1 不足以证否，复测需 keep_raw 积累或改用 repowiki/tasks 更大样本。

其余 excluded 原因：#374 模型相反（我们知识随仓库版本化 vs 他们机器数据搬出业务仓）+ 身份解析我们用宿主 *_PROJECT_DIR 更靠前；#375 分发维度 vs 归属维度（related≠same）；#304 tree-sitter 我们是主线；#368 无趋势数据；#458/#465 无删除用例；#380 无分发形态。frontmatter 三条转自查 checklist 不立项。

处置表已写入 docs/teamai-cli-增量调研与借鉴分析-2026-09.md §6，§1/§2/§3 的初稿判断已就地加修正。待用户确认是否沉淀 lesson 笔记：借鉴调研前先查本仓是否已有该能力，别把「没宣传」当「没做」。

### 2026-09-11

继续「docs 里借鉴过的项目自上次借鉴后的新合入」调研。先跑全景扫描：11 个本地克隆逐个 git fetch + rev-list --count --since=<各调研文档标注的基线日期> origin/HEAD。增量：codebase-memory-mcp 1182、semantica 682、WeKnora 588、OpenViking 268、llm_wiki 183、claude-mem 36、openwiki 34、RepoWiki 23，MindForge / wikiskill / AIO 均 0。全景表写进 docs/claude-mem-增量调研与借鉴分析-2026-09.md 附 A。

本轮深挖 claude-mem（基线 2026-09-02 f92996e/v13.23.1 → d095021d/v13.24.1，36 commit），产出 docs/claude-mem-增量调研与借鉴分析-2026-09.md，处置：7 候选 0 采纳 / 2 deferred / 5 excluded。两项 deferred：①#3898 tool_uses 的四条工程不变量（upsert ON CONFLICT、自读工具跳过、64KB 截断+原文 content_hash、原始 body 只按 id 取）留档，承接 teamai #336 的 per-call friction 计数；②#3960 skill_invoked 技能遥测——本仓 telemetry 只有 hit/adopted/by_file，无技能维度事件，是真缺口，但技能命中率尚未成为任何在办项判定输入，故 deferred 到 skill_creator 验证阶段。核心证伪：claude-mem 新增能力依托「OpenRouter 计费归因 + 插件市场分发」两个本仓没有的前提。

下一轮队列（已排）：OpenViking（268，#4858 输入过滤 / #4900 跨宿主 turn 捕获 / #4779 队列自愈 / #4906 recall 装配，与采集注入同层，候选密度最高）→ openwiki（34，#859 指纹忽略 Windows ctime 漂移、#777/#841 AGENTS.md 托管块）→ WeKnora（588，文档健康检查）。

### 2026-09-11（续）

本轮连带发现一条会推翻旧结论口径的事实：`[tool-error: …]` 行只由 tool_digest 产生，而它在本仓只有两个调用点（_ide_hook.py:268、capture_conversation.py:221），session-end 的 transcript 补采集（capture_session_end.py）不经过 tool_digest。因此 teamai #336 上次实测「8 条 raw 中仅 1 条含 tool-error、漏检率 0%」测的其实是**通道覆盖面**而非漏检率——复测前必须先回答「工具失败信号在几条通道上被采集、各自覆盖多少会话」，否则加大样本只是放大同样偏差。已写进 docs/claude-mem-增量调研与借鉴分析-2026-09.md §1.3。

顺手做了下轮两项的预检（已落文档附 B）：OpenViking #4724（camelCase isError）→ excluded，数据面不同（本仓走 hook payload 的 is_error，他们修 AI SDK/transcript 的 isError），附前瞻提醒：将来若加 transcript 直读通道必须同时认 isError；openwiki #859（指纹忽略 Windows ctime 漂移）→ excluded，本仓指纹基于内容（doc_similarity.compute_fingerprint:109、page_manifest.compute_source_fingerprint:104），不用 stat 元数据。

下一轮开工点：OpenViking 深挖（基线 2026-08-21，268 commit），候选清单：#4900 跨宿主 turn 协议保留捕获、#4906 从装配 prompt 召回、#4858 recall/capture 的可配置正则输入过滤（对照 _FRAMEWORK_NOISE）、#4779 dsh 队列进程内排空自愈、#4907 缺失任务记录视为已删除（对照 task 索引 stale 条目）、#4559 跳过争用的父级新鲜度更新。

### 2026-09-11（整体报告）

11 个借鉴项目全部完成增量扫描，产出 docs/借鉴项目整体增量调研报告-2026-09.md。合计 44 候选：0 采纳 / 15 deferred / 29 excluded。三路并行采集（OpenViking+openwiki / WeKnora+llm_wiki / CBM+semantica+RepoWiki），本仓对照与裁决由主 Agent 完成，子代理只做事实采集。

三条结论：①一半以上候选本仓早有等价物——最典型是 OpenViking 的 auto-recall 预算机制，本仓 codewiki/mcp/tools/injection_budget.py:1 的 docstring 第一行就写着「V2, OpenViking auto-recall 借鉴」，已落地；另有 deprecated≈墓碑、内容指纹 upsert、多信号确定性排序、git≈修订历史等 6 个样本，坐实「借鉴调研先证伪」那条 stable 笔记。②他仓集体往服务端/队列/多租户走，本仓是本地 markdown + git + 同步 MCP，属主动不同（未知 task_id 显式报错、stale 索引就地跳过）。③真主线是「成本/预算从软约束变硬约束」（CBM 无损分页、WeKnora 砍 LLM 重排、llm_wiki 早停、OpenViking 超预算丢弃、RepoWiki 扫描预算），本仓 injection_budget 在注入侧已就位，空档在扫描侧预算与 deprecated 防重灌。

15 项 deferred 分三类：留档照抄（#1-9）、转其他任务裁决（#10 CBM workspace manifest 审批 → 多仓工作区）、自查项（#13 wikilink 重写代码围栏、#14 ADR 是否整文件重写、#15 deprecated 是否会被新 ingest 复活）。

口径提醒：提交数 rev-list --count（含 merge）与 --no-merges 差异很大（CBM 1182 vs 727），报告里已写明，以后别当矛盾。

### 2026-09-12

HL-Mem 调研（docs/HL-Mem-调研与借鉴分析.md，基线 v1.1.7/aa5d0688）经 grill-with-docs 两轮拷问定稿：16 候选处置不变（4 absorbed / 5 deferred / 7 excluded），但范围收窄：①A1 冲突一等对象——源码实测剥离≈重写（纯函数约 1800 行 + SQLite 绑定约 2200+ 行），自动发现依赖 slot 注册表底座被排除，只做手动声明；定稿顶级 conflicts/ 页面类型（ADR-0007，否决 notes/conflicts/ 与双向引用），已立项任务「冲突一等对象」，排期与 Phase5 批次二错开。②A3 反馈延寿降档并入 Phase5（公式 BayesianUsefulnessPolicy 37 行纯函数可直抄，三层夹紧），任务记忆已转注 Phase5。③A2 能力矩阵落点定 docs/capability-matrix.md（非 repowiki，产品元文档不进知识语料），已编写：首次登记约 20 项，发现 registry 描述 22 vs 实际 24 checks 漂移待修。④A4 三态门控（tri-state gate）已落 CONTEXT.md glossary + CONTRIBUTING.md。⑤C7 降级口径（检索无结果明确回「未检索到」）已落 agents.md 使用建议第 5 条。克隆已归位 D:/repos/hl_mem；Experience 通道已立项「Experience-通道调研」待排期。二次复核修正报告三处事实错误：矩阵实为 7 列 39 条非 4 列 37 条；C8 与 Phase5 T7 的矛盾已补注；补记 service_health 槽位二次夹紧。

### 2026-09-12（存储与压缩机制专题）

六参考项目（hl_mem/claude-mem/mem0/CBM/OpenViking/teamai-cli）存储与压缩机制对比已完成，产出 repowiki/wiki/queries/参考项目记忆存储与压缩机制对比-2026-09.md。要点：①「压缩」四分类（写入时/归纳式/上下文预算/衰减）不可混用；②全场只有 teamai-cli self 模式与本仓一样知识随业务仓 git 版本化；③OpenViking merge_policy 与本仓 Doctrine 合并纪律几乎逐句对应（独立收敛互证）；④HL-Mem Mental Model 归纳 ⇔ compact_task_memories 同一形态。

**重要修正（作废一条转注）**：整体调研报告 deferred #10「CBM workspace manifest 审批键」系误读——CBM 的 workspace manifest 实为 Rust Cargo.toml workspace 清单（跨 crate 导入解析，pass_lsp_cross.c:478-488），与审批/多仓无关。此前转注到「多仓工作区」任务的这条参考已失效，实施多仓工作区时勿再消费该参考。

### 2026-11-27 09:36 #7rko

C2 第三语言 Vue SFC 薄适配已完成并验收：新增确定性 SFC 扫描器，脚本外等长掩码后复用 JS/TS analyzer，保留原文件行号；提取组件、Options API 成员、脚本函数、导入与模板组件/表达式边。组件与脚本同名时使用 path::script.Name 并重映射关系；Vue caller 仅对完整 path::symbol 放行精确跨语言命中。审查发现的插值伪标签、ID 冲突、跨语言精确解析、前 64KiB 指纹漏检均已先红后绿修复；指纹改为全文流式 SHA-256，旧缓存升级后首次可能全量重算。验证：Vue 专项 25 passed，Vue/Rust/Ruby/correctness/latest compat 联合 106 passed，最终全量 1670 passed/2 skipped/1 warning；ruff、mypy、diff check 通过；MCP 契约 121/5 与既有基线一致；正式 stdio 首次 9 组件，无变更与单文件新增 ArticleList.reset 增量均正确。backlog 已更新，Vue 决策笔记保持 draft 未确认。本轮未提交、未推送；下一语言候选 Go package-aware 仍按需求触发，不自动展开。

### 2026-11-27 10:44 #n88f

Go package-aware 薄适配已完成：保留本地组件 ID 与 route extractor，新增 directory/package 精确解析、go.mod/local replace、仓库 import 可见性、隐式 interface method-set，以及 MCP/watch 增量缓存 package 合并；外部 qualified type、同名包函数/方法、陈旧 interface 边均有回归覆盖。Go 专项 25 项、相邻联合 131 项通过；最终全量 1694 passed, 2 skipped, 1 warning（第 25 项 Go 反例在全量收集后新增，已由专项覆盖）；正式 stdio MCP 首次/无变更/单文件增量通过。边界：interface 仅按方法名集合近似，不校验完整签名/指针接收者/嵌入接口；dot/blank import 保守。下一步：保留 Go 决策草稿待用户确认；提交与推送仍需用户明确授权。

### 2026-11-27 13:45 #9a8p

> [superseded 2026-11-27 by #4yy7]

C2 Scala package-aware 薄适配已完成代码与专项验收：独立 tree-sitter-scala wheel、grammar preflight、声明 package/import 精确解析、companion `$` 身份、Scala 2/3 类型/方法、wildcard 唯一命中、重载弃权、词法 receiver 作用域、缓存嵌套身份与旧边重裁决、继承基类优先及顶层后备、构造参数字段链 package 固化；`.scala/.sc` 与 SBT manifest/service/artifact 接入已同步。三轮审查反例均有回归，Scala 专项 42 passed、语言联合 173 passed，ruff/mypy/diff check 通过；OKF 为既有 121/5。正式 stdio MCP 首次 5 组件、无变更及单文件 5→6 增量通过。决策草稿 notes/2026-11-27-scala-analyzer-应保留组件-id-并按声明-package-精确解析.md 已可检索且保持 draft。最终全量仍在运行；未提交、未推送、未确认草稿。

### 2026-11-27 14:06 #4yy7

C2 Scala package-aware 薄适配已完成并验收：独立 tree-sitter-scala wheel、grammar preflight、声明 package/import 精确解析、companion `$` 身份、Scala 2/3 类型/方法、wildcard 唯一命中、重载弃权、词法 receiver 作用域、缓存嵌套身份与旧边重裁决、继承基类优先及顶层后备、`super` 基类解析、构造参数字段链 package 固化；`.scala/.sc` 与 SBT manifest/service/artifact 接入已同步。三轮审查反例均有回归：Scala 43 passed、语言联合 174 passed、Scala/artifact 82 passed，ruff/mypy/diff check 通过；OKF 为既有 121/5。正式 stdio MCP 首次/无变更/单文件 5→6 增量通过，super 临时仓只连 lib.Base.work。最终全量（清除本机代理环境后）：1738 passed, 2 skipped, 1 warning。决策草稿 notes/2026-11-27-scala-analyzer-应保留组件-id-并按声明-package-精确解析.md 已可检索且保持 draft。边界：完整类型推导、宏、动态派发、重载目标选择、多基类线性化，以及跨文件同包重载/顶层后备仍保守。未提交、未推送、未确认草稿。

### 2026-11-27 15:40 #ya5h

Dart/Flutter C2 语言切片完成：独立 tree-sitter-dart wheel 与 grammar preflight，新增 dart.py/dart_imports.py/dart_flutter.py，实现 visible-scope 解析（相对与 package URI、prefix、show/hide、export 闭包、part、library 私有名、词法遮蔽、继承成员与字段链），接入 CallGraph、SQLite metadata 原始引用复核、旧缓存迁移、pubspec 语义依赖、CLI/prompt/review/服务识别/artifact facts。Flutter 仅做轻量确定性分类，不执行 analyzer 或生成代码，不承诺完整类型推导/泛型/动态派发。验证：Dart 专项 36 passed；语言/artifact/tree repair 联合 257 passed；最终全量 1774 passed, 2 skipped, 1 warning；ruff check/format、git diff --check、新增三模块 mypy 通过；OKF 保持 121 passed/5 failed 既有基线。正式 stdio MCP 验证首次分析、无变更、单文件增量、package/prefix/part 边、pubspec 改名与 artifact-only pubspec，工具总数仍 53。决策草稿：repowiki/notes/2026-11-27-dart-analyzer-应按-library-visible-scope-精确解析并持久化原始引用.md（draft，未确认）。当前代码、文档与草稿均未提交、未推送；未开始 Zig。

### 2026-11-27 16:51 #allr

> [superseded 2026-11-27 by #l5so]

C2 Zig 薄适配已实现并通过专项/联合/正式 MCP 验证，最终全量回归正在运行。使用独立 tree-sitter-zig==1.1.2 wheel，保留 path::logical_name 组件 ID；覆盖容器、泛型、@import/re-export、build.zig addModule、调用/实例化/类型边。未知 receiver 不猜尾名；任一 Zig 变化全量重解析 Zig，非 Zig 增量合并存活缓存。alias-only 文件纳入指纹，build.zig 同时是 build artifact 并提取源码引用。独立审查发现并修复显式类型初始化漏调用边、block 局部类型污染、删除文件指纹永久误报三个问题。Zig 专项 21 passed，语言/artifact/tree/change 联合 273 passed，ruff/mypy/diff check/lock check 通过；OKF 121/5 为既有基线。正式 stdio 首次 4 组件，无变更、单文件增量、build.zig 映射、alias 删除后下一轮收敛均通过。backlog/调研已回填，Zig 决策笔记保持 draft 未确认。本轮未提交、未推送；下一语言候选 Lean 4 不自动展开。

### 2026-11-27 16:59 #l5so

C2 Zig 语言薄适配已完成并验收：使用独立 tree-sitter-zig==1.1.2 wheel 与 grammar preflight，保留 <relative_path>::<logical_name> 组件 ID；覆盖容器/泛型、@import/re-export、build.zig 两种 addModule 映射、调用/构造器/实例化/类型引用。Zig caller 只接受完整 ID 精确解析；任一 Zig 变化保守全量重解析，非 Zig 增量合并存活缓存。alias-only 指纹、删除清理、block 局部作用域、显式类型初始化调用边均已修复；build.zig 同时作为 build artifact 并提取源码引用；源码发现、CallGraph、watch、CLI、prompt、review、服务识别与 artifact facts 已接入。验证：Zig 专项 21 passed、联合 273 passed、最终全量 1795 passed/2 skipped；ruff、mypy、diff、lock、wheel 构建通过；MCP 契约 121/5 为既有基线；正式 stdio 首次/无变更/单文件/build.zig/artifact/删除收敛通过。backlog 与决策草稿已更新，草稿未确认。本轮未提交、未推送；下一语言候选 Lean 4 不自动展开。

### 2026-11-27 18:36 #d1qq

C2 Lean 4 薄适配已完成：保留 path::logical_name 组件 ID，新增 header scanner、Tree-sitter 引用提取与 import/open/export/private/protected 精确 resolver；六平台 ABI 15 grammar 随包离线分发，Tree-sitter 下限升至 0.25.0。任一 Lean 变化全语言重解析，非 Lean 增量合并存活缓存；import-only 指纹、watch、Git 删除收敛、Lake 服务识别与 artifact facts 均已接入。Lean 专项 103、Lean/watch 最终 113、联合 179、全量 1898 passed/2 skipped；mypy 0 error，ruff/锁文件/diff 检查通过；最终 wheel 六平台 SHA-256 全通过；正式 stdio MCP 首次/无变更/单文件增量通过；MCP 契约维持 121/5 既有基线。决策草稿 repowiki/notes/2026-11-27-lean-analyzer-应按-import-可见域精确解析并离线分发-grammar.md 保持 draft，待用户逐篇确认；下一步仍需用户明确授权提交/推送。

### 2026-11-27 21:24 #ee8z

真实 MCP 复核完成：通过正式 ClientSession/StdioServerParameters 启动 codewiki 5.16.8，握手成功且列出 53 个工具；临时 Git+Lean/Makefile 仓库验证首次 3 组件、无变更 no_changes=true、Point 单文件新增 Geo.jump、Main 单文件增量、list_components/list_dependencies 精确解析到 Geo.jump、Makefile artifact-only 变更及 get_task_context（pending_raw_count=0）均通过。MCP handler 契约仍为 121 passed/5 failed 既有基线。Qoder 宿主连接器状态另经 manage_app_mcp 只读查询：codewiki 当前 disabled、toolCount=0，所以服务端可用不等于宿主工具目录已挂载；未擅自启用或修改连接器配置。

### 2026-11-27 22:24 #p2d6

完成 code-review 修复：语义 manifest（go.mod/pubspec.yaml）变化通过 analyze/watch 共用 helper 失效对应语言全部缓存 caller；go.mod 纳入 mtime/fingerprint，vendor/testdata 嵌套 manifest 不参与指纹。Vue 缓存节点仅复核语言相关边，并用 _parsed_files 保留指向未重解析且仍存在 JS/TS 缓存目标的有效边。Zig 统一 realpath 边界和 canonical 相对 ID，覆盖 build.zig root、import、re-export、declared_in，拒绝绝对/../符号链接逃逸；修正 build.zig 测试素材。验证：八语言+watch 345 passed；相邻分析/缓存 66 passed；清理 NO_PROXY 后全量 1911 passed/2 skipped；ruff/format/diff check 通过；mypy 16 个 cache.py 既有错误；MCP 契约 121 passed/5 failed 既有基线。未提交、未推送。

### 2026-11-28 05:23 #5w2t

已按用户授权提交并推送代码：commit fae7731e8fd428810ee7c7aaf4318f0a24eef3ca（feat: 扩展多语言分析并加固增量缓存），分支 feat/codewiki-upstream-b1-b5-c2-c3，本地与 origin 同步。提交仅含 codewiki/、pyproject.toml、uv.lock 和六个新增语言测试；未纳入文档、repowiki 笔记/任务记忆、telemetry、.qoder/settings.json、work/ 等并行会话产物。全量回归 1911 passed/2 skipped。

### 2026-11-28 05:25 #5126

非代码交付物已按用户授权提交并推送：commit 9ec88b5da362ab7909d0ddea653234b25aa893dc（docs: 归档多语言适配决策与任务记忆），包含 2 份任务文档、8 篇决策/经验草稿和本任务记忆；分支 feat/codewiki-upstream-b1-b5-c2-c3 已与 origin 同步。仍排除 .qoder/settings.json、telemetry、会话 raw、work/、wiki log 与并行用户记忆等运行时/并行会话产物。
