## 早期记忆（摘要）

## 早期记忆（摘要）

2026-09-04 ~ 09-11 早期他山之石调研结论摘要：

【已完成研究】①caveman：SKILL.md 单事实源经三条链路注入（hooks/Native Pack/skills 目录），SessionStart stdout 隐藏注入 + compact 重注入防漂移；2 条 architecture 笔记已 stable；技能已装 ~/.codebuddy/skills。②ponytail：三层加载档位 T1 指令/T2 技能/T3 hooks，CodeBuddy 属 T2；机制草稿已 reject。③wikiskill：SKILL 自动生成定档方案 C 半闭环（单向编译器 B：confirmed notes/scenarios → SKILL.md draft → 确认闸门 → .codebuddy/skills/），不建自动评分门控。④skill-creator 设计定稿：四 mode prepare/submit/install/retire、两区制（草稿 repowiki/skills/ 不生效 → install 到 .codebuddy/skills/）、容量硬顶 12、批次最多新建 1；consolidate_notes 产知识层 scenario，skill_creator 产行为层，单向下游。未决：Q10 回流验证判定、Q11 lint 规则与容量取值。⑤humanizer v2.11.2 已装用户级。⑥ponytail/caveman 融合方向定档但未落地。

【teamai-cli 增量调研（09-10）】v0.20.0→v0.23.1（250 commit），8 候选 0 采纳。grill 后拍板：判据=只有实测缺口才做。两个证伪：friction_score 已有打分（friction.py），锁已有 OS flock（store.py:166-189）强于 teamai 的 O_EXCL 替代品。#336 实测无缺口 excluded（n=1 样本警告：复测需 keep_raw 或 repowiki/tasks 更大样本）；#374 模型相反（知识随仓库版本化 vs 机器数据搬出业务仓）。

【整体增量调研（09-11）】11 项目全覆盖，44 候选 → 0 采纳 / 15 deferred / 29 excluded，报告 docs/借鉴项目整体增量调研报告-2026-09.md。claude-mem 细节另存 docs/claude-mem-增量调研与借鉴分析-2026-09.md（36 commit，7 候选 0/2/5，对方能力依托 OpenRouter 计费归因+插件市场分发，本仓无此前提）。三条方法论结论：①一半候选本仓早有等价（injection_budget.py:1 docstring 即借鉴自 OpenViking）；②他仓往服务端/队列/多租户走，本仓本地 markdown+git+同步 MCP 是主动不同取向，此类不是缺口；③主线是「成本/预算从软约束变硬约束」，本仓空档在扫描侧预算与 deprecated 笔记是否被新 ingest 复活。15 项 deferred 分三类：留档照抄 9、转多仓工作区 1（后证实系误读作废：CBM workspace manifest 实为 Rust Cargo 清单，与审批无关，勿再消费）、自查项 3（wikilink 代码围栏切分 / ADR 是否整文件重写 / deprecated 是否被复活）。

【口径修正（重要）】[tool-error] 只由 tool_digest 产生，仅 _ide_hook.py 与 capture_conversation.py 两个调用点，session-end 补采集不经过它 → 之前「漏检率 0%」测的是通道覆盖面而非漏检率，先定覆盖面再谈样本量。

【流程与坑】借鉴项目统一克隆到 D:\repos（余约 20 个待补）；蒸馏 subagent 自报笔记状态不可信，须 get_task_context related_notes 复核；CodeBuddy UserPromptSubmit 是否喂 stdin/消费 stdout 未真机验证。

【遗留待办】2026-09-04 旧 draft「在 CodeBuddy 使用跨 Agent 技能」保留待定未裁决；IDE hook 修复（BOM 容错+stderr 诊断）已提交推送待验收。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-09-19，共 12 条。

### 2026-09-11 08:52

待办：3 条蒸馏草稿待用户 confirm（repowiki 版本化资产架构事实 / 小样本不能当证否 / 增量调研 SOP），第 2 条建议补入「通道覆盖面」这一层；本地 develop 领先 origin 7 个提交未推送。

### 2026-09-12 08:28

### 2026-09-12 08:56

### 2026-09-18 15:11 #mxom

graphiti 调研闭环：报告落盘 docs/graphiti-调研与借鉴分析.md；借鉴点经 grill 裁决后实施 ADR-0011（归产品维护）——蒸馏 LLM 输出防御性校验（解析失败保留 raw + parse_failed 状态）+ 中文标题分词复用 retrieval.tokenize（弱冲突带对中文生效）+ 缺字段 note 剔除记 invalid_note。全量测试 1165 passed。不做：检索 recipe 预设化、退役时间维度。

