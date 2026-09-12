## 早期记忆（摘要）

2026-09-04 ~ 09-11 早期他山之石调研结论摘要：

【已完成研究】①caveman：SKILL.md 单事实源经三条链路注入（hooks/Native Pack/skills 目录），SessionStart stdout 隐藏注入 + compact 重注入防漂移；2 条 architecture 笔记已 stable；技能已装 ~/.codebuddy/skills。②ponytail：三层加载档位 T1 指令/T2 技能/T3 hooks，CodeBuddy 属 T2；机制草稿已 reject。③wikiskill：SKILL 自动生成定档方案 C 半闭环（单向编译器 B：confirmed notes/scenarios → SKILL.md draft → 确认闸门 → .codebuddy/skills/），不建自动评分门控。④skill-creator 设计定稿：四 mode prepare/submit/install/retire、两区制（草稿 repowiki/skills/ 不生效 → install 到 .codebuddy/skills/）、容量硬顶 12、批次最多新建 1；consolidate_notes 产知识层 scenario，skill_creator 产行为层，单向下游。未决：Q10 回流验证判定、Q11 lint 规则与容量取值。⑤humanizer v2.11.2 已装用户级，临时 clone 已清。⑥ponytail/caveman 融合方向定档（产品能力=代码+回复精简，三层分离，风格注入不落盘，先私有通道验证）但未落地。

【teamai-cli 增量调研（09-10）】v0.20.0→v0.23.1（250 commit），8 候选 0 采纳，产出证伪清单。两个 excluded 带前置条件：#336 漏检率 0% 是 n=1 样本不能当证否（需 keep_raw 或 repowiki/tasks/ 更大样本；且后续口径修正：tool_digest 仅两个调用点，先定通道覆盖面再谈样本量）；#374 依赖「团队无 git worktree 并行习惯」假设，若不成立退回探测。

【流程与坑】借鉴项目统一克隆到 D:\repos（teamai-cli 已到位，余约 20 个待补）；蒸馏 subagent 自报的笔记状态不可信，须 get_task_context related_notes 复核；CodeBuddy UserPromptSubmit 是否喂 stdin/消费 stdout 未真机验证；settings.json UserPromptSubmit 段无 draft 技能期间空转可删。

【遗留待办】2026-09-04 旧 draft「在 CodeBuddy 使用跨 Agent 技能」保留待定未裁决；IDE hook 修复（BOM 容错+stderr 诊断）已提交推送待验收。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-09-12，共 26 条。

### 2026-09-11 07:23

### 2026-09-11 08:52

整体增量调研报告已落盘 docs/借鉴项目整体增量调研报告-2026-09.md：11 个项目全覆盖（codebase-memory-mcp 1182 / semantica 682 / WeKnora 588 / OpenViking 268 / llm_wiki 183 / claude-mem 36 / openwiki 34 / RepoWiki 23 / MindForge·wikiskill·AIO 无新增），44 候选 → 0 采纳 / 15 deferred / 29 excluded。

### 2026-09-11 08:52

分项目细节：docs/claude-mem-增量调研与借鉴分析-2026-09.md（f92996e/v13.23.1 → d095021d/v13.24.1，36 commit，7 候选 → 0 采纳 / 2 deferred / 5 excluded；核心是对方能力依托 OpenRouter 计费归因 + 插件市场分发，本仓无此前提）。

### 2026-09-11 08:52

三条方法论结论：① 一半候选本仓早有（最典型是 injection_budget.py:1 的 docstring 就写着借鉴自 OpenViking auto-recall）；② 他仓往服务端/队列/多租户走，本仓是本地 markdown + git + 同步 MCP 的主动不同取向，此类不是缺口；③ 主线是「成本/预算从软约束变硬约束」，本仓空档在扫描侧预算与 deprecated 笔记是否被新 ingest 复活。

### 2026-09-11 08:52

15 项 deferred 分三类：留档照抄 9（输入过滤无配置即恒等+编译失败不抛、增量基线失效兜底+单源失败仍写 state、去重 Jaccard 预筛、无损分页只在 end<allowed_count 才发 cursor 等）、转多仓工作区 1（workspace manifest 审批键）、自查项 3（wikilink 代码围栏切分 / ADR 是否整文件重写 / deprecated 是否被复活）——3 个自查项等用户裁决是否现在跑。

### 2026-09-11 08:52

口径修正（重要）：[tool-error] 只由 tool_digest 产生，仅 _ide_hook.py:273 与 capture_conversation.py:222 两个调用点，session-end 补采集不经过它 → 之前「8 条 raw 仅 1 条含 tool-error、漏检率 0%」测的是通道覆盖面而非漏检率，先定覆盖面再谈样本量。

### 2026-09-11 08:52

待办：3 条蒸馏草稿待用户 confirm（repowiki 版本化资产架构事实 / 小样本不能当证否 / 增量调研 SOP），第 2 条建议补入「通道覆盖面」这一层；本地 develop 领先 origin 7 个提交未推送。

### 2026-09-11 08:52

整体增量调研报告已落盘 docs/借鉴项目整体增量调研报告-2026-09.md：11 个项目全覆盖（codebase-memory-mcp 1182 / semantica 682 / WeKnora 588 / OpenViking 268 / llm_wiki 183 / claude-mem 36 / openwiki 34 / RepoWiki 23 / MindForge·wikiskill·AIO 无新增），44 候选 → 0 采纳 / 15 deferred / 29 excluded。

### 2026-09-11 08:52

分项目细节：docs/claude-mem-增量调研与借鉴分析-2026-09.md（f92996e/v13.23.1 → d095021d/v13.24.1，36 commit，7 候选 → 0 采纳 / 2 deferred / 5 excluded；核心是对方能力依托 OpenRouter 计费归因 + 插件市场分发，本仓无此前提）。

### 2026-09-11 08:52

三条方法论结论：① 一半候选本仓早有（最典型是 injection_budget.py:1 的 docstring 就写着借鉴自 OpenViking auto-recall）；② 他仓往服务端/队列/多租户走，本仓是本地 markdown + git + 同步 MCP 的主动不同取向，此类不是缺口；③ 主线是「成本/预算从软约束变硬约束」，本仓空档在扫描侧预算与 deprecated 笔记是否被新 ingest 复活。

### 2026-09-11 08:52

15 项 deferred 分三类：留档照抄 9（输入过滤无配置即恒等+编译失败不抛、增量基线失效兜底+单源失败仍写 state、去重 Jaccard 预筛、无损分页只在 end<allowed_count 才发 cursor 等）、转多仓工作区 1（workspace manifest 审批键）、自查项 3（wikilink 代码围栏切分 / ADR 是否整文件重写 / deprecated 是否被复活）——3 个自查项等用户裁决是否现在跑。

### 2026-09-11 08:52

口径修正（重要）：[tool-error] 只由 tool_digest 产生，仅 _ide_hook.py:273 与 capture_conversation.py:222 两个调用点，session-end 补采集不经过它 → 之前「8 条 raw 仅 1 条含 tool-error、漏检率 0%」测的是通道覆盖面而非漏检率，先定覆盖面再谈样本量。

### 2026-09-11 08:52

待办：3 条蒸馏草稿待用户 confirm（repowiki 版本化资产架构事实 / 小样本不能当证否 / 增量调研 SOP），第 2 条建议补入「通道覆盖面」这一层；本地 develop 领先 origin 7 个提交未推送。

### 2026-09-12 08:28

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
