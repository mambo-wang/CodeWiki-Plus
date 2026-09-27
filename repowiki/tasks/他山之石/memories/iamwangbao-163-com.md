## 早期记忆（摘要）

## 早期记忆（摘要）

2026-09-04 ~ 09-19 他山之石调研结论摘要：

【已完成研究】①caveman：SKILL.md 单事实源经三条链路注入（hooks/Native Pack/skills 目录），SessionStart stdout 隐藏注入 + compact 重注入防漂移；2 条 architecture 笔记 stable；技能已装 ~/.codebuddy/skills。②ponytail：三层加载档位 T1 指令/T2 技能/T3 hooks，CodeBuddy 属 T2；机制草稿已 reject。③wikiskill：SKILL 自动生成定档方案 C 半闭环（单向编译器 B：confirmed notes/scenarios → SKILL.md draft → 确认闸门 → .codebuddy/skills/），不建自动评分门控。④skill-creator 设计定稿：四 mode prepare/submit/install/retire、两区制（草稿 repowiki/skills/ 不生效 → install 到 .codebuddy/skills/）、容量硬顶 12、批次最多新建 1；consolidate_notes 产知识层 scenario，skill_creator 产行为层，单向下游。未决：Q10 回流验证判定、Q11 lint 规则与容量取值。⑤humanizer v2.11.2 已装用户级。⑥ponytail/caveman 融合方向定档但未落地。

【teamai-cli（09-10）】v0.20.0→v0.23.1，8 候选 0 采纳。判据=只有实测缺口才做。证伪：friction_score 已有打分（friction.py），锁已有 OS flock（store.py:166-189）。#336 实测无缺口 excluded（n=1 样本警告）；#374 模型相反。

【整体增量调研（09-11）】11 项目 44 候选 → 0 采纳/15 deferred/29 excluded，报告 docs/借鉴项目整体增量调研报告-2026-09.md；claude-mem 细节另存 docs/claude-mem-增量调研与借鉴分析-2026-09.md（对方依托 OpenRouter 计费归因+插件市场分发，本仓无此前提）。方法论三条：①一半候选本仓早有等价；②他仓服务端/队列/多租户取向不是缺口；③主线是成本/预算从软约束变硬约束，本仓空档在扫描侧预算与 deprecated 笔记是否被新 ingest 复活。deferred 三类：留档照抄 9、转多仓工作区 1（⚠️作废：CBM workspace manifest 实为 Rust Cargo 清单，与审批无关，勿再消费）、自查 3（wikilink 代码围栏切分/ADR 是否整文件重写/deprecated 是否被复活）。

【口径修正（重要）】[tool-error] 只由 tool_digest 产生，仅 _ide_hook.py 与 capture_conversation.py 两个调用点，session-end 补采集不经过它 → 之前「漏检率 0%」测的是通道覆盖面而非漏检率。

【流程与坑】借鉴项目统一克隆到 D:\repos；蒸馏 subagent 自报笔记状态不可信，须 get_task_context related_notes 复核；CodeBuddy UserPromptSubmit 是否喂 stdin/消费 stdout 未真机验证（后已实施 active-settle 薄触发并真机验证）。

【graphiti（09-18）】借鉴落地为 ADR-0011（归产品维护）：蒸馏 LLM 输出防御性校验（解析失败保留 raw + parse_failed 状态）+ 中文标题分词复用 retrieval.tokenize + 缺字段 note 剔除记 invalid_note。Round 2：_is_title_subset 降级规则——真子集且 sim∈[0.6,0.8) 降级弱冲突带，≥0.8 近全同改写走快路径。教训：改判定带阈值后必须实测真实标题对分布。

【llm-wiki-compiler（09-18）】llmwiki v1.3.0，通用知识编译器。可借鉴认知：eval 量化门禁、freshness 四态、意图日志原子性、profile-as-data；不借 TS 栈与 CLP 全量 FSM。处置笔记 stable。

【cognee（09-18~19）】8 借鉴点全部证伪 0 采纳（6 条本仓已有等价：pending-status≈水位线、tool_digest≈LIVE 快路径、secret_redact≈脱敏、submit 单次多产出、usage_heat≈流式加权、file_lock+noop≈抢锁放弃；2 条语义不同）。价值定位「独立收敛互证」。报告 §三/§五已按证伪改写。

【memos（09-19）】MCP 协议合规工程最高水平。absorbed 1 条挂起搭车：registry 加 annotations 参数，destructive 集合={edit_doc_file, reject_note, delete_task}，等下次 registry 契约变更顺路落地，不单独立项。deferred 3（structuredContent 与错误形状同根、任务级 eval 并入质量量化主线）、excluded 6。

