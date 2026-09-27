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

### 2026-09-10 20:32

### 2026-09-10 21:41

### 2026-09-10 21:42

2026-09-10 完成 teamai-cli 增量调研（基线 v0.20.0 → HEAD v0.23.1，新增 250 commit、3 篇设计文档），成果存档 `docs/teamai-cli-增量调研与借鉴分析-2026-09.md`（§6 为处置表）。

### 2026-09-10 21:42

8 个借鉴候选最终 0 采纳：#374/#375/#304/#368/#458/#380 直接 excluded，#378 降级为「frontmatter 自查 checklist」不立项，#336 经探测脚本实测（raw 8 条、含 tool-error 1 条、漏检率 0% < 20% 阈值）后也 excluded——本轮产出是证伪清单而非功能清单。

### 2026-09-10 21:42

#336 的 excluded 带前置条件：现有 raw 样本仅 8 条（蒸馏后删除导致），0% 是 n=1 的结果，不能当已证否；若要真判定需先开启 `keep_raw` 积累 raw 或改用 `repowiki/tasks/` 更大样本。

### 2026-09-10 21:42

#374 excluded 依赖一个用户假设：团队没有 `git worktree` 并行开发习惯。若该假设不成立（存在同仓多检出、知识需跨检出共享），#374 要从 excluded 退回探测。

### 2026-09-10 21:42

下一个待调研项目定为 claude-mem（「使用信号闭环」的另一条实现路线，可与已 excluded 的 #336 直接对照）；借鉴项目统一克隆到 `D:\repos`，目前仅 teamai-cli 到位，剩余约 20 个待补（上次批量克隆命令被取消）。

### 2026-09-11 07:04

### 2026-09-11 07:07

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
