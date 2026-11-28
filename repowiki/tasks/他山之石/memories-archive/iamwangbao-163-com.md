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

### 2026-11-27 00:23 #hwb1

> [superseded 2026-11-27 by #t2wh]

B4 计划写入门禁与 B5 聚类质量 validator 已实施，均作为内部模块接入既有 MCP handler、不新增工具。B4 默认 observe，enforce 仅放行 pending 页面或精确 target；按实际 routed 路径、计划 schema/hash 身份与当前 centralized 仓分区判定，delete-only 不授权重建；计划外写入落审计且不污染 plan_hash。B5 按完整 scope 文件分块估算 token，父模块聚合后代并集；缺测/逃逸/不可读显式进入 unmeasured，部分缺测不判微页；使用轻量组件元数据与会话签名缓存，异常降级 unavailable，不自动改树。两轮独立审查的安全边界与性能问题均已修复，schema 中英模板同步。验证：B4 专项 39、B5 专项 20、联合 189、相邻 B1-B5 63、B4 周边 107；全量 1537 passed/2 skipped；MCP 契约 121 passed/5 failed（既有 OKF/frontmatter/confirm gate 基线，无新增）；ruff、相关 mypy、stdio 53 工具/schema/prompt、diff check 通过；未运行 smoke。已更新后续借鉴清单并生成 B4/B5 两篇 decision draft（待用户 confirm，未自动确认）。本轮未提交、未推送。下一步仅在明确需求下启动 C1/C2/C3，不自动展开。

### 2026-09-20 12:03 #l5dy

ADR-0013 E 项实施完成（2026-09-20）：① 新建 codewiki/mcp/tools/limits.py（压缩阈值组 40/24KB/keep20/4096 + 写入窗口软限 5 + 压缩级别 0.75/0.875）；② task_manager.py 改为 import + 历史私有名 re-export，行为等价；③ wiki_lint.py 新增 threshold_drift 检查（扫 registry.py/prompts.py 文案 vs limits.py 常量，锚定正则避免 50KB 误报）+ registry schema enum 同步；④ 首日即抓到真实漂移：registry.py:2953 compact 描述写 2048 实际常量 4096，已修文案；⑤ 新增 tests/test_threshold_drift.py 6 用例全过，全量 1168+6 passed。B 项（ingest_note reason 必填 + evidence 可选）待实施。

### 2026-11-27 00:25 #t2wh

> [superseded 2026-11-27 by #4xve]

B4 计划写入门禁与 B5 聚类质量 validator 已实施，均作为内部模块接入既有 MCP handler、不新增工具。B4 默认 observe，enforce 仅放行 pending 页面或精确 target；按实际 routed 路径、计划 schema/hash 身份与当前 centralized 仓分区判定，delete-only 不授权重建；计划外写入落审计且不污染 plan_hash。B5 按完整 scope 文件分块估算 token，父模块聚合后代并集；缺测/逃逸/不可读显式进入 unmeasured，部分缺测不判微页；使用轻量组件元数据与会话签名缓存，异常降级 unavailable，不自动改树。两轮独立审查的安全边界与性能问题均已修复，schema 中英模板同步。验证：B4 专项 39、B5 专项 20、联合 189、相邻 B1-B5 63、B4 周边 107；全量 1524 passed/2 skipped/1 warning；MCP 契约 121 passed/5 failed（既有 OKF/frontmatter/confirm gate 基线，无新增）；ruff、相关 mypy、stdio 53 工具/schema/prompt、diff check 通过；未运行 smoke。已更新后续借鉴清单并生成 B4/B5 两篇 decision draft（待用户 confirm，未自动确认）。本轮未提交、未推送。下一步仅在明确需求下启动 C1/C2/C3，不自动展开。

### 2026-11-27 00:50 #4xve

> [superseded 2026-11-27 by #7hpa]

B4 计划写入门禁与 B5 聚类质量 validator 已实施并完成最终验证，均作为内部模块接入既有 MCP handler、不新增工具。B4 默认 observe，enforce 仅放行 pending 页面或精确 target；按实际 routed page key、计划 schema/hash 身份与当前 centralized 仓分区判定，delete-only 不授权重建；计划外写入落审计且不污染 plan_hash。最终审查修复了同 stem 跨仓归因：plan 构建/delete/replan/manifest 查询、删除执行、mark_op_done 与 job ledger 均按当前分区及实际 page key 结算；query/entity/他仓模块页只计 other_written，不误关缺页 job，overview 保留明确例外。B5 按完整 scope 文件分块估算 token，父模块聚合后代并集；缺测/逃逸/不可读显式进入 unmeasured，部分缺测不判微页；使用轻量组件元数据与会话签名缓存，异常降级 unavailable，不自动改树。验证：B4 专项 39、B5 专项 20、B1-B5 联合 63、跨仓修复后 B4 周边 114、文档写入/路由周边 51；最终全量 1531 passed/2 skipped/1 warning；MCP 契约 121 passed/5 failed（既有 OKF/frontmatter/confirm gate 基线，无新增）；核心 5 文件与新增专项测试 mypy、ruff、diff check 通过；未运行 smoke。已更新后续借鉴清单并保留 B4/B5 两篇 decision draft（待用户 confirm，未自动确认）。本轮未提交、未推送。下一步仅在明确需求下启动 C1/C2/C3，不自动展开。

### 2026-09-20 12:25 #5c41

ADR-0013 B 项实施完成（2026-09-20）：① note_ingest.py 加 reason 校验（status=stable 必填，缺失拒绝并提示改走 draft→confirm；draft 可选）+ evidence 处理（复用 confirm_note 语义：test_ref/commit_ref/reviewed_by，提供时升 confidence_level=strong 并记 metadata.verification，未知 key 拒绝）；② reason/verification 写进 frontmatter metadata；③ registry.py ingest_note schema 加 reason/evidence 参数描述，status 描述同步更新；④ 新增 tests/test_ingest_reason_evidence.py 7 用例，修 4 处既有裸 stable 调用补 reason；⑤ 全量 1182 passed。ADR-0013 全部落地（E+B）。

### 2026-09-20 19:39 #ki12

完成 hook/AGENTS.md 竞品调研（claude-mem、hindsight、teamai-cli、letta-code、openwiki、better-harness、caveman、project-cairn）。核心结论：①AGENTS.md 应瘦身成路由层（cairn ≤60 行预算 + 文档职责表），细节外置 wiki 按需检索；②task-memory 协议存在 AGENTS.md 块与 SessionStart hook 双通道重复注入，应单点收敛（建议保留 hook 硬通道，AGENTS.md 留一行指针）；③hook 可借鉴 teamai-cli golden fixture 钉渲染输出、claude-mem 原生 async:true（需真机验证 CodeBuddy 支持）；④明确不借 claude-mem 六事件全采集（噪音）、inline bash 路径解析、letta commit-on-write（模型相反）。下一步：向用户确认优化方案后落地。

### 2026-09-20 20:43 #f5gt

ADR-0015 落地完成：AGENTS.md 托管块瘦身与注入通道收敛。改动：①zh.yaml/en.yaml CodeWiki 块 89→45 行（保留采纳声明/标注依据/语言闸门，纠正识别三步流程并入使用建议第 3 条，归档示例 JSON 删除指向 get_prompt(ingest-note)，路由表压成单行）；②prompts.py _TASK_MEMORY_AGENTS_SECTION 40→8 行指针式（hook 注入优先，未注入时按 task-workflow prompt 执行，全文收敛到 hook 硬通道+prompt）；③本仓 AGENTS.md 163→97 行，Team memory fusion 节外移到 repowiki/wiki/team-memory-fusion.md；④本仓两块用产品渲染器刷新（_build_section + upsert_agents_section）。全量测试 1109 passed。golden fixture（D5）deferred 到下次动 ide_config.py 前补。待办：commit 未做（等用户确认）。

### 2026-11-27 06:58 #r0xt

> [superseded 2026-11-27 by #sdc2]

C2 第二语言 Ruby 薄适配已实施：独立 tree-sitter-ruby 0.23.1 + grammar preflight，保留完整 namespace、#/. 方法身份、词法常量/继承作用域与保守接收者推断；跨文件裸调用延迟解析且不做尾名猜测。两轮审查反例已修复。验证：Ruby 专项 43 passed、Ruby/Rust 68 passed、加入 correctness/latest compat 联合 81 passed；真实 Ruby 标准库 19 样本得到 956 组件/2823 关系；正式 stdio MCP 首次 16 组件。增量复测发现并修复 AnalysisCache._SRC_EXTS 缺 .rb/.rs，导致无改动全量误报；修复后 no_changes=true，单文件新增只报 support.rb 与 #report。OKF 契约 121/5 与基线一致。backlog 已更新，Ruby 决策草稿保持 draft。最终全量测试正在复跑；未提交、未推送、未确认草稿。

### 2026-09-20 21:26 #os6r

ADR-0015 已提交推送：cb305c7 feat: ADR-0015 AGENTS.md 托管块瘦身与注入通道收敛（5 文件，+102/-196），已推送 origin/develop。排除项：repowiki/schema.yaml（auto-sync 副作用重写，非本次改动）、.codebuddy/memory（工作记忆）。后续 deferred 项：①UserPromptSubmit 薄触发提升主动沉淀命中率（方案已给出，用户暂不做）；②golden fixture 测试（下次动 ide_config.py 前补）。

### 2026-11-27 13:45 #9a8p

> [superseded 2026-11-27 by #4yy7]

C2 Scala package-aware 薄适配已完成代码与专项验收：独立 tree-sitter-scala wheel、grammar preflight、声明 package/import 精确解析、companion `$` 身份、Scala 2/3 类型/方法、wildcard 唯一命中、重载弃权、词法 receiver 作用域、缓存嵌套身份与旧边重裁决、继承基类优先及顶层后备、构造参数字段链 package 固化；`.scala/.sc` 与 SBT manifest/service/artifact 接入已同步。三轮审查反例均有回归，Scala 专项 42 passed、语言联合 173 passed，ruff/mypy/diff check 通过；OKF 为既有 121/5。正式 stdio MCP 首次 5 组件、无变更及单文件 5→6 增量通过。决策草稿 notes/2026-11-27-scala-analyzer-应保留组件-id-并按声明-package-精确解析.md 已可检索且保持 draft。最终全量仍在运行；未提交、未推送、未确认草稿。

### 2026-11-27 16:51 #allr

> [superseded 2026-11-27 by #l5so]

C2 Zig 薄适配已实现并通过专项/联合/正式 MCP 验证，最终全量回归正在运行。使用独立 tree-sitter-zig==1.1.2 wheel，保留 path::logical_name 组件 ID；覆盖容器、泛型、@import/re-export、build.zig addModule、调用/实例化/类型边。未知 receiver 不猜尾名；任一 Zig 变化全量重解析 Zig，非 Zig 增量合并存活缓存。alias-only 文件纳入指纹，build.zig 同时是 build artifact 并提取源码引用。独立审查发现并修复显式类型初始化漏调用边、block 局部类型污染、删除文件指纹永久误报三个问题。Zig 专项 21 passed，语言/artifact/tree/change 联合 273 passed，ruff/mypy/diff check/lock check 通过；OKF 121/5 为既有基线。正式 stdio 首次 4 组件，无变更、单文件增量、build.zig 映射、alias 删除后下一轮收敛均通过。backlog/调研已回填，Zig 决策笔记保持 draft 未确认。本轮未提交、未推送；下一语言候选 Lean 4 不自动展开。

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