### 2026-09-18 16:44 #seek

ADR-0011 Round 2 完成（grill 第二轮）：实测发现子集标题误杀风险（0.75 直落强重复带），实施 _is_title_subset 降级规则——真子集且 sim∈[0.6,0.8) 降级到弱冲突带，≥0.8 近全同改写仍走快路径（全量测试抓到 0.857 同义改写反例后修正）；parse_error 写入 raw frontmatter 供下轮 worker 可见。73 passed 验证。教训：改判定带阈值后必须实测真实标题对分布。

### 2026-09-18 17:23 #fhi1

调研 atomicstrata/llm-wiki-compiler（llmwiki v1.3.0，TypeScript/Node≥24，MIT，作者 Ethan Joffe，活跃度高——最后提交 2026-09-17）。定位：Karpathy LLM Wiki 模式的通用知识编译器，原始素材（md/PDF/URL/YouTube）→ 带引用的可互链 Markdown wiki。核心机制已代码核对：①CLP 配置化生命周期 profile（.llmwiki/profile.json 声明实体/关系/生命周期FSM/工作流/信任门，写路径 fail-closed 强制，引擎无领域分支）；②意图日志+单一变更执行器 seam（src/trust/journal.ts、executor.ts，批次原子性契约，crash 恢复 replay）；③计算式 freshness 层（state.json 哈希对比，fresh/stale/orphaned/unverified 四态，refresh --stale 定向修复）；④eval 量化评估（health/citation coverage/depth/support/graph health + 阈值 + 历史delta，src/eval/index.ts）；⑤review policy 自动扣留（低置信/矛盾/违规schema/违规出处四类 hold 模式）；⑥MCP server 10+ 工具；⑦OKF 开放知识格式交换 + Ed25519 签名模板分发。对 CodeWiki-Plus 的可借鉴点：eval 量化门禁、freshness 四态分类、意图日志原子性、profile-as-data 原则；明确不借：TS 技术栈、CLP 全量 FSM 机制（对代码 wiki 场景过重）。

### 2026-09-18 17:28 #oc38

完成 cognee（topoteretes/cognee v1.5.4）调研，报告落盘 docs/cognee-调研与借鉴分析.md。核心发现：cognee 的 improve() 是会话→永久图谱桥接总入口（7 stage 全 fail-open），四个底座无关的可借鉴工程习惯——①水位线增量持久化（成功才推进、失败重试、陈旧检测，修 O(n²)）；②LIVE 确定性+ BATCH LLM 两级提取（错误轨迹零成本成 lesson，每 10 条才付一次 LLM）；③脱敏先行（错误文本入库前正则抹 secret/JWT/UUID）；④流式加权 w+=α(r−w) 替代裸计数（反馈与频率双通道）。明确不借：图库底座、无确认闸门的自动加权、truth subspace 质心、全局上下文索引分桶摘要。下一步候选：把①②③落成 CodeWiki 采集/蒸馏通道的具体设计方案。

### 2026-09-19 09:25 #llhc

cognee 调研 grill 复核定稿：8 个借鉴点全部证伪、0 采纳（6 条本仓已有等价实现：pending-status≈水位线、tool_digest 错误链≈LIVE 快路径、secret_redact≈脱敏、submit 单次多产出、usage_heat 三件套≈流式加权、file_lock+noop≈抢锁放弃；2 条语义不同不采纳：raw 优先级标记无排队前提、novelty 限定同类节点集违背 related≠same Doctrine）。报告 docs/cognee-调研与借鉴分析.md §三/§五已按证伪结论改写，cognee 价值定位为「独立收敛互证」。另：5 条蒸馏草稿笔记已全部 confirm 为 stable（llm-wiki-compiler 处置、noop 竞争处置、confirm_note 文件名坑、Experience 通道不立项、任务记忆状态滞后）。

### 2026-09-19 09:32 #zj2v

完成 memos（usememos/memos，HEAD 7e3d3c6，2026-09-19）调研，报告落盘 docs/memos-调研与借鉴分析.md。核心发现：其 MCP server（server/mcp/）协议合规工程是迄今调研项目最高水平——OpenAPI 驱动工具目录+白名单、进程内回环执行、annotations 方法推导+覆盖表修正、structuredContent 对象形规范化（修 #6022）、错误结果不带 schema（修 #6139）、任务级 eval（15 QA 钉种子数据）。处置：absorbed 1 条（registry 加 annotations 参数，写类工具标 destructiveHint，建议立项小改动）；deferred 3 条（structuredContent/outputSchema 与错误形状同根、任务级 eval 并入质量量化主线与 llm-wiki-compiler 调研合流）；excluded 6 条（无 OpenAPI 前提、无 SQL 存储、stdio 无 TTL 需求等）。

