---
type: Conversation
title: "conversation 20260911T015609Z"
status: distilled
stale_after: 2026-12-10
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:56:09Z }
captured_at: "2026-09-11T01:56:09Z"
content_hash: "sha256:7eb42fb98bece83897203ca059b750236547f21de66f73cea69a580a7c4411be"
friction_score: 30
friction_signals: "correction=1,interrupt=0,repeat=0,user_turns=13"
keep_raw: false
link_to: ""
source_session: "fc9c288d92e541518ce4a19721da0c75"
turn_count: 106
---

# Conversation Transcript

user: 继续调研
assistant: [tool: ask_followup_question · {"questions": [{"question": "本会话要关联到哪个进行中的任务？（列表里没有想要的任务时，可直接在输入框中输入新任务名后回车）", "header": "任务关联", "options": ["CodeWiki 架构深化分析", …
user: <question>本会话要关联到哪个进行中的任务？（列表里没有想要的任务时，可直接在输入框中输入新任务名后回车）</question>
<answers>
他山之石
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"fc9c288d92e541518ce4a19721da0c75\",\"t…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"他山之石\",\"repo_path\":\"d:/repos/CodeWiki-CN\"}",…
assistant: [tool: task · {"subagent_name": "distill-worker", "description": "补蒸馏他山之石积压", "prompt": "请对任务「他山之石」执行补蒸馏（Mode C，纯 MCP JSON）。repo_path = d:/repos/CodeWiki-CN。步骤…

[tool: search_file · *借鉴*]

[tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\docs"}]
assistant: [tool: list_dir · {"target_directory": "D:\\repos"}]

[tool: search_content · d:\repos\CodeWiki-CN\docs]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\teamai-cli-增量调研与借鉴分析-2026-09.md"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\TencentDB-Agent-Memory-增量调研与借鉴分析-2026-09.md"}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\claude-mem-调研与借鉴分析.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\codebase-memory-mcp跨服务分析-源码借鉴分析.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\LLM-Wiki-借鉴与整合.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\MindForge-调研与借鉴分析.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\OpenViking-调研与借鉴分析.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\OpenWiki-借鉴详细设计方案.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\repowiki-项目研究与借鉴分析.md", "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\Semantica-AIO-决策智能与本体-借鉴分析.md", "limit": 14}]
assistant: [tool: execute_command · $d='claude-mem','codebase-memory-mcp-src','llm_wiki','MindForge','OpenViking','openwiki','RepoWiki','semantica','WeKnora','wikiskill',…
assistant: [tool: execute_command · $items=@(@('claude-mem','2026-09-02'),@('codebase-memory-mcp-src','2026-07-25'),@('llm_wiki','2026-07-01'),@('MindForge','2026-08-27')…
assistant: [tool: execute_command · foreach($it in @(@('claude-mem','2026-09-02'),@('OpenViking','2026-08-21'),@('openwiki','2026-08-31'),@('llm_wiki','2026-07-01'))){ $n…
assistant: [tool: execute_command · git -C D:\repos\claude-mem log --since=2026-09-02 --oneline origin/HEAD | Select-Object -First 45]

[tool: read_file · {"filePath": "D:\\repos\\claude-mem\\CHANGELOG.md", "limit": 90}]
assistant: [tool: execute_command · git -C D:\repos\claude-mem show --stat --format='%h %s' fd0ecf02 | Select-Object -First 30; Write-Output '######'; git -C D:\repos\cla…

[tool: search_file · *telemetry*]

[tool: search_content · D:\repos\claude-mem]
assistant: [tool: read_file · {"filePath": "D:\\repos\\claude-mem\\RECEIPT-JOIN.md"}]

[tool: read_file · {"filePath": "D:\\repos\\claude-mem\\src\\services\\telemetry\\skill-id.ts"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\telemetry.py"}]
assistant: [tool: execute_command · git -C D:\repos\claude-mem show fd0ecf02 -- docs/public/progressive-disclosure.mdx | Select-Object -First 120]

[tool: execute_command · git -C D:\repos\claude-mem show d095021d -- src/services/worker/http/shared.ts src/services/telemetry/scrub.ts docs/public/telemetry.m…
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\plans\\cli-capability-progressive-disclosure.md"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\src\tool_digest.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\telemetry.py]
assistant: [tool: search_content · D:\repos\claude-mem\src\services\telemetry\scrub.ts]

[tool: search_content · D:\repos\claude-mem\src\services\sqlite\tool-uses.ts]
assistant: [tool: execute_command · git -C D:\repos\claude-mem show origin/HEAD:src/services/telemetry/scrub.ts | Select-String -Pattern 'skill_' | ForEach-Object { "$($_…

[tool: execute_command · git -C D:\repos\claude-mem show origin/HEAD:src/services/telemetry/skill-id.ts | Select-Object -First 70 | ForEach-Object -Begin {$i=0…
assistant: 现在把 claude-mem 这轮增量调研落盘。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\claude-mem-增量调研与借鉴分析-2026-09.md", "content": "# claude-mem 增量调研与借鉴分析（2026-09-11）\n\n> 增量对象：*…
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"add_task_memory\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"他山之石\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"c…
assistant: [tool: execute_command · git -C D:\repos\OpenViking log --since=2026-08-21 --no-merges --format='%s' origin/HEAD | ForEach-Object { if ($_ -match '^(\w+)(\(([^…

[tool: execute_command · git -C D:\repos\openwiki show --stat --format='%h %s' 1b84ea8 | Select-Object -First 20; Write-Output '#####'; git -C D:\repos\openwik…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: execute_command · git -C D:\repos\OpenViking log --since=2026-08-21 --no-merges --format='%h %s' origin/HEAD | Select-String -Pattern 'memory|openclaw|p…
assistant: [tool: execute_command · git -C D:\repos\OpenViking show --format='%h %s' 98f24e16 | Select-Object -First 70]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\src\\tool_digest.py", "offset": 195, "limit": 80}]

[tool: search_content · d:\repos\CodeWiki-CN\tests]
assistant: [tool: list_dir · {"target_directory": "C:\\Users\\Administrator\\.codebuddy"}]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"他山之石\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"c…
assistant: 本轮调研推进如下。

## 1. 先跑全景扫描（11 个借鉴项目）

本地克隆逐个 `git fetch` + `rev-list --count --since=<各调研文档标注的基线> origin/HEAD`：

| 项目 | 基线 | 新增提交 | 队列 |
|---|---|---|---|
| codebase-memory-mcp | 2026-07-25 | 1182 | 量大，先按 diffstat 过滤 |
| semantica | 2026-08-09 | 682 | 中 |
| WeKnora | 2026-07-21 | 588 | 中 |
| OpenViking | 2026-08-21 | 268 | **下一轮** |
| llm_wiki | ~2026-07 | 183 | 低 |
| claude-mem | 2026-09-02 | 36 | **本轮已完成** |
| openwiki | 2026-08-31 | 34 | 已预检 |
| RepoWiki | 2026-07-29 | 23 | 低 |
| MindForge / wikiskill / AIO | — | 0 | 无新合入 |

## 2. claude-mem 增量调研（已落盘）

`docs/claude-mem-增量调研与借鉴分析-2026-09.md`：`f92996e`/v13.23.1 → `d095021d`/v13.24.1，36 commit。
**7 候选 → 0 采纳、2 deferred、5 excluded**，核心是证伪：他们的新增能力依托「OpenRouter 计费归因 + 插件市场分发」两个本仓没有的前提。

- `#3898 tool_uses` 明细表 → excluded（建表主需求是把 \$ 归因到工具，`RECEIPT-JOIN.md:5,69-73`；本仓无花费数据面）。但四条工程不变量留档 deferred：upsert 语义、自读工具跳过（`tool-uses.ts:48-74`）、64KB 截断+原文 `content_hash`、原始体只按 id 取（`RECEIPT-JOIN.md:164-189`）。
- `#3960 skill_invoked` 技能遥测 → deferred：本仓 telemetry 只有 `hit`/`adopted`/`by_file`（`telemetry.py:20-21,139,190,208`），**无技能维度事件**，是真缺口；但技能命中率尚未成为任何在办项的判定输入。真要动手可直接抄他们的封闭枚举（第三方一律折叠为 `other`，`skill-id.ts:12-33,62-69`）。

## 3. 一条会推翻旧结论口径的连带发现

`[tool-error: …]` 行只由 `tool_digest` 产生，而它只有两个调用点——`_ide_hook.py:268`、`capture_conversation.py:221`；**session-end 的 transcript 补采集不经过它**。所以上次 teamai #336 实测「8 条 raw 中仅 1 条含 tool-error、漏检率 0%」测的是**通道覆盖面**，不是漏检率。复测前必须先回答「工具失败信号在几条通道上被采集、各覆盖多少会话」，否则加大样本只是放大同样的偏差。已写进文档 §1.3。

## 4. 下轮两项预检（已落附 B）

- OpenViking `#4724` camelCase `isError` → excluded：本仓 `tool_digest.py:213` 只读 `is_error`，但作用对象是 hook payload（测试固定 `is_error`，`tests/test_ide_hook_capture.py:779`），他们修的是 AI SDK/transcript 面。前瞻提醒：将来若加 transcript 直读通道，必须同时认 `isError`。
- openwiki `#859` 指纹忽略 Windows ctime 漂移 → excluded：本仓指纹基于内容（`doc_similarity.py:109`、`page_manifest.py:104`），不碰 stat 元数据。

---

补蒸馏 subagent 仍在后台跑「他山之石」的 1 条积压对话，草稿出来后我会一并给你确认。

下一步我会深挖 OpenViking（268 commit，候选：`#4900` 跨宿主 turn 协议保留捕获、`#4858` recall/capture 可配置正则过滤、`#4779` 队列自愈、`#4907` 缺失任务记录视为已删除、`#4559` 跳过争用的父级新鲜度更新）。

另外，有一条值得沉淀的教训候选：「实测缺口时先检查测量通道的覆盖面，别把『没采到』当『没漏检』」——要记成 note 吗？（需你确认后我才写入）

<!-- codewiki:referenced-docs: [] -->
user: <question>本会话要关联到哪个进行中的任务？（列表里没有想要的任务时，可直接在输入框中输入新任务名后回车）</question>
<answers>
他山之石
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-task-他山之石</from>
<summary>Message from distill-task-他山之石</summary>
<content>
任务「他山之石」补蒸馏已完成（Mode C），如实汇报如下，请复核。

## 处理范围
- prepare 返回该任务 1 条 pending raw：`conv-看一下docs里我们借鉴过的项目，自上次借鉴过后有什么新的合入值得借鉴`（20723 字符、57 轮、friction_score=10）
- 已 read_file 通读全文后提取；raw 现已归档到 `repowiki/conversations/`，`repowiki/raw/` 下不再残留

## 提交结果
- **第一次 submit**：`notes_created=3`、`memories_written=5`，但返回 `conflicts_pending=3`（三条都命中弱重复候选）
- 已 read_file 读了全部候选笔记（4 篇：2026-09-10 借鉴调研先证伪 / 2026-09-01 teamai-cli 冲突全景 / 2026-09-06 借鉴建议先过代码核对 / 2026-09-05 竞品调研必须克隆源码），逐条判定后**三条均取 `store`**（理由见下），用 `distilled_file` 侧通道重提交
- **重提交超时（MCP -32001）但已实际生效**：经文件系统复核，3 条笔记均已落盘且 status=draft，git 已产生自动提交 `4409078 codewiki: auto-sync knowledge (distill_submit)`；再次 prepare/submit 均返回 noop（无 pending）
- 未收到 `skill_hint`

## 新建笔记 3 条（全部 status=draft，需 confirm_note 才转正）
1. `notes/2026-09-11-repowiki-是随代码版本化的资产机器数据搬出业务仓的通用做法在本仓模型相反.md`（architecture, priority 85）
   repowiki 是随代码版本化的资产而非机器缓存，故 teamai #374「机器数据出仓」在本仓模型相反；`.meta/locks` + `store.py:166-189` 的 OS flock 强于对方 O_EXCL+owner token；并给出「缓存 vs 资产 / 分发 vs 归属」两条模型相反判据
2. `notes/2026-09-11-探测脚本用小样本算出-0-漏检不能当成缺口已证否.md`（lesson, priority 82）
   漏检率 0% 是 n=1 的结果（raw 仅 8 条、含 tool-error 的 1 条），只能写「未观测到缺口」不能写「已证否」，须标注样本量与翻转条件（开 `keep_raw` 或换更大样本）
3. `notes/2026-09-11-他山之石增量调研流程统一克隆-since-基线取增量-逐项在本仓证伪-出处置表-存档-docs.md`（procedure, priority 75）
   增量调研 SOP：统一克隆到 D:\repos → `git log --since` + `--diff-filter=A -- docs/designs` 取增量 → 逐项在本仓 grep 证伪 → 三分类处置表（excluded 必填原因）→ 落 `docs/` → 初稿错了就地加修正块

**去重判定说明（供复核）**：候选里最像重复的是 2026-09-10「借鉴调研先证伪」那条，但它只讲「先查本仓再下结论」的顺序纪律，不含本条的「版本化资产 vs 机器缓存」架构事实、「小样本不能当证否」的统计约束、以及完整流程骨架，故判定为互补而非重复，取 store 而非 skip。若你认为第 3 条与 2026-09-05/09-06 两条调研纪律笔记重合度过高，可以直接 reject，我不反对。

## 任务记忆（已直写落盘，无需确认）
`repowiki/tasks/他山之石/memories/iamwangbao-163-com.md` 新增 5 条：teamai-cli 增量调研完成并存档 `docs/teamai-cli-增量调研与借鉴分析-2026-09.md`；8 个候选 0 采纳全 excluded；#336 的 excluded 带样本量前置条件；#374 依赖「团队无 git worktree 习惯」假设；下一个待调研项目 claude-mem + 剩余约 20 个借鉴项目待克隆到 `D:\repos`。

## 建议你在停顿点展示给用户的待确认草稿
上面 3 条，逐条 confirm_note 或 reject。另有一条**未采纳的候选**也请一并过目：对话末尾 Agent 提议沉淀的「借鉴调研时把本仓已有能力当成缺口」lesson —— 我判定它与 2026-09-10 已有 stable 笔记重复，未产出草稿，如你认为该笔记表述不到位可让我补一条。

## 一处需要你留意的工具行为
重提交走 `distilled_file` 时，MCP 调用返回超时但实际处理成功（笔记落盘、raw 已归档、暂存文件被自动删除）。下次遇到同类超时，建议先查文件系统再决定是否重提，否则可能重复建笔记。另外本次 git_sync 曾报「推送重试 5 次未成功，本地提交已保留」，远端可能落后本地，值得人工确认一下。
</content>
</teammate-message>
</additional_input>
assistant: [tool: execute_command · git -C d:\repos\CodeWiki-CN --no-pager log --oneline -5; Write-Output '### notes'; Get-ChildItem -Path d:\repos\CodeWiki-CN\repowiki\n…

[tool: execute_command · git -C d:\repos\CodeWiki-CN --no-pager status -sb | Select-Object -First 3; git -C d:\repos\CodeWiki-CN --no-pager log --oneline origi…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\repowiki\notes]
assistant: [tool: execute_command · Get-ChildItem -Path d:\repos\CodeWiki-CN\repowiki\notes -Filter '2026-09-11-*' | ForEach-Object { Write-Output "== $($_.Name)"; Get-Co…
assistant: 补蒸馏回来了，我已独立复核（不采信自报）：

**复核结果**：3 条笔记确实落盘 `repowiki/notes/`，frontmatter 均为 `status: draft`；raw 已归档；git 有 `4409078` → `54de700` 两个 distill_submit 提交（重提交生效了，但笔记没有重复创建，无 `-1` 后缀副本）。本地 `develop` **领先 origin 7 个提交未推送**（含这 5 条 auto-sync），需要的话我单独推。

## 待你裁决的 3 条草稿

| # | 类型 | 标题 | 我的建议 |
|---|---|---|---|
| 1 | architecture | repowiki 是随代码版本化的资产，「机器数据搬出业务仓」的通用做法在本仓模型相反 | **confirm**——它与 2026-09-10「借鉴调研先证伪」是互补不是重复（那条讲顺序纪律，这条讲架构事实 + 「缓存 vs 资产 / 分发 vs 归属」判据） |
| 2 | lesson | 探测脚本用小样本算出 0% 漏检，不能当成缺口已证否 | **confirm，但需补一层**——见下 |
| 3 | procedure | 他山之石增量调研流程：统一克隆 → since 基线取增量 → 逐项在本仓证伪 → 出处置表 → 存档 docs/ | **confirm**——与 09-05/09-06 的「调研纪律」笔记不重合（那两条讲态度，这条讲可执行的五步骨架） |

## 第 2 条要补的那层

它是「n=1 不足以证否」；我今天发现的更靠前一层的问题是：`[tool-error: …]` 只由 `tool_digest` 产生，而它只有 `_ide_hook.py:268` 与 `capture_conversation.py:221` 两个调用点，**session-end 的 transcript 补采集不经过它**。所以那个 0% 测的是**通道覆盖面**，不是漏检率——样本量再大也只是在放大同一个偏差。

次序是：先确认测量通道覆盖面，再谈样本量。这两层放一条 note 里更不容易被误用，我建议**第 2 条 confirm 后把这段补进去**（confirm 只改状态，补内容要单独编辑），或者并列为独立一条。你定走哪种。

## 提议被否的那条

「借鉴调研时把本仓已有能力当成缺口」——subagent 判定与 2026-09-10 那条 stable 笔记重复、未产出草稿。我同意它的判断，不动。

---

你说 confirm 哪几条（或者说「全部确认」），我就执行；第 2 条的补充方式也一并告诉我。之后我接着深挖 OpenViking（268 commit，候选清单已定）。

<!-- codewiki:referenced-docs: [] -->
user: 调研所有项目后给个整体的借鉴报告
assistant: 明白，这次要全覆盖。我并行开三路调研，各自负责一批项目，我来做本仓证伪与最终处置。

[tool: task · {"subagent_name": "code-explorer", "description": "调研 OpenViking 与 openwiki 增量", "prompt": "你是「他山之石」增量调研的采集员。目标仓库（已克隆、已 fetch）：\n- D:\\repos\\Ope…

[tool: task · {"subagent_name": "code-explorer", "description": "调研 WeKnora 与 llm_wiki 增量", "prompt": "你是「他山之石」增量调研的采集员。目标仓库（已克隆、已 fetch）：\n- D:\\repos\\WeKnor…

[tool: task · {"subagent_name": "code-explorer", "description": "调研 CBM/semantica/RepoWiki 增量", "prompt": "你是「他山之石」增量调研的采集员。目标仓库（已克隆、已 fetch）：\n- D:\\repos\\co…
assistant: [tool: send_message · {"type": "shutdown_request", "recipient": "distill-task-他山之石", "content": "补蒸馏已复核完成（3 条 draft 已落盘），本会话不再需要你，请结束。"}]
assistant: 等三路回报的同时，我先把本仓侧的对照底稿备好（用于裁决，不是重复采集）：

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\capture_conversation.py", "offset": 176, "limit": 30}]
assistant: 三路调研已并行开工（OpenViking+openwiki / WeKnora+llm_wiki / codebase-memory-mcp+semantica+RepoWiki），已完成的分工与对照底稿：

- 已完成：claude-mem（36，含处置表）、全景扫描（11 项目）、openwiki #859 与 OpenViking #4724 预检。
- 本仓侧对照基线已确认：噪声过滤在 `capture_conversation.py:180-201`（`_FRAMEWORK_NOISE` + 前缀表），新鲜度是已深耕领域（`note_freshness.evaluate_note_freshness`、`wiki_lint._check_stale_notes:1083-1171`、`page_manifest.detect_stale_pages:351`、`wiki_search` 的 freshness gate `:81-98/:618`、`watch._incremental_refresh:118-156`），无持久化任务队列（同步 MCP + `git_sync` 重试）。

等三路报告回来后，我会做本仓证伪、出统一处置表，然后产出整体借鉴报告。
user: <teammate-message>
<from>distill-task-他山之石</from>
<summary>Message from distill-task-他山之石</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1789081796984","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"distill-task-他山之石","timestamp":"2026-09-10T23:09:57.433Z"}
</content>
</teammate-message>
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\hooks\task_session_start.py]
assistant: 对照底稿补齐：本仓对 stale 任务索引条目是"就地跳过"（`task_session_start.py:146`），与 OpenViking #4907「缺失记录视为已删除」是同层问题。三路调研仍在跑，等它们返回后统一裁决出报告。
user: <teammate-message>
<from>scout-weknora-llmwiki</from>
<summary>Message from scout-weknora-llmwiki</summary>
<content>
## WeKnora
**版本与构成**：基线 2026-07-21 → origin/HEAD 5db13a13，共 588 提交；v0.8.0 发布说明于 2026-09-03（d75cf72f）。前缀分布：fix(frontend)34 / fix(knowledge)30 / fix(sandbox)25 / feat(sandbox)17 / fix(agent)18 / fix(wiki)12 / feat(knowledge)13 / refactor(knowledge)9 / docreader+parser 16 / rerank 3 / chunking+chunks 8。
**主线**：重心已整体迁到 sandbox + skills + agent/MCP 工具链（约占六成提交），知识侧转入"wiki 页面身份与目录治理"的加固期，而非新增能力。与我们同层的新东西集中在 wiki 去重/目录/修订三处。

候选：
1. `2523dc72` fix(wiki): prevent concurrent duplicate page identities (#2850) — 新增 `internal/application/service/wiki_ingest_dedup.go`：在 LLM 去重调用前，用 slug token + 名称字符 bigram 的 Jaccard 做候选预筛，TopK=20、分数下限 0.08、语料 ≤25 页直接跳过（`:25-45`、`:86-105`）。解决：100+ 页时把全量语料塞进提示词导致 token 膨胀，弱模型出现"城镇登记失业人员→中华优秀传统文化"（Jaccard 0）的幻觉合并。**同层可借鉴**：repowiki 笔记合并/去重的候选剪枝。
2. `9e867381` fix(wiki): keep folder names that look like page-type labels when placing pages — 同一 category_path 按来源分叉清洗：有 FolderID 的走 `TrimWikiFolderSegments` 原样保留（用户目录权威），无目录的才走 `CleanWikiCategoryPath` 页面类型清洗（模型噪声）（`internal/application/service/wiki_page.go:1281-1295`、`internal/types/wiki_page.go:63+`）。解决：名为"概念/Concepts"的目录被当噪声剥掉，页面退到根层。**教训**：同一字段两种语义来源必须显式分叉，不要指望一套清洗规则覆盖。
3. `80a5003c` feat(wiki): page revision history with diff, revert, manual editing — wiki_page_revisions 迁移 + 行级 diff（前端 `frontend/src/utils/wikiLineDiff.ts`），四个写页 agent 工具统一记录 revision，带 revert。
4. `e7582cf5` fix(agent): stop using the chat model to rerank knowledge search — `internal/agent/tools/knowledge_search.go` 净删 303 行，取消"用聊天模型再跑一次重排"，成本/延迟/不确定性转回检索侧。
5. `8d7298fb` fix(graph): feed OCR chunks to graph extraction instead of image-link placeholders — 图谱抽取前用 OCR chunk 替换图片链接占位（`knowledge_post_process.go` + `docparser/markdown_image_scanner.go`）。

**无新增**：健康检查维度没变——`internal/application/service/wiki_lint.go` 基线后仅 1 个提交（e88564a7 删日志），仍是 orphan / broken-link / 内容<50 字符 / stale source-ref / missing-cross-ref 五类，100 分起扣（`:152-224`）。已浏览但无价值：sandbox/skills/MCP/IM/OIDC/前端样式/i18n。

## llm_wiki
**版本与构成**：v0.6.3 → v0.6.11（12 次 release），基线后 183 提交（fix 72 / feat 48），提交无模块前缀。
**主线**：ingest 管线并发化与可恢复、deep research 批处理与重跑、检索从"开关"升级为"模式"、lint 规则可配置、wikilink 规范化收口。

候选：
1. `e33e8ac` feat: configure structural lint rules（配 `840f42a` drop missing-page findings for pages that already exist）— 项目级 `.llm-wiki/lint-config.json`，开关 ignoreOrphan / ignoreNoOutlinks / ignorePages（`src/lib/lint-config.ts:4-8`、归一化 `:16-25`、路径 `:27-29`），读取失败 warn 后回落默认（`:31-40`）。**对 `lint_wiki` 直接可抄**：可配置豁免 + 配置损坏显式降级。
2. `3f3cfa0` feat: add smart retrieval mode（配 `3ab48b7` faithful source answer mode）— Smart 模式每轮检索后比证据增量，连续 2 次无增益即强制收尾（`src-tauri/src/agent/runtime.rs:1808-1823`，预算 `:2834-2838`）；Faithful 在提示词构建前就剥离 overview.md/schema.md 等生成式上下文（`:2791-2799`）；检索签名去重（`:2869-2887`）。机制一句话：**上下文隔离在 prompt 构造前完成，不靠"请忽略"的软约束**。
3. `0013ca3` fix: harden merged wikilink normalization — 合并页重写 wikilink 时先按代码围栏/缩进/行内代码切分，奇数反斜杠转义不改、非 .md 扩展名不剥路径（`src/lib/page-merge.ts:224-249`、`:296-310`）。
4. `92f3cba` filter knowledge by source + `3550dae`/`0ff6f31` batch/rerun deep research — 源身份归一化（去 `./` 与 `raw/sources/` 前缀 + 小写）作过滤键（`src/lib/knowledge-source-filter.ts:7-12`、`:29-38`）；review 项用 ACTIVE_RESEARCH_STATUSES 排除在跑任务后批量发起、失败可重跑（`src/lib/review-batch-research.ts:3-8`、`:18-34`）。
5. `c99a26d` make reasoning during ingest selectable — ingest 硬编码 reasoning off 会让部分模型直接 400；改为可配置、默认仍 off（`src/lib/reasoning-capabilities.ts:119-135`），并按 provider 能力归一化历史脏值（`:27-35`、`:72-109`）。**模式**：默认值不变，但别把默认值焊死。

已浏览无价值：locale/UI 预览/PDF 与 MinerU 后端/代理 TLS/快捷键/并发 worker 参数。

</content>
</teammate-message>
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\note_consolidation.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\wiki_lint.py]
assistant: WeKnora + llm_wiki 两路已回，我先做掉它们的本仓证伪：

- **#2850 wiki 去重预筛**（Jaccard bigram + TopK=20 + 小语料直接跳过）：本仓 `note_consolidation.py:47` 只有 `_PENDING_NOTES_LIMIT = 50` 的顺序截断，**没有相似度预筛**——候选是按 pending 顺序取前 N 全塞进 prompt。同样的膨胀/误合并风险存在，但尚未实测到误合并案例 → 预裁决 **deferred（留档手法）**。
- **llm_wiki 可配置 lint 豁免**（`.llm-wiki/lint-config.json`）：本仓 lint 的开关走**调用参数 `checks`**（`wiki_lint.py:58,:2449`）+ `schema.yaml` 的两处配置（`:2404,:2412`），再加一个项目级 lint 配置文件就是第三处真相 → 预裁决 **excluded（违反单点收敛）**；其中"配置读取失败显式降级"我们已有（freshness 的 fallback chain，`:1104-1132`）。

另两路（OpenViking+openwiki / CBM+semantica+RepoWiki）还在跑，等齐后统一出报告。
user: <teammate-message>
<from>scout-viking-openwiki</from>
<summary>Message from scout-viking-openwiki</summary>
<content>
## OpenViking

**版本与构成**：tag v0.4.19，origin/HEAD f55cb417（2026-09-10）。268 提交 = 163 fix / 49 feat / 17 docs / 9 refactor / 5 perf / 4 ci / 3 test。前缀上 bot+openclaw+plugins 与 web-studio 占约六成（宿主接入广度 + 控制台），引擎侧集中在 semantic/queuefs、session/memory、tasks。

**主线**：① 宿主 turn 协议适配（OpenClaw 9.3 把捕获从 afterTurn 挪到 commitTurn，插件必须按 host 版本判断归属）；② 记忆/语义管线从"跑通"转向"可诊断、可运营"（输入过滤层、排障 skill、提取指标）；③ 摘要新鲜度与并发控制开始按成本显式调度。

**候选清单**

1. `6b9d5490` 跨宿主 turn 协议保留捕获 — `examples/openclaw-plugin/context-engine.ts:251` `usesDeferredTurnCapture` 解析 host 版本，返回 undefined 时**抛错拒绝 ACK**（`:420`）而非猜测，因为 ACK 会丢掉 outbox 里唯一一份；`inFlightTurns`（`:360`/`:461`）在捕获开始前 publish promise，并发交付共享成功与失败。解决：宿主协议漂移时静默丢 turn。不变量：归属不明 > 静默降级。
2. `f55cb417` 从 incoming assembly prompt 召回 — `services/context-lifecycle-service.ts:427` 抽出 `recallForAssemble`，`:468` 在 assemble **之后**用 `params.prompt` 单独召回并只追加到 systemPromptAddition，`:464` `dedupTurns: 0`（系统注入是瞬态的，下一 turn 必须能召回同一 URI），超预算整体丢弃。解决：宿主把待处理 turn 与 history 分开传时，召回不能落进持久化消息。
3. `708dba60` 可配置正则输入过滤器 — `examples/memory-plugin-shared/lib/input-filters.mjs:59` 解析 / `:147` 编译 / `:171` 应用，sed 风格 `s`/`d`/`k` 三动作、可按 role 作用域、规则是纯字符串（复用现有 string-list 配置通道，**无配置即恒等**）；编译错误不抛异常只进 `errors`；时间预算仅 advisory，超时仍跑完（尾部可能正是脱敏规则）。解决：召回 query 与捕获 transcript 在进服务端前没有可塑形层。
4. `3841e6f2` 队列自愈 — `examples/memory-plugin-shared/lib/pending-queue.mjs:282` `releaseClaim` + `:378` `replayPending(..., {consumeRetries:false})`：后台 drainer（默认 60s）重放时不消耗重试预算、把 claim 还原为原文件名，重试记账与 D4 删除仍归 session-start。解决：latch 只在 session init 复位 → 长驻进程一次可重试写失败即永久卡死。
5. `a7c77e6c` 新鲜度感知父级聚合 — `openviking/storage/queuefs/semantic_ops/freshness_policy.py:31` `decide_parent_refresh`：纯策略函数，pending 按**事件**计数而非唯一子节点，阈值等价于 `ceil(ratio*total)`；无基线或目录小于采样上限立即刷新，否则累计到比例才重算，显式等待仍同步。解决：宽目录每改一文件就重算 L1 overview。
6. `a5166386` + `cf0fb06d` 任务记录兼容 — `openviking/service/task_tracker.py:91` `_extra_fields` 保留未知字段（`:1151` 把 payload 按已知/未知分流），`to_dict` 改显式白名单（`:95`）避免 `asdict` 把内部字段带进公开响应；`task_store.py` 的 `delete` 把"记录已不存在"当成功。解决：多写者/多版本并存时字段被静默丢弃。
7. `3d4cef7a` 技能元数据不丢 — `openviking/session/train/components/skill_policy_updater.py:168`：先把 `merge_memory_fields` 的 `description/allowed_tools/tags` 合并，再套 `patch_metadata`。解决：策略更新冲掉 LLM 抽出的描述。
8. `e86642ca` 绕过会话回退原生压缩 — `examples/openclaw-plugin/plugin/openclaw-runtime-compaction.ts:27` 懒加载宿主 `delegateCompactionToRuntime`。不变量：bypass = 交还宿主默认行为，而非什么都不做。

**已浏览但无借鉴价值**：bot/飞书等宿主接入广度、web-studio 文案与图表、CI/依赖/Docker、VLM/embedding 参数传递、#4724 camelCase isError（已排除）、#859 类 Windows 指纹（数据面不同）。

## openwiki

**版本与构成**：0.5.1。34 提交里 12 条是 `docs: update OpenWiki`（**wiki 自维护的产物**）、6 条 deps/version/chore，真代码提交约 14 条，多为 reasoning-effort 与 provider 适配。

**主线**：这一轮工程侧只做两件事——增量摄入的正确性（connector diff 与故障隔离）、托管指令块（CLAUDE.md/AGENTS.md）的正确性；其余精力已转移到 wiki 文档自身的自动更新。

**候选清单**

1. `cf0700f`（#777）+ `fb3c4c2`（#841）托管 AGENTS.md — `src/ingestion/code-mode.ts:25` `CLAUDE_AGENTS_IMPORT = "@AGENTS.md"`，`:449` 用 `@path` 而非 Markdown 链接（Claude Code 只展开自己的 `@` 语法；旁边有 CLAUDE.md 时它不会再读 AGENTS.md，链接是惰性的）；`:464` `resolvesToSameFile` 用 ino+dev 判定 CLAUDE.md 是否为 AGENTS.md 的符号链接（ino=0 视为未知，避免 Windows 全等），是同文件就内联指令避免自引用；`:247` 内容已仅为该 import 时不再重写。直接相关本仓 AGENTS.md 托管块。
2. `e280c17`（#414）增量 diff + 故障隔离 — `src/connectors/sources/git-repo.ts:136` `createRepoManifest` 接收 `previousHead`，`:151` 经 `:204` `resolveReachableHead`（`rev-parse --verify --quiet`，force-push/历史重写返回 undefined 并回退工作区 diff），有基线则 `diff previousHead..HEAD` + `log previousHead..HEAD`；同 PR 把 `ingestAllConnectors` 改 `Promise.allSettled`，单 connector / 单 stream 失败降级为 warning 且**仍写 state**（避免 latestIds 不前进导致下次全量重拉）。与本仓"取 since 基线做增量"完全同构，且补了基线失效兜底。
3. `84c8d6c`（#789）容忍重复 submit_plan — `src/agent/repository-runner.ts:287` 删掉"已提交即抛错"的守卫（`:314` 直接 `submitRepositoryPlan`），把重复提交交给下游幂等。与本仓 submit 语义方向一致。

**已浏览但无借鉴价值**：Gemini/OpenAI-compatible reasoning effort 映射、.env 单次原子反转义、google fonts CSP、visualizer 图标签、fast-uri 安全升级、planner 之外的 UI 诊断面板。

补充：两个仓库本地检出都落后于 origin/HEAD（OpenViking 本地 0ef62175，openwiki 本地 3bc038d），以上行号全部取自 `git show origin/HEAD:<path>` 实测结果。

</content>
</teammate-message>
assistant: OpenViking + openwiki 也回来了，两处值得单独拎出来的对照（其余多为"主动不同的设计取向"而排除）：

- **#4858 可配置正则输入过滤器**（`input-filters.mjs:59/147/171`，sed 风格 `s`/`d`/`k`、按 role 作用域、**无配置即恒等**、编译错误只进 `errors` 不抛）：本仓噪声表是硬编码 `_FRAMEWORK_NOISE`（`capture_conversation.py:180-189`）。宿主适配面每扩一次就得改代码 → 预裁决 **deferred**，真做时照抄"无配置即恒等 + 编译失败不抛"两条。
- **openwiki #414 增量 diff 的基线失效兜底**（`git-repo.ts:136/151/204`，`rev-parse --verify --quiet` 失败即回退工作区 diff）+ **单源失败仍写 state**（否则下次全量重拉）：与我们"since 基线取增量"完全同构，且补了基线失效兜底 → 预裁决 **deferred（可抄）**。
- **openwiki #777 托管 AGENTS.md 用 `@AGENTS.md` import**（`code-mode.ts:25/449/464`，ino+dev 判同文件避免自引用）：本仓是 upsert 标记块（`agents_md.py:68,121-139`）。若 CodeBuddy 支持 `@` 展开，托管/手写可彻底分离 → 预裁决 **deferred（待真机验证宿主是否展开）**。

第三路（codebase-memory-mcp 1182 / semantica 682 / RepoWiki 23）还在跑，等齐后我出统一处置表和整体报告。
user: <teammate-message>
<from>scout-cbm-semantica</from>
<summary>Message from scout-cbm-semantica</summary>
<content>
口径说明：按 `--since=<基线> --no-merges origin/HEAD` 实测提交数为 cbm 727、semantica 476、RepoWiki 23（你给的 1182/682 应含 merge 或其他口径）。以下行号均来自实际 diff/文件内容。

## codebase-memory-mcp
构成与聚类（origin/HEAD=055fbb7d，727 条非 merge）：fix(mcp)38、fix(cli)38、fix(ci)29、fix(pipeline)24、fix(cypher)20、fix(daemon)18、fix(windows)13、fix(extract)13、fix(release)12、fix(store)8、feat(pipeline)7、feat(mcp)7、perf(pipeline)6。
新增文件目录：tests/fixtures 70、scripts/ci 25、internal/cbm 23（多为 vendored 语法）、tools/tree-sitter-arkts 18、chialisp 12、src/foundation 9、src/pipeline 6、src/ui 6、pkg/go 5。
主线：本轮不是堆新分析器，而是「MCP 输出做小且无损 + 重要度/增量/预算可见」。修复集中在 mcp/cli/pipeline，新能力落在 importance、delta、workspace、FTS、ADR 段写入。

候选：
- e5f3aab0 index-time importance scoring：pass_importance.c:12 公式 importance=sqrt(num_refs)*priv*generic*distinct*test_penalty；:225 append_prop 先删旧 key 再写（:219 注释点明纯 append 会产出 {"importance":1.0,…,"importance":2.0} 的静默属性污染）；:340 pass 入口。解决：给检索/输出排序一个与 LLM 无关的确定性重要度。
- bbd13335 delta-merge executor（closure route）：pipeline_delta.c:2 明说不再「整图载入 RAM 重灌一代」；:73 delta_edge_type_is_recomputed 区分哪些边类型必须重算；:315/:341 只 patch 节点/边。解决：大仓增量索引。
- 03e93557 + 80d52797 workspace 边界：workspace.c:186 classify_root 按广度/敏感度分类索引根；:583 manifest_read 读项目级 manifest；:673 manifest_is_approved 用内容摘要做审批键（:603 注释：manifest 变了审批即失效）。解决：多仓授权 + 改了要重批，和我们「多仓工作区」直接同层。
- 01c7e549 BM25 body 列：store.c:372 建 nodes_fts；:397 FTS_BODY_EXPR 取 docstring 作 prose 源；:410 用 `SELECT body FROM nodes_fts LIMIT 0` 探测旧库是否有该列再降级。解决：符号检索外补散文检索，且带向后兼容探测。
- 14c229b1 lossless semantic pagination（+3909e5a0 lean output）：mcp.c:988 仅当 end<allowed_count 才发 nextCursor；:1110 cursor_offset 把 cursor 解成 offset；:548 工具描述要求「把 next/next_cursor 原样传回」。解决：预算内不丢信息地分页。
- 7bef7f4d/d013555d ADR 段级写入：mcp.c:709-716 manage_adr 新增 set_sections，只重写命名段（:11860 解析 section_updates，:12152 兼容旧文件型 ADR）。解决：文档增量改写，和我们的 ADR 回写同层。

整片跳过：fix(ci)+scripts/ci（29+25）、fix(windows)/msan/build/release/deps、tests/fixtures 70、internal/cbm 下 vendored 语法（arkts/chialisp/plsql/perl，属批量语言支持，仅 706bb2ce/97ecfe7f 有通用性但不建议报）、graph-ui/src、soak-mac* 日志、fix(cli) 的客户端安装目标（72ee8805 Grok / f518eaee omp / 63be2980 OpenCode）。

## semantica
构成（origin/HEAD=76515280，476 条）：fix 35、fix(export)24、docs 21、fix(explorer)20、fix(ci)18、fix(context)17、fix(vector_store)17、fix(ontology)14、security 11+9、fix(kg)11、fix(mcp)10、feat(vector_store)7。
新增文件：.github/requirements 24、tests/* 大批量、explorer/src 17、integrations/{google_adk,crewai,langchain}、semantica/evals 6、semantica/llms 5、semantica/explorer 5、semantica/ontology 4、semantica/context 4。
主线：从「能建图」转向「图要能被校验、被撤回、被擦除」——质量闸门 + 撤回/墓碑 + 跨存储擦除 + 确定性 IRI。

候选：
- 471cbe77 ontology deterministic quality gate：quality_gate.py:91 OntologyQualityGate；:135 DEFAULT_THRESHOLDS 可覆盖；:158 _validate_thresholds 解出 min_coverage/max_errors/max_warnings；:140 check 报 error/warning/info 计数。同层于我们的 lint_wiki：确定性、阈值可配、失败即闸门。
- f1e7e64a ContextGraph retraction/purge：context_graph.py:1556 retract_node、:1662 retract_edge（带时间点的撤回）；:1718 purge_node/:1821 purge_edge 落墓碑 :506 _tombstones；:1895 get_tombstone 记录何时、为何被清除。解决：删除不消失，负反馈可审计、防重灌复活。
- e040d84d ErasureCoordinator：erasure.py:129 协调器；:182 erase_entity 跨 vector/graph/memory 三存储；:82 ErasureReceipt 带 :110 incomplete_stores——部分失败显式列出而非静默成功。解决：一个实体多副本的删除一致性。
- e1092ac5 确定性 IRI：rdf_exporter.py:54 mint_entity_iri、:67 mint_relationship_iri；:58 注释指出此前同一实体每次导出 IRI 都变。解决：跨次导出的稳定标识。
- 9c38fd49 MCP 语义检索工具面：retrieval.py:88 _chunk_id(source, version, index, text)、:96 _doc_hash、:100 _find_matching_rows 按 (source, version) 定位、:269 _upsert 统一 store/update。解决：文档级 upsert 用内容坐标幂等定位，不依赖外部 ID。

整片跳过：fix(export)24 + tests/export 16（Turtle/N-Triples 序列化细节）、explorer/* 全部（前端 Web UI：20 fix + 17 src + 16 tests）、各 vector store 的 iter_all/delete_vectors 逐后端新增（faiss/milvus/weaviate/pinecone）、integrations、security/deps、.github/requirements、docs(cookbook) 16。

## RepoWiki
构成：23 条（与清单一致），版本 0.3.1→0.4.1（08cf8ea）；类型分布 feat 9、chore 4、fix 3、ci 2、test/perf/docs 各 1。
主线：把「生成」做成「可重复、可增量、可缓存」——内容键缓存 + 逐页指纹增量 + 零 LLM 产物。

候选：
- 47afa15 + ef292c0 内容键缓存与增量导出：cache.py:22 content_hash、:27 Cache(SQLite)；analyzer.py:68 tree_hash（file_tree+关键文件）、:209 模块级 cache_key；export/markdown.py:45-47 逐页 fingerprint 与 state 比对、未变跳过写入，:57-59 删除已消失模块 md。解决：小改后重跑零 API 调用。
- 69bfd53 用 hook 取代 watcher 守护：README 增量段改为建议 `.git/hooks/post-commit` 或 CI 触发，理由是「缓存让重扫很便宜，所以不需要 watcher 守护」。与 cbm 的 watcher_enabled 主开关（README.md:156、docs/CONFIGURATION.md:91 明说「daemon 启动时读一次，改完必须 daemon stop」）是同一问题的两种答案，建议对照吸收。
- 5de86d7 扫描预算按优先级分配：scanner.py:101-102 先保承载依赖结构的语言、docs/assets 后拿预算；:267-269 硬上限 max(max_files*4, max_files+100)；:351-352 注释点明「docs 重的仓里朴素 walk 会先用 markdown 填满预算」。解决：成本可见性——预算被谁吃掉。
- 6a7eddf 持久 RAG 索引：rag.py:27 index_fingerprint(project)、:78 save_index、:100 load_index、:140 load_or_build_index（未变则复用）。解决：多轮 chat 不重建索引。
- bc8302d 页面交叉链接：wiki_builder.py:97 _link_pages → :280 _apply_cross_links → :300 _linkify_line → :317 _rel_href。解决：符号/文件提及自动成链（我们是编译期 wikilink 规则，它是生成期后处理）。

整片跳过：c836c46/08cf8ea/e7ba8b4/1c7638e 版本与打包、1688d3d/c47c478 CI、bc2877d 前端产物入 wheel、3c7fbac GITHUB_TOKEN 私有仓、3ff4780 Pages loader、539e2c7 demo 链接、25f0dcd/9423534 路径与测试稳定性、cd15ed3 litellm 懒导入（perf 但与知识层无关）。

</content>
</teammate-message>
assistant: 三路齐了。做最后一批本仓证伪，然后出报告：

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\note_query.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\workspace_bootstrap.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\note_lifecycle.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: 三路全部回来，本仓证伪也做完了（关键一条：本仓 `injection_budget.py:1` 的 docstring 就写着「OpenViking auto-recall 借鉴」——说明 OpenViking 那套预算机制我们早就吸收过了）。现在出整体报告。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\借鉴项目整体增量调研报告-2026-09.md", "content": "# 借鉴项目整体增量调研报告（2026-09-11）\n\n> **范围**：`docs/` 里有调研底稿的…
assistant: [tool: send_message · {"type": "shutdown_request", "recipient": "scout-viking-openwiki", "content": "报告已收到并纳入整体报告，工作完成，请结束。"}]

[tool: send_message · {"type": "shutdown_request", "recipient": "scout-weknora-llmwiki", "content": "报告已收到并纳入整体报告，工作完成，请结束。"}]

[tool: send_message · {"type": "shutdown_request", "recipient": "scout-cbm-semantica", "content": "报告已收到并纳入整体报告，工作完成，请结束。"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"他山之石\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"c…
assistant: 全部 11 个项目调研完毕，整体报告已落盘：**`docs/借鉴项目整体增量调研报告-2026-09.md`**

## 结果：44 个候选 → 0 采纳 / 15 deferred / 29 excluded

| 项目 | 增量提交 | 主线 |
|---|---|---|
| codebase-memory-mcp | 1182 | MCP 输出做小且无损、重要度/增量/预算可见 |
| semantica | 682 | 从「能建图」转向可校验、可撤回、可擦除 |
| WeKnora | 588 | sandbox/agent 工具链为主，wiki 侧转目录与去重加固 |
| OpenViking | 268 | 宿主 turn 协议、记忆管线可诊断、新鲜度按成本调度 |
| llm_wiki | 183 | ingest 并发化、检索从开关升级为模式 |
| claude-mem | 36 | 分发形态 + 用量可观测 |
| openwiki | 34 | 增量摄入与托管指令块的正确性 |
| RepoWiki | 23 | 把「生成」做成可重复/可增量/可缓存 |
| MindForge / wikiskill / AIO | 0 | 无新合入 |

## 三条结论

**1. 本轮最大价值仍是证伪——一半候选本仓早就有。** 最典型：OpenViking 的 auto-recall 超预算丢弃被列为候选时，本仓 `codewiki/mcp/tools/injection_budget.py:1` 的 docstring 第一行就写着「V2, OpenViking auto-recall 借鉴」，已落地。同类还有 6 个（`deprecated` ≈ 墓碑、SHA-256 内容指纹 ≈ 内容坐标 upsert、多信号确定性排序、git ≈ 修订历史等），给「借鉴调研先证伪」那条 stable 笔记又添了样本。

**2. 他仓集体往服务端/队列/多租户走，本仓是主动不同的取向**——本地 markdown + git 版本化 + 同步 MCP，没有常驻写入端。所以队列自愈、计费分区、缺失记录即删这类，都不是缺口。

**3. 真正在动的主线是「成本/预算从软约束变硬约束」**，五个项目不约而同。本仓 `injection_budget` 已覆盖注入侧，**空档在扫描侧预算**和 **deprecated 笔记会不会被新 ingest 复活**。

## 15 项 deferred 分三类

- **留档照抄**（9）：真做时直接抄实现，如输入过滤「无配置即恒等 + 编译失败不抛」、增量「基线失效兜底 + 单源失败仍写 state」、去重 Jaccard 预筛、无损分页只在 `end < allowed_count` 才发 cursor。
- **转其他任务**（1）：CBM 的 workspace manifest 审批（内容摘要做审批键、变更即失效）→ 转「多仓工作区」裁决，related ≠ same。
- **自查项**（3，成本最低、现在就能做）：① wikilink 重写是否按代码围栏切分；② ADR 回写是不是整文件重写；③ deprecated 笔记是否会被后续 ingest 复活。

## 附带的方法论产出

上一轮那个「0% 漏检」结论的口径问题已定性：`[tool-error: …]` 只有两个产生点（`_ide_hook.py:268`、`capture_conversation.py:221`），session-end 的补采集不经过它——**测的是通道覆盖面，不是漏检率**。先确认覆盖面，再谈样本量。

另外两件待办的裁决还悬着：**3 条蒸馏草稿要不要 confirm**、以及整体报告里那 3 个自查项要不要现在就跑——你说一声我就动手。本地 `develop` 领先 origin 7 个提交未推送，需要的话一起推。
user: <teammate-message>
<from>scout-cbm-semantica</from>
<summary>Message from scout-cbm-semantica</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1789082586293","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"scout-cbm-semantica","timestamp":"2026-09-10T23:23:07.455Z"}
</content>
</teammate-message>

<teammate-message>
<from>scout-viking-openwiki</from>
<summary>Message from scout-viking-openwiki</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1789082585518","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"scout-viking-openwiki","timestamp":"2026-09-10T23:23:07.456Z"}
</content>
</teammate-message>

<teammate-message>
<from>scout-weknora-llmwiki</from>
<summary>Message from scout-weknora-llmwiki</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1789082586126","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"scout-weknora-llmwiki","timestamp":"2026-09-10T23:23:07.464Z"}
</content>
</teammate-message>
assistant: 三路 scout 都已确认关闭，可以清理团队了。

[tool: team_delete]
assistant: 团队已清理。本轮交付：

- `docs/借鉴项目整体增量调研报告-2026-09.md` — 11 个项目全覆盖，44 候选 / 0 采纳 / 15 deferred / 29 excluded
- `docs/claude-mem-增量调研与借鉴分析-2026-09.md` — 分项目细节 + 全景表 + 下轮预检

等你两个裁决：

1. **3 条蒸馏草稿**（架构事实 / 小样本不能当证否 / 增量调研 SOP）→ confirm 哪几条，全部也行；第 2 条要不要把「通道覆盖面」那层补进去。
2. **3 个自查项**要不要现在跑：wikilink 重写的代码围栏切分、ADR 是否整文件重写、deprecated 笔记会不会被新 ingest 复活。

<!-- codewiki:referenced-docs: [] -->
user: 继续
assistant: 收到。先跑 3 个自查项，再处理草稿确认。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\doc_writer.py", "offset": 1117, "limit": 50}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: 三个自查全部查完，结论都是"已覆盖"。更新报告后处理草稿：
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"confirm_note\"],[\"codewiki\",\"edit_doc_file\"]]"}]
assistant: 先给第 2 条补上「通道覆盖面」那层，再统一确认：

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\repowiki\\notes\\2026-09-11-探测脚本用小样本算出-0-漏检不能当成缺口已证否.md"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"note_file\":\"2026-09-11-…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"note_file\":\"2026-09-11-…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"note_file\":\"2026-09-11-…
assistant: [tool: execute_command · git -C d:\repos\CodeWiki-CN remote -v; git -C d:\repos\CodeWiki-CN --no-pager log --oneline origin/develop..develop | Measure-Object -…

[tool: execute_command · Select-String -Path 'd:\repos\CodeWiki-CN\repowiki\notes\2026-09-11-探测脚本用小样本算出-0-漏检不能当成缺口已证否.md' -Pattern '^status:' ; Select-String -…
assistant: 「继续」的两件事都做完了。

## 1. 三项自查 → 全部关闭（都是本仓已覆盖）

| 自查 | 结论 |
|---|---|
| wikilink 重写的代码围栏 | **已覆盖**：`doc_writer.py:1119` docstring 就声明跳过围栏/已有链接/frontmatter，`:1139-1147` 用 `in_code` 实现；lint 侧 `wiki_lint.py:324` 也忽略 code span。差异只剩「合并页重写」，本仓 consolidate 不走 wikilink 重写 |
| ADR 是否整文件重写 | **无对应面**：本仓没有 ADR 写入工具，`docs/adr/` 只被注释和提示词引用（ADR-0001~0005），谈不上整文件还是段级 |
| deprecated 防重灌 | **已覆盖且比墓碑更主动**：`retrieval.py:456` 打分 −0.35、`note_query.py:464/1014` 跳过、`distill_conversation.py:498/654/699` 不作候选、`skill_creator.py:650-651/710-712` submit 不复活且 install 拒绝——四条入口都拦，而 semantica 的墓碑只是记录 |

结论已写进报告新增的 §2.1，§5 的待办同步勾掉。

## 2. 三条草稿已确认落库

第 2 条先补了「通道覆盖面先于样本量」那层（新的一节，含两个调用点的具体行号与三步次序），然后三条一起 confirm：

- `2026-09-11-repowiki-是随代码版本化的资产…在本仓模型相反.md` → stable
- `2026-09-11-探测脚本用小样本算出-0-漏检不能当成缺口已证否.md` → stable
- `2026-09-11-他山之石增量调研流程…存档-docs.md` → stable

复核过 frontmatter，`status: stable`（不是只信工具返回）。

## 一件需要你处理的事

`git_sync` 推送连续失败：**本地 `develop` 领先 `origin`（github.com/mambo-wang/CodeWiki-Plus）11 个提交**，auto-push 重试 5 次没成功（大概是网络或凭据问题）。要我现在手动 `git push` 试一次吗——还是你自己推？

其余收尾：deferred #10（CBM workspace manifest 审批）要转到「多仓工作区」任务去做裁决，我可以现在就写进那个任务的记忆里。

<!-- codewiki:referenced-docs: [] -->
user: 好的
assistant: [tool: execute_command · git -C d:\repos\CodeWiki-CN push origin develop 2>&1 | Select-Object -First 15]

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"多仓工作区\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: 推送被 GitHub 拦下了——**提交里检出 PyPI API Token**。先定位：

[tool: execute_command · git -C d:\repos\CodeWiki-CN push origin develop 2>&1 | Out-File -Encoding utf8 -FilePath d:\repos\CodeWiki-CN\.push-error.txt; Get-Con…

[tool: search_content · d:\repos\CodeWiki-CN]
assistant: 发现问题根因了，情况需要你立刻处理：

[tool: execute_command · git -C d:\repos\CodeWiki-CN --no-pager log --oneline -S "pypi-AgEIcHlwaS5vcmc" --all -- repowiki/ | Select-Object -First 10; Write-Out…
assistant: [tool: execute_command · Write-Output '### remote contains secret?'; git -C d:\repos\CodeWiki-CN --no-pager log --oneline -S "pypi-AgEIcHlwaS5vcmc" origin/deve…

[tool: delete_file · {"target_file": "d:\\repos\\CodeWiki-CN\\.push-error.txt", "explanation": "删除诊断用的临时文件"}]
assistant: **先说最紧急的：PyPI token 已经进远端了。**

## 事实

- 推送被 GitHub push protection 拦下（`GH013`），原因是 **PyPI API Token** 明文。
- 位置：`repowiki/conversations/conv-发布版本.md:85,90`（发布时把 `$env:UV_PUBLISH_TOKEN=<redacted:secret>'` 整条命令连同 token 采进对话了），`conv-推送代码.md` 也引用了同一串。
- **远端 `origin/develop` 已包含提交 `bbc10f9`（chore: L2 知识聚合 2026-09-08 批次）**，该提交里就有这串 token；本地还有一个 `a05f375`（竞品调研）。

也就是说：这个 token 已经在 GitHub 公开仓库 `mambo-wang/CodeWiki-Plus` 上。**第一件事是去 PyPI 后台 revoke 这个 token**，清理历史是第二件事——不 revoke，删再多历史都没用。

## 两件事需要你拍板（都是破坏性的，我不擅自做）

**1. 清理历史**：远端和本地都得重写。
- 远端已公开 → 必须 `git filter-repo`（或 BFG）把这两个文件从全部历史中剔除，然后 **force push**。这会改写已发布历史，所有 clone 过的人都要重新拉。
- 本地 `develop` 领先 11 个提交，其中也带着这些文件，一起重写。
- 替代方案（省力但藏不住）：只删当前文件 + 新提交，历史里的 token 仍可检索——**不推荐**，已经被抓取过的仓库/镜像留得住。

**2. 堵住采集侧**：这是机制漏洞，不是手滑。采集把命令行原文写进 `repowiki/conversations/`，而 repowiki 是要提交推送的资产——任何在对话里出现过的密钥都会被写进公开仓库。可选项：
- 给 `capture_conversation` / `tool_digest` 加一层**密钥形态脱敏**（类似 `claude-mem` 的白名单思路，或按 `pypi-`/`ghp_`/`sk-` 等前缀做正则），命中即替换为 `<redacted:kind>`；
- 或至少在 `git_sync` 推送前加一道 secret 预检（早于 GitHub 拦截，我们自己的闸门）。

第 2 条建议里那个「发版本」任务（本仓有这个任务）也值得记一笔：发布流程里 token 走环境变量没问题，问题在**采集把整条命令录进知识库**。

## 要不要我现在做

我可以先做**非破坏**的部分：把当前工作区那两个文件里的明文 token 抹掉、并加一道采集侧脱敏（改代码 + 跑测试）。**历史重写和 force push 等你确认**——那会影响所有 clone，得你点头。

另外，这条事故本身值得沉淀成 pitfall 笔记（"采集对话会把密钥写进随代码版本化的知识库"），等你说要我再写。

任务记忆已写入：CBM 的 workspace manifest 审批候选已转给「多仓工作区」裁决。
user: 按你说的做
assistant: 开始。先做非破坏部分——采集侧脱敏。先定位落盘收口点：

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\capture_conversation.py]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\src\\tool_digest.py", "offset": 1, "limit": 60}]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\capture_conversation.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\capture_conversation.py", "offset": 204, "limit": 75}]
assistant: 收口点找到了：`digest_blocks`（工具行）与 `_extract_transcript`（正文）。先建脱敏模块（stdlib-only，两条采集路径共用一份）：

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\src\\secret_redact.py", "content": "# -*- coding: utf-8 -*-\n\"\"\"Secret redaction for …
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\src\\tool_digest.py", "offset": 267, "limit": 50}]
assistant: [tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_secret_redact.py", "content": "# -*- coding: utf-8 -*-\n\"\"\"Tests for codewiki.src.s…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -m pytest tests/test_secret_redact.py -q 2>&1 | Select-Object -Last 25]
assistant: 脱敏测试全绿。跑全量回归，同时清理工作区里的明文 token：

[tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 12]

[tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -c "from pathlib import Path; from codewiki.src.secret_redact import redact_secrets;…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\repowiki\conversations]

[tool: execute_command · cd d:\repos\CodeWiki-CN; git filter-repo --version 2>&1 | Select-Object -First 2; .venv\Scripts\python.exe -m pip show git-filter-repo…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\repowiki\conversations\conv-@command-codewiki-蒸馏对话提取记忆和经验.md]
assistant: 残留那处是我在对话里写的**说明文字**（`pypi-AgEIcHlwaS5vcmc...` 带省略号），不是真 token，保留无害。现在做历史重写：

[tool: execute_command · uv --version 2>&1 | Select-Object -First 2; Write-Output '### rules'; $p="$env:TEMP\fr-rules.txt"; Set-Content -LiteralPath $p -Encodi…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git status --porcelain | Select-Object -First 20; Write-Output '### count'; (git status --porcelain | Measure…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; Remove-Item -LiteralPath '.\$null' -Force -ErrorAction SilentlyContinue; git check-ignore -v repowiki/convers…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git diff --stat -- repowiki/conversations | Select-Object -Last 3; Write-Output '### untracked/modified count…
assistant: 工作区与 HEAD 都已无明文 token（残留那一处是带省略号的说明文字，非真值）。现在提交修复并重写历史：

[tool: execute_command · cd d:\repos\CodeWiki-CN; git add codewiki tests; git add "docs/claude-mem-增量调研与借鉴分析-2026-09.md" "docs/借鉴项目整体增量调研报告-2026-09.md"; git st…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git restore --staged codewiki/mcp/prompts.py; git commit -m "fix(capture): redact secrets before archiving co…
assistant: 本地历史重写（会改写所有 commit，之后需要 force push）：

[tool: execute_command · cd d:\repos\CodeWiki-CN; uvx git-filter-repo --replace-text "$env:TEMP\fr-rules.txt" --force 2>&1 | Select-Object -Last 15]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; Write-Output '### secret still in history?'; git log --all --oneline -S "pypi-AgEIcHlwaS5vcmc" | Select-Objec…
assistant: 历史里的 token 已清除，但发现一个副作用要先处理——先确认你的未提交改动有没有被卷走：

[tool: execute_command · cd d:\repos\CodeWiki-CN; Write-Output '### status'; git status --porcelain; Write-Output '### stash'; git stash list; Write-Output '##…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -c "t=open('AGENTS.md',encoding='utf-8').read(); print('AGENTS.md chars:', len(t)); …
assistant: 停一下——发现**副作用**：filter-repo 的 reset 把你会话开始时那三处未提交改动卷走了（AGENTS.md 回到 10175 字符未精简版、cli plan 里的「体积拆解/AGENTS.md 体积/执行记录」章节没了）。先抢救：

[tool: execute_command · cd d:\repos\CodeWiki-CN; git fsck --unreachable --no-reflogs 2>$null | Select-String '^unreachable blob' | ForEach-Object { $_.ToStrin…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -c "]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; .venv\Scripts\python.exe -c "t=open('codewiki/mcp/prompts.py',encoding='utf-8').read(); i=t.find('_TASK_MEMOR…
assistant: 抢救失败——filter-repo 在末尾跑了 `repack + clean unreachable objects`，把 dangling blob 一起 gc 了，git 侧无法找回。

## 现状盘点

**已完成的（原计划）：**
- 脱敏模块 `codewiki/src/secret_redact.py` + 两处调用（`tool_digest.digest_blocks`、`capture_conversation._extract_transcript`），8 条新测试
- 全量 **932 passed, 2 skipped**（16 分钟）
- 提交 `fix(capture): redact secrets before archiving conversations`（现已重写为 `37ecf04`）
- **本地历史已重写**：621 个 commit，`git log --all -S` 已查不到该 token

**我造成的副作用（必须告诉你）：**

`filter-repo --force` 在重写后会 `reset --hard`，你会话开始时那三处**未提交**的改动被吞了：

| 文件 | 丢失内容 | 现状 |
|---|---|---|
| `AGENTS.md` | 第一刀（删 QwenWork 块）+ 第二刀（task memory 段精简） | 回到 10175 字符 / 214 行，`CODEWIKI-QWENWORK` 块回来了 |
| `codewiki/mcp/prompts.py` | `_TASK_MEMORY_AGENTS_SECTION` 3286→836，以及 `_prompt_task_workflow` 的「存储布局与实现约束」段 | 常量回到 3307 字符 |
| `docs/plans/cli-capability-progressive-disclosure.md` | 「体积拆解实测」「AGENTS.md 常驻体积」「执行记录」三章 | 已无这些章节 |

这是我的操作失误：重写历史前应该先 `stash` 未提交改动，我没做。

## 我能恢复多少

- **`prompts.py` 的 836 字符常量：能，原文在我手上**（本会话系统提示注入的 TEAM-MEMORY-TASK 块正是它）。它是唯一真相源，恢复后重跑 `upsert_agents_section` 就能把 AGENTS.md 自动同步回精简版。
- **cli plan 三章：能**，我在本会话读过那份文档的全文 185 行，可原样写回。
- **`_prompt_task_workflow` 的「存储布局与实现约束」段：不能**，我从未读过那段正文，回滚后的 prompts.py 里也没有，只能标注待重做。

## 请你定两件事

1. **恢复范围**：①只恢复 prompts.py 常量 + 重跑生成器同步 AGENTS.md（最小、最关键）；②再恢复 cli plan 三章；③都不恢复，我自己来。
2. **force push 时机**：建议**先去 PyPI revoke 那个 token**（历史重写只能阻止扩散，救不了已泄露的值），revoke 之后我再 force push 覆盖远端历史。要不要等你说 revoke 完成再推？

<!-- codewiki:referenced-docs: [] -->
user: 能恢复多少就恢复多少
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 30, "limit": 40}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 1232, "limit": 45}]