【supermemory（09-19）】开源仓是客户端/集成层，核心引擎闭源。12 候选 0 立即落地。「declined 即 forgotten」本仓已有更精细三层等价（handler 跳过 deprecated + 索引层 -0.35 降权 + 蒸馏去重豁免；曾误判降权是死代码被代码核对证伪）。derives/isLatest deferred；SMFS 归 Cli能力、MemoryBench 归质量量化、SKILL.md 范本归技能提取。

【hindsight（09-19）】vectorize-io 生物拟态记忆，重基建重 LLM，与本仓前提相反。absorbed 2：①索引抑制——注入块列知识页清单致 40 轮 0 次搜索（本仓只列 3 条最新笔记已部分符合）；②consolidation prompt 两规则——每条 op 必带 reason、NO COMPUTATION。deferred 2：knowledge page delta 刷新、4 臂检索+RRF（等 query_wiki 多路召回需求）。

【遗留待办】2026-09-04 旧 draft「在 CodeBuddy 使用跨 Agent 技能」保留待定未裁决；IDE hook 修复已提交推送待验收；09-11 的 3 条蒸馏草稿待 confirm（版本化资产架构事实/小样本不能当证否/增量调研 SOP）。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-09-24，共 30 条。

### 2026-09-19 23:11 #ar98

letta 调研完成（2026-09-19）：letta-ai/letta main 分支只是 landing page，当前实现在 letta-ai/letta-code（TS 编码 agent）。报告落盘 docs/letta-调研与借鉴分析.md。核心机制：.letta 目录 MemFS（Markdown+frontmatter）、memory 工具写入即 git commit 且 reason 必填、reflection 子代理默认每 25 step 触发在隔离 worktree 改记忆、mergePolicy auto/explicit 显式合并、失败压制自动反思、记忆与 Skill 同通道沉淀。借鉴点：worktree 隔离合并、commit-on-write+reason、step-count 触发、失败压制、限额集中管理（directory-limits.ts 模式）。不借鉴：云端 MemFS 同步、LLM 自由编辑记忆、遥测、Mods。

### 2026-09-19 23:23 #hge5

## hindsight 借鉴 grill 拷问定案（2026-09-19）
- grill 五题全按推荐落定：①absorbed 语义=必须有可指认落点（prompt/文档/代码行），否则降级 deferred；②两条规则只落 _DISTILL_SYSTEM；③reason+NO COMPUTATION 合并成一条；④deferred 不定触发信号（deferred 是留档不是 backlog）；⑤索引抑制不动代码。
- 已落地：_DISTILL_SYSTEM 新增第 6 条纪律「Reasoned and literal」（codewiki/mcp/tools/distill_conversation.py），tests/test_distill_p1.py 补断言，全量 1169 passed 零回归。
- ADR-0012 已写入 docs/adr/；decision 草稿笔记已补「落地」章节；调研报告处置表 #3 改为 absorbed（已落地）。
- 待办：两条草稿笔记（索引抑制 pitfall、distill 规则 decision）仍待用户 confirm_note。

### 2026-09-20 10:56 #d489

letta 借鉴 grill 拷问定案（2026-09-20）：ADR-0013 已落盘 docs/adr/0013-letta-stable-reason-and-limits-module.md。落地两项：① ingest_note 加可选 reason 字段进 frontmatter，status=stable 直写时必填（draft/confirm_note/batch_set_status/add_task_memory 豁免）；② 新建 codewiki/mcp/tools/limits.py 收敛 task_manager 压缩阈值组（40 条/24KB/keep 20/摘要 4096）与写入窗口软限（5 条），lint_wiki 加 threshold_drift 检查防文案漂移。排除四项：worktree 隔离（consolidate 已有两段式）、step-count 触发（轮与 step 不同构）、失败压制（触发稀疏，自我修正推翻初判）、技能同通道（skill_hint 已有）。顺序 E 先 B 后（同文件 registry.py 避免冲突）。调研报告 §四已同步处置状态。

### 2026-09-20 11:17 #vj5o

ADR-0013 方案 B 修订（2026-09-20）：ingest_note stable 直写除 reason 必填外，新增可选 evidence 字段（test_ref/commit_ref/reviewed_by），复用 confirm_note 语义——提供时记 metadata.verification 并升 confidence_level=strong。分工：reason 管可见性（防静默，自报意图声明，可被编造），evidence 管验证（人工可核验的结构化锚点）。ADR 已补能力边界声明。另：聚合 frontmatter 折行 pitfall 笔记已确认入库（stable）。