### 2026-09-19 19:06 #w7jl

Grill 轮裁决 memos 调研的 annotations 借鉴：absorbed 但挂起搭车（不单独立项），等下次 registry 契约变更时顺路落地。判定标准采用 memos「覆盖/删除既有状态 → destructive」：destructive 集合 = {edit_doc_file, reject_note, delete_task}，confirm_note/ingest_note/batch_set_status 不标。SDK 层已核实支持（mcp/types.py:1329 Tool.annotations）。MCP 协议术语不进 CONTEXT.md。草稿笔记已落盘：notes/2026-09-19-mcp-工具-annotations-挂起待搭车sdk-已支持判定标准采用-memos-覆盖既有状态说.md（待 confirm_note）。报告 docs/memos-调研与借鉴分析.md 处置表已同步更新。

### 2026-09-19 19:27 #9tx3

supermemory 调研完成，报告落盘 docs/supermemory-调研与借鉴分析.md。基线 HEAD 57b430b（2026-09-18），本地克隆 D:\repos\supermemory。核心结论：开源仓是客户端/集成层（MCP server、tools SDK、SMFS、MemoryBench），核心引擎闭源。12 项候选处置：6 项 excluded（确认闸门/双层记忆/成组蒸馏/检索缓存/采纳计数均已有等价，Claude memory 适配器方向相反）、3 项 deferred（derives+isLatest 挂知识飞轮主线；SMFS 文件系统哲学归 Cli能力任务；MemoryBench 归质量量化主线——同根信号第三次出现）、2 项归任务参考（annotations 四档为已裁决提供第二佐证；SKILL.md 范本归技能提取任务）。

### 2026-09-19 22:34 #6huc

supermemory「值得借鉴落地吗」grill 复核定案：无立即落地项。关键验证：supermemory「declined 即 forgotten」本仓已完全等价且是更精细三层设计（handler 层跳过 deprecated note_query.py:1030/465/672 + 索引层 -0.35 降权压出 top-N 槽位 retrieval.py:485 + 蒸馏去重豁免 apply_authority=False distill_conversation.py:678）。曾误判降权是死代码被代码核对证伪——降权作用于排序层在 handler 过滤之前。derives/isLatest 维持 deferred（知识形态不同）；SMFS 哲学归 Cli能力、MemoryBench 归质量量化、SKILL.md 范本归技能提取，均不推送等任务自然消费。报告 §3 处置表 #1 已改写为已验证等价。决策笔记已落草稿待确认。

### 2026-09-19 22:45 #yoy8

## hindsight 调研（2026-09-19）
- 克隆 D:\repos\hindsight（HEAD 0a58d69，2026-09-19 当日提交，vectorize-io 出品，约 4740 文件），报告落盘 `docs/hindsight-调研与借鉴分析.md`。
- 定位：生物拟态长期记忆系统（hindsight-api Python 引擎 + coding-agents TS 集成包接 18 个编码 Agent），重基建重 LLM（Postgres+embedding+cross-encoder，每次 retain 都跑 LLM 提取），与本仓架构前提相反。
- 核心收获在集成层认知：①索引抑制——注入块列知识页清单导致 40 轮实测 0 次搜索（全拿注入 id 直接 read），absorbed 为注入设计约束（本仓现状已部分符合，只列 3 条最新笔记）；②consolidation prompt 两条规则 absorbed 进 distill/聚合 prompt：每条 op 必带 reason、NO COMPUTATION（不推断未明说的数字）。
- deferred 2：knowledge page delta 刷新（等再生成成本成痛点）、4 臂检索+每臂截断+RRF 融合（等 query_wiki 多路召回需求）。
- 其余 excluded：工具指南反复注入、引用致谢、降级留痕、mission 外置等本仓已有等价；Memory Defense/云端 bank 前提不成立。

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
### 2026-09-04 12:12

完成 caveman（JuliusBrussee/caveman）仓库的技能生效机制研究：结论为多宿主分发提示词注入系统——SKILL.md 单事实源经三条链路注入（Claude Code Plugin hooks / CLI+Proxy 的 Native Pack / 通用 skills 目录）；核心机制是 SessionStart hook 的 stdout 作为隐藏系统上下文注入，compact/resume 触发重注入防压缩漂移。

### 2026-09-04 12:12

研究用的 clone 留在 d:/repos/CodeWiki-CN/.caveman-tmp/；对话收尾时向用户提出两个待办选项（整理成 repowiki comparison/query 笔记 or 清理临时目录），尚未收到决定——下一步需确认是否沉淀对比笔记及临时目录去留。

