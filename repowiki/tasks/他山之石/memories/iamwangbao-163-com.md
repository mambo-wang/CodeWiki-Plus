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

### 2026-09-10

teamai-cli 增量调研完成并存档：基线 docs/teamai-cli-调研与借鉴分析.md（2026-08-21 v0.20.0）→ 现 HEAD 9e7adc7（2026-09-10，v0.23.1/v0.24.0-beta.5），250 个新提交。存档为 docs/teamai-cli-增量调研与借鉴分析-2026-09.md。

两个最值得借鉴的合入：①#374 数据分区——~/.teamai/projects/<slug(anchor)>/，slug=basename+sha256 前 16 hex（8hex 不安全有论证），projectAnchor（worktree list 首项，共享身份）与 workspaceRoot（当前检出，资源落点）分离，明确否决 git-common-dir 方案，锁改 O_EXCL+owner token+回收哨兵；②#336 摩擦信号从 CodeBuddy transcript 确定性提取（interrupt/toolReject/toolError 三类，CodeBuddy 需读 messages/*.json blob，'User rejected this command' 只计人拒，isError 只计真失败），可直接移植补 CodeWiki friction_score 恒为 0 的缺口。次要：#375 role×project 正交+learnings 根层共享子目录私有、#304 WASM tree-sitter 可选降级+PARSE_SKIP gap、#368 KB Health 报告。

下一步待用户拍板：①摩擦信号移植 ②分区+锁 ③先立 ADR；以及是否把可复用机制沉淀为 repowiki note。借用项目统一克隆到 D:\repos 的动作只完成 teamai-cli（其余 20 个未克隆，上次批量克隆命令被取消）。

### 2026-09-10 21:41

### 2026-09-10

grill 拷问后拍板 teamai-cli 借鉴处置（判据=只有实测缺口才做，Doctrine 归因调优 SOP）：8 个候选 0 个直接做、7 个 excluded、1 个待实测。

初稿两个判断被证伪：①「friction_score 恒为 0 是缺口」——实际 friction.py 已有打分（correction×20+interrupt×20+repeat×15+规模档，min_user_turns=4），且 [tool-error:] 行已由 tool_digest.py:213-237 写进 raw，只是没计数；②「锁缺 owner token」——store.py:166-189 用 OS flock，比 teamai 的 O_EXCL+owner token+陈旧回收更强（后者是无 flock 的替代品）。

#336 探测结果：repowiki/raw 仅剩 8 条、含 tool-error 的仅 1 条，漏检率 0%（阈值 20%），但该会话 score=5 已被覆盖 → excluded，原因「实测无缺口」；附样本量警告：n=1 不足以证否，复测需 keep_raw 积累或改用 repowiki/tasks 更大样本。

其余 excluded 原因：#374 模型相反（我们知识随仓库版本化 vs 他们机器数据搬出业务仓）+ 身份解析我们用宿主 *_PROJECT_DIR 更靠前；#375 分发维度 vs 归属维度（related≠same）；#304 tree-sitter 我们是主线；#368 无趋势数据；#458/#465 无删除用例；#380 无分发形态。frontmatter 三条转自查 checklist 不立项。

处置表已写入 docs/teamai-cli-增量调研与借鉴分析-2026-09.md §6，§1/§2/§3 的初稿判断已就地加修正。待用户确认是否沉淀 lesson 笔记：借鉴调研前先查本仓是否已有该能力，别把「没宣传」当「没做」。

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