### 2026-09-20 12:03 #l5dy

ADR-0013 E 项实施完成（2026-09-20）：① 新建 codewiki/mcp/tools/limits.py（压缩阈值组 40/24KB/keep20/4096 + 写入窗口软限 5 + 压缩级别 0.75/0.875）；② task_manager.py 改为 import + 历史私有名 re-export，行为等价；③ wiki_lint.py 新增 threshold_drift 检查（扫 registry.py/prompts.py 文案 vs limits.py 常量，锚定正则避免 50KB 误报）+ registry schema enum 同步；④ 首日即抓到真实漂移：registry.py:2953 compact 描述写 2048 实际常量 4096，已修文案；⑤ 新增 tests/test_threshold_drift.py 6 用例全过，全量 1168+6 passed。B 项（ingest_note reason 必填 + evidence 可选）待实施。

### 2026-09-20 12:25 #5c41

ADR-0013 B 项实施完成（2026-09-20）：① note_ingest.py 加 reason 校验（status=stable 必填，缺失拒绝并提示改走 draft→confirm；draft 可选）+ evidence 处理（复用 confirm_note 语义：test_ref/commit_ref/reviewed_by，提供时升 confidence_level=strong 并记 metadata.verification，未知 key 拒绝）；② reason/verification 写进 frontmatter metadata；③ registry.py ingest_note schema 加 reason/evidence 参数描述，status 描述同步更新；④ 新增 tests/test_ingest_reason_evidence.py 7 用例，修 4 处既有裸 stable 调用补 reason；⑤ 全量 1182 passed。ADR-0013 全部落地（E+B）。

### 2026-09-20 19:39 #ki12

完成 hook/AGENTS.md 竞品调研（claude-mem、hindsight、teamai-cli、letta-code、openwiki、better-harness、caveman、project-cairn）。核心结论：①AGENTS.md 应瘦身成路由层（cairn ≤60 行预算 + 文档职责表），细节外置 wiki 按需检索；②task-memory 协议存在 AGENTS.md 块与 SessionStart hook 双通道重复注入，应单点收敛（建议保留 hook 硬通道，AGENTS.md 留一行指针）；③hook 可借鉴 teamai-cli golden fixture 钉渲染输出、claude-mem 原生 async:true（需真机验证 CodeBuddy 支持）；④明确不借 claude-mem 六事件全采集（噪音）、inline bash 路径解析、letta commit-on-write（模型相反）。下一步：向用户确认优化方案后落地。

### 2026-09-20 20:43 #f5gt

ADR-0015 落地完成：AGENTS.md 托管块瘦身与注入通道收敛。改动：①zh.yaml/en.yaml CodeWiki 块 89→45 行（保留采纳声明/标注依据/语言闸门，纠正识别三步流程并入使用建议第 3 条，归档示例 JSON 删除指向 get_prompt(ingest-note)，路由表压成单行）；②prompts.py _TASK_MEMORY_AGENTS_SECTION 40→8 行指针式（hook 注入优先，未注入时按 task-workflow prompt 执行，全文收敛到 hook 硬通道+prompt）；③本仓 AGENTS.md 163→97 行，Team memory fusion 节外移到 repowiki/wiki/team-memory-fusion.md；④本仓两块用产品渲染器刷新（_build_section + upsert_agents_section）。全量测试 1109 passed。golden fixture（D5）deferred 到下次动 ide_config.py 前补。待办：commit 未做（等用户确认）。

### 2026-09-20 21:26 #os6r

ADR-0015 已提交推送：cb305c7 feat: ADR-0015 AGENTS.md 托管块瘦身与注入通道收敛（5 文件，+102/-196），已推送 origin/develop。排除项：repowiki/schema.yaml（auto-sync 副作用重写，非本次改动）、.codebuddy/memory（工作记忆）。后续 deferred 项：①UserPromptSubmit 薄触发提升主动沉淀命中率（方案已给出，用户暂不做）；②golden fixture 测试（下次动 ide_config.py 前补）。

### 2026-09-21 10:08 #y1a8