### 2026-09-04 12:23

caveman 研究收尾决定（2026-09-04）：1) 蒸馏草稿①「caveman 技能生效机制」用户拒绝，已 reject_note 标记 deprecated；2) 草稿②「Agent hook 注入的工程化防御与防漂移可复用模式」暂不处理，保留 draft 待定；3) .caveman-tmp/ clone 目录已按用户选择删除清理，无遗留待办。

### 2026-09-04 14:00

「他山之石」caveman 技能生效机制研究已完成（clone 临时目录 d:\repos\CodeWiki-CN\.caveman-tmp\），2 条 architecture 笔记已由用户确认落盘（stable）：2026-09-04-caveman-技能生效机制skillmd-单事实源经三条加载链路注入各-agent-上下文、2026-09-04-agent-hook-注入的工程化防御与防漂移可复用模式caveman-提炼。

### 2026-09-04 14:00

用户询问 CodeBuddy 使用方式后拍板：把 caveman 当普通 Skill「全量」安装到 ~/.codebuddy/skills/（复制 skills/ 下全部纯规则技能，含 caveman-commit/review/help）。安装动作在会话末尾仍在执行（PowerShell 查找 clone 目录），下一步：确认安装完成、新开会话验证 /caveman 触发与退出词，并清理 .caveman-tmp。

### 2026-09-04 14:00

主会话发现 raw/ 下另有 14 条「未关联任务」pending raw（各带 .lck 空锁，系某次未带 task_id 的 submit 误批处理所致，均未落盘副作用），建议由主 Agent 统一安排归属后再蒸馏；本 worker 未触碰。

### 2026-09-05 19:20

ponytail 技能生效机制研究完成：单份 SKILL.md 规则靠三层加载档位生效（T1 指令层=AGENTS.md 等常驻、T2 技能层=SKILL.md 渐进式披露、T3 hooks 层=仅 Claude Code/Codex 消费 claude-codex-hooks.json）；本机 CodeBuddy 为 T2，无自动激活/跨会话档位记忆，默认永远 full。已提炼 2 条 architecture 草稿（机制/工程手法）待确认。

### 2026-09-05 19:20

grill 拷问「ponytail/caveman 融合 CodeWiki MCP」第一轮 Q1–Q4 用户已答复并确认方向：Q1=b（产品能力：给 CodeWiki 增加代码精简+AI 回复精简）、Q2=按推荐三层分离（通用注入框架+规则包可换）、Q3=C（风格注入不落盘，自动注入可主张不违反 Doctrine 确认闸门）、Q4=C（先在 AGENTS.md/.codebuddy/skills 私有通道验证闭环再产品化）。

### 2026-09-05 19:20

下一步待办：hook-probe 探索代理核实 CodeWiki 现有 hook/注入设施事实（_ide_hook.py 采集方向 vs 注入方向需新增反向通道；CodeBuddy 是否支持 stdout 隐藏注入）返回后开第二轮拷问；融合方案尚未落地实现。

### 2026-09-05 23:20

2026-09-05：wikiskill（arXiv:2608.27454 开源实现）+ 论文解读调研完成，产出 comparison 页「自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用」（wiki/comparisons/）。定档结论：能实现，推荐方案 C 半闭环（MVP=单向编译器 B：confirmed notes/scenarios → SKILL.md draft → 确认闸门 → .codebuddy/skills/）；不建自动评分门控（CodeWiki 无 held-out 基准）；素材源=notes/scenarios；生成走 Mode C；先仓库内闭环再家族分发。grill Q1-Q4 用户均按推荐处理。下一步待用户拍板：是否进入 skill-creator 设计/实现。

### 2026-09-05 23:39

2026-09-05（续）：grill 第二轮 Q6-Q9 用户仍全按推荐，skill-creator 设计定档并落 wiki/queries/skill-creator设计方案.md。定档：①产物粒度=scenario 直译为主 + 未吸收的高价值 pitfall/lesson/decision 单条补充；②选材=prepare 列候选 + 显式 topic/sources 指定，禁止全自动触发（Doctrine 显式触发）；③落盘=两区制，草稿 repowiki/skills/ 不生效 → 确认后 install 到 .codebuddy/skills/ 生效（单区 draft 标记方案否决：草稿期技能已被 IDE 触发，闸门形同虚设）；④更新=整份重写 + metadata.revisions 变更记录段（不做 unified diff）；⑤工具形态 skill_creator 四 mode：prepare/submit/install/retire，容量硬顶 12，批次最多新建 1 份。分工：consolidate_notes 产知识层 scenario，skill_creator 产行为层 SKILL，单向下游。未决：Q10 回流验证判定、Q11 lint 规则与容量取值。