UserPromptSubmit active-settle 薄触发已实现（ADR-0015 后续，grill 2026-09-21 两轮）：①_ide_hook.py 加 ACTIVE_SETTLE_REMINDER 常量（混合措辞：回看补写+前瞻自查）与 _repo_has_active_tasks()（读 tasks/.index.json，fail-open）；②_handle_user_prompt 输出改为技能提示与提醒拼接（技能在前）；③test_skill_match.py 补 5 条断言（注入/无任务静默/非 active 静默/拼接顺序/索引损坏 fail-open）。全量 1131 passed。决策记录：PreCompact 不做（Q1 超集）、Stop+block 不做（无 transcript 无法验证+循环风险）、触发条件用「仓库有 active 任务」代理信号（绑定落盘方案 deferred）。待办：commit 未做。

### 2026-09-21 11:12 #iyy2

SubagentStart hook 评估定案（他山之石后续）：不做。理由：①CodeBuddy 是否支持该事件未验证；②沉淀责任应留在主 Agent——subagent 上下文窄、无任务级视野做四问过滤、跑完即销毁，直接落盘会绕过确认闸门（笔记）或灌爆任务记忆（直写）；③主 Agent 收到 subagent 返回值的那一刻就是天然停顿点，已被 active-settle 通道覆盖。正确增强点是「发起 subagent 的返回值约定」：已增补进 get_prompt(task-workflow) 的「会话进行中」节——主 Agent 派发子任务时 prompt 末尾加「返回结果时报告三件事：做了什么、关键发现、值得沉淀的经验（若有）」，过滤/查重/落盘全在主 Agent。distill-worker 是特例不冲突。全量测试 1130 passed（1 个并发测试 flaky 单独跑通过）。待办：commit 未做。

### 2026-09-21 15:18 #6txu

Workspace Conventions 模板瘦身完成（ADR-0015 同款收敛）：①两个模板（agents-md-workspace-centralized.md.tpl / agents-md-workspace.md.tpl）的「新业务仓接入清单」8→2 行——手工三步与 add_workspace_repo 工具事务式同步四处重复，收敛为工具名+get_prompt(add-workspace-repo) 指针，手工兜底三步移入该 prompt 注意事项；②分支策略 3→1 行（删解释留规则）。48→40 行。全量 1136 passed。待办：commit 未做。

### 2026-09-24 20:55 #fnyx

完成 agentmemory（rohitg00/agentmemory）源码调研并存档 repowiki/wiki/queries/agentmemory-调研.md。核心发现：重运行时路线（常驻 iii-engine、hooks 全量自动采集、264 函数、BM25+向量+图 RRF 检索、四层记忆巩固+衰减驱逐）。三项借鉴候选全部不立项：合成压缩→absorbed（与确认闸门冲突）；自动衰减驱逐→deferred（与「候选必有去向」Doctrine 冲突，等 lint_wiki low_adoption 数据）；slots 固定槽位→excluded（MEMORY.md+AGENTS.md+任务记忆三件套已覆盖）。总体判断：全自动采集/巩固/驱逐路线 CodeWiki 明确不走，本次调研价值在确认架构边界。

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

### 2026-09-25 21:35 #dvsa

skill hint 评估裁决（2026-09-25）：蒸馏 worker 提示笔记「hook 注册命令用 python -m 包内入口」命令密度 4 可能值得编译成技能。经 skill_creator prepare + 材料实读裁决不编译（no_action 已提交）：① 该笔记是 architecture 类型，不在 skill 素材边界内（素材只收 scenarios + stable pitfall/lesson/decision）；② 内容是结构认知（回答「hook 行为更新要不要改 settings.json」），非可触发行为指令，编译无触发场景。顺带发现：prepare 标记 worth_compiling=true 的同主题 pitfall「全局 codewiki.exe 无法 import 本地包，install-hooks 需用 python -m codewiki.cli.main」——deferred：信息量单薄（一条命令选择），单独成技能碎片化，等同类素材积累后并入。

### 2026-09-25 22:03 #o805

agentmemory Round 2 小优化 grill 定案（2026-09-25，用户裁决「按推荐」）：① MCP 工具面裁剪开关立项（P2）——CODEWIKI_TOOLS=core 环境变量，registry 加 filter，参考 agentmemory core-8 思路按本仓场景重定义核心集，归产品维护；② 会话多样性约束 deferred（等 lint_wiki 重复笔记数据）；③ RRF 融合 excluded（单流 BM25 无第二路可融，未来加向量检索时再议）；④ related_notes 语义召回 excluded（注入场景要确定性，task_id 精确匹配是特性不是缺陷）。已核对本仓等价物：同义词扩展（ontology.yaml）、CJK 分词（jieba+regex 降级）、SHA-256 去重（capture content_hash）均已有，无需行动。调研文档已更新第六节+处置表（repowiki/wiki/queries/agentmemory-调研.md）。