### 2026-09-07 09:42

humanizer v2.11.2（AI 文本去 AI 味技能，基于 Wikipedia Signs of AI writing，5 大类 35 种 AI 写作模式）已按既有模式安装到用户级 C:\Users\Administrator\.codebuddy\skills\humanizer\（纯 SKILL.md + README，无 hooks/symlink 依赖，与 caveman 安装决策一致）；.humanizer-tmp 临时 clone 已删除。

### 2026-09-07 09:42

用户裁决（2026-09-05）：ponytail 机制草稿已 reject_note（status=deprecated）；ponytail/caveman 融合 decision 草稿经 get_task_context 核实实际未落盘（蒸馏 subagent 自报不可信，related_notes 复核为凭）无需 reject；humanizer 安装过程明确不沉淀笔记。

### 2026-09-07 09:42

遗留待办：2026-09-04 旧 draft「在 CodeBuddy 使用跨 Agent 技能：纯 SKILL.md 直接装 ~/.codebuddy/skills/（hooks 需 CLI/插件市场）」一直保留待定未裁决，等待用户确认生效 / reject / 继续保留。

### 2026-09-07 10:53

修复 _ide_hook.py 两处问题：stdin BOM 容错（utf-8-sig + lstrip，对齐 wrapper capture_session_end.py）与诊断输出定向 stderr（无载荷/disabled/envelope 诊断/无 turns 四处 print，stdout 只留 hookSpecificOutput 与捕获结果），补 2 个回归测试，54 测试全绿，已提交推送。

### 2026-09-07 10:53

用户评审「他山之石」补蒸馏的 4 条草稿：②output_dir 纯函数 ③skill-creator 定档 ④disposition 三值机制 confirm 转 stable；①跨仓库 output_dir 劫持 pitfall 被用户拒绝（deprecated）。

### 2026-09-07 10:53

遗留：IDE hook 修复待用户验收；CodeBuddy 对 UserPromptSubmit 是否喂 stdin、是否消费 stdout hookSpecificOutput 未真机验证；settings.json 的 UserPromptSubmit 段在无 draft 技能期间空转，可考虑暂时删除。

### 2026-09-21 10:08 #y1a8

UserPromptSubmit active-settle 薄触发已实现（ADR-0015 后续，grill 2026-09-21 两轮）：①_ide_hook.py 加 ACTIVE_SETTLE_REMINDER 常量（混合措辞：回看补写+前瞻自查）与 _repo_has_active_tasks()（读 tasks/.index.json，fail-open）；②_handle_user_prompt 输出改为技能提示与提醒拼接（技能在前）；③test_skill_match.py 补 5 条断言（注入/无任务静默/非 active 静默/拼接顺序/索引损坏 fail-open）。全量 1131 passed。决策记录：PreCompact 不做（Q1 超集）、Stop+block 不做（无 transcript 无法验证+循环风险）、触发条件用「仓库有 active 任务」代理信号（绑定落盘方案 deferred）。待办：commit 未做。

### 2026-09-21 11:12 #iyy2

SubagentStart hook 评估定案（他山之石后续）：不做。理由：①CodeBuddy 是否支持该事件未验证；②沉淀责任应留在主 Agent——subagent 上下文窄、无任务级视野做四问过滤、跑完即销毁，直接落盘会绕过确认闸门（笔记）或灌爆任务记忆（直写）；③主 Agent 收到 subagent 返回值的那一刻就是天然停顿点，已被 active-settle 通道覆盖。正确增强点是「发起 subagent 的返回值约定」：已增补进 get_prompt(task-workflow) 的「会话进行中」节——主 Agent 派发子任务时 prompt 末尾加「返回结果时报告三件事：做了什么、关键发现、值得沉淀的经验（若有）」，过滤/查重/落盘全在主 Agent。distill-worker 是特例不冲突。全量测试 1130 passed（1 个并发测试 flaky 单独跑通过）。待办：commit 未做。

### 2026-09-21 15:18 #6txu

Workspace Conventions 模板瘦身完成（ADR-0015 同款收敛）：①两个模板（agents-md-workspace-centralized.md.tpl / agents-md-workspace.md.tpl）的「新业务仓接入清单」8→2 行——手工三步与 add_workspace_repo 工具事务式同步四处重复，收敛为工具名+get_prompt(add-workspace-repo) 指针，手工兜底三步移入该 prompt 注意事项；②分支策略 3→1 行（删解释留规则）。48→40 行。全量 1136 passed。待办：commit 未做。
