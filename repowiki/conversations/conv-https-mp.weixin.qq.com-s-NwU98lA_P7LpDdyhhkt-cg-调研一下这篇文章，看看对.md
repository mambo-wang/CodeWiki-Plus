---
type: Conversation
title: "conversation 20260906T151817Z"
status: distilled
stale_after: 2026-12-05
generated: { by: codewiki/5.6.1, at: 2026-09-06T15:18:17Z }
captured_at: "2026-09-06T15:18:17Z"
content_hash: "sha256:c43c73cb3df59f7b88bc9cb7e1b6f725c12033189d31116f5f7741b49c6a54cc"
friction_score: 5
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=4"
keep_raw: false
link_to: ""
source_session: "4a93b9221bce4788a5ebc8bc4be149ce"
task_id: "他山之石"
turn_count: 42
---

# Conversation Transcript

user: https://mp.weixin.qq.com/s/NwU98lA_P7LpDdyhhkt-cg  调研一下这篇文章，看看对我们有什么借鉴价值吗
assistant: [tool: ask_followup_question · {"questions": [{"question": "本次会话要关联哪个任务？（关联后本会话的对话会自动带上 task_id，并触发积压对话的后台补蒸馏）", "header": "任务关联", "options": ["新建任务（请在下一个弹框输入任…
user: <question>本次会话要关联哪个任务？（关联后本会话的对话会自动带上 task_id，并触发积压对话的后台补蒸馏）</question>
<answers>
他山之石
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"]]"}]

[tool: web_fetch · https://mp.weixin.qq.com/s/NwU98lA_P7LpDdyhhkt-cg]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"4a93b9221bce4788a5ebc8bc4be149ce\",\"t…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"他山之石\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"query_wiki\"]]"}]

[tool: task · {"subagent_name": "distill-worker", "description": "蒸馏他山之石积压对话", "prompt": "请对任务「他山之石」（task_id=他山之石）的 2 条未蒸馏 raw 对话执行补蒸馏，走 Mode C（纯 MCP JSON）流程：\…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"query\":\"渐进式披露 分层导航 向量检索 检…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"query\":\"CodeWiki 内容定位 概念 …
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki]

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"query\":\"调研报告的借鉴建议必须先过代码核对…
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_query.py]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki/src/be/dependency_analyzer]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/tools/skill_creator.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_query.py]

[tool: search_content · d:/repos/CodeWiki-CN/repowiki/schema.yaml]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki]

[tool: search_content · d:/repos/CodeWiki-CN/repowiki/schema.yaml]
assistant: 已绑定任务「他山之石」，并拉取了上下文（2 条积压 raw 待蒸馏；本轮蒸馏子代理未拿到 codewiki MCP 权限，稍后我自己在自然停顿点处理）。

## 文章是什么

有赞共享技术的《KNOWLEDGE WIKI：面向 AI 的项目知识层建设实践》——在 workspace 里用 `.wiki/` 目录建分层领域知识库，配一个可安装的 skill（read/init/update 三模式），让 Agent「遇事先查 wiki、有收获就提案沉淀」。

## 核对后的总体判断：高度同构，我们在多数维度已经更强

按本仓库的纪律，借鉴建议先过代码核对（依据：`notes/2026-09-06-调研报告的借鉴建议必须先过代码核对b2b1-痛点表述与实际不符的三处教训.md`，draft 未确认）：

| 文章主张 | CodeWiki 现状（本次代码核对） | 判定 |
|---|---|---|
| 渐进式披露替代向量检索 | 已有且更硬：`query_wiki` 四档 `overview/directory/detail/check`（`codewiki/mcp/tools/note_query.py:179,284,374,478,853-861`）+ `est_tokens` 成本透传与「先按 est_tokens 挑再 expand」预算提示（`:955-1002,1176-1188`）+ `max_chars` 夹取（`:828`） | **已有，且多了 token 预算控制** |
| 异步链路是 wiki 最大价值（Producer/Consumer 代码串不起来） | **已覆盖**：`cross_service_matcher.py:5,216-234` 做 Kafka/RabbitMQ/RocketMQ 跨仓 producer↔consumer 匹配；`mq_patterns.py:1,51-73` 检测 MQ 生产/消费点 | **已做，且这是我们的稀缺资产** |
| 最终交付物是可安装的 skill | 已落地：`skill_creator.py` 四 mode `prepare/submit/install/retire`（`:821-826,643,729`） | **已定档并实现** |
| 知识跟着 git 走（submodule 分布式） | 我们是 `repowiki/` 仓内 + 集中式工作区布局，绕开了文章自认的短板「各域无法交叉检索、难以全局统计」 | **我们的选择更优** |
| 过时 wiki 比没有 wiki 更危险 | 陈旧信号只做到一半：`possibly_stale` 仅在 `by_file` 时间线计算（`note_query.py:702`），BM25 结果未带；`confidence_level` 在 `codewiki/` 源码 **0 命中**，Phase5 置信分层尚未落地 | **真缺口** |
| Harness 四要素（约束/反馈/验证/治理） | Doctrine 全覆盖：准入规则、`adopted_count` 采纳反馈、`confirm_note` 闸门、`lint_wiki` | 同构，可互为背书 |

## 真正值得借鉴的只有 4 条

1. **补一份「不沉淀什么」负面清单**。文章明确列出不写：纯实现细节、逐行代码说明、SQL 细节、一次性排查、无复用价值的临时讨论、证据不足的猜测。我们的 `repowiki/schema.yaml` 只定义了 `note_types`（`:140`）和 `page_types`（`:254-323`），grep「不写/禁止/排除」**0 命中**——只有正面路由表，没有负面清单。这是最低成本的一条，写进 `schema.yaml` 即可被 lint 与提示词消费。

2. **最小作用域原则**（文章原话：能写 context 不写 app，能写 app 不写 workspace）。映射到我们是「能写 module 不写 scenario，能写 scenario 不写全局 doctrine」。目前 `ingest_note` 没有这个约束提示。

3. **候选必须有去向，排除要写原因**。文章用于初始化（保留/并入/排除三选一，排除必填原因）。我们 `consolidate_notes` 与蒸馏都有「候选消失」问题——被吸收的笔记为什么退役、为什么没入选，缺少可审计记录。中等成本，价值在于 `lint_wiki` 能据此查覆盖完整性。

4. **把「Harness Engineering」当作对外表达框架**。文章用「驾驭 Agent 而不是放任它」包装知识治理，传播效果好。呼应我们今天的竞品横评结论（draft）：deepwiki-open 用最弱工程拿最高 star，验证网页 Demo 的传播效应——**定位语言本身就是杠杆，且几乎零成本**。

## 一条反向警示

文章放弃全量 Code Wiki 的三条理由里，最实的一条是「AI 理解代码能力已强，翻译一遍性价比低」。**这条不能照单全收**：它成立的前提是「只有 LLM 直读这条路」。而我们的横评结论是四家竞品全走 LLM 直读、无一家做 AST 静态分析，AST 调用图是我们唯一的稀缺资产；文章里「AI 从代码里根本串不起来的异步链路」，恰好是 `cross_service_matcher` 已经在做的事。**不要在定位讨论里把竞品放弃的东西也一起放弃。**

要不要把上面「4 条借鉴 + 1 条反向警示」整理成一条 comparison 笔记（`wiki/comparisons/knowledge-wiki 有赞 vs CodeWiki`）落盘？按规矩需要你确认后才写入。

<!-- codewiki:referenced-docs: ["notes/2026-09-06-deepwiki-类四竞品源码横评结论llm-直读是主流ast-调用图是-codewiki-唯一稀缺资产.md", "notes/2026-09-06-调研报告的借鉴建议必须先过代码核对b2b1-痛点表述与实际不符的三处教训.md", "notes/2026-08-21-下一期方向资产置信分层与负反馈闭环roadmap-phase-5.md"] -->
user: 我觉得只有第三条有价值，这个可以怎么做？
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"repo_path\":\"d:/repos/CodeWiki-CN\",\"by_file\":\"codewiki/mcp/to…

[tool: search_file · consolidate_notes.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 240, "limit": 120}]

[tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/registry.py", "offset": 1660, "limit": 70}]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 395, "limit": 160}]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki]
assistant: 先纠正一处映射偏差：文章说的是**生成侧**的「候选无声消失」（初始化时概念/流程被丢掉没记录）；我们是**聚合侧**的「候选无声滞留」——同一个可审计性缺口，方向相反。

## 现状（已过代码核对）

- 候选来源：`_pending_confirmed_notes` 只按「status ∈ stable/confirmed **且无** `consolidated_into`」筛（`codewiki/mcp/tools/note_consolidation.py:260-292`）
- submit 报告只收 `scenarios: [{file, action, source_notes, summary?, heat?}]`（`codewiki/mcp/registry.py:1677-1678,1709-1718`）
- 溯源只写在**入选者**身上：`consolidated_into` 双向链接（`note_consolidation.py:476,483-485`）
- **未入选者零标记**——既没有「为什么没入选」，也没有「这条已经判过」

后果是可观察的：每次 prepare 都要重新权衡同一批笔记；无法区分「还没轮到」和「判定不值得聚合」，后者会永久卡在 pending 里顶着计数器——`notes_since_last_consolidation` 现在 41 / 阈值 10，已经在持续告警。

## 最小做法：候选 disposition 三选一

复用已有收敛点，不新建写回函数：`_update_frontmatter_meta`（`note_consolidation.py:134`，locked RMW，与 `:499` 同一调用形态）。

| verdict | 含义 | reason |
|---|---|---|
| `absorbed` | 已入场景块 | 不用新增，走现有 `source_notes` ⇄ `consolidated_into` |
| `deferred` | 本轮不聚合，等素材/等同类积累 | 可选 |
| `excluded` | 判定永不入场景块（一次性任务状态、个人偏好、临时上下文） | **必填** |

落盘形态（笔记 frontmatter `metadata`）：

```yaml
disposition:
  verdict: excluded
  reason: "一次性任务状态，非可复用工作方法"
  at: "2026-09-06"
```

## 改动清单（4 处，约 40 行）

1. `registry.py:1709-1718` —— report 增加可选 `dispositions: [{file, verdict, reason?}]`
2. `note_consolidation.py` submit —— 在 `:507` 后、`:509 if errors:` 前加校验与写回；`excluded` 无 reason 直接进 errors（沿用 `:443-452` 对 `action=deleted` 要求正文为 `[DELETED]` 的同一校验风格）
3. `note_consolidation.py:260-292` —— `excluded` 跳过不再进 pending；`deferred` 保留但回带 `disposition` 字段
4. 提示词：`_CONSOLIDATE_SYSTEM`（`:43-92`）与 `prompts.py:1246-1250` 各加一句「每条候选必须给出去向」

## 明确不做

- **`lint_wiki` 加「长期 deferred 告警」**：文章那句「覆盖完整性审查」的落点在这儿，但阈值现在定是拍脑袋，等 disposition 积累几轮再定。
- **不改 `distill_conversation`**：蒸馏的候选是 raw 对话，submit 后即删，不存在滞留问题，加了是纯负担。

<!-- codewiki:referenced-docs: ["notes/2026-09-06-调研报告的借鉴建议必须先过代码核对b2b1-痛点表述与实际不符的三处教训.md"] -->

[tool: ask_followup_question · {"questions": [{"question": "verdict 用几值？", "options": [{"label": "三值（absorbed/deferred/excluded）", "description": "能表达「等素材积累」，但…
user: <title>候选去向外挂：两个决策</title>

<question>verdict 用几值？</question>
<answers>
三值（absorbed/deferred/excluded）(能表达「等素材积累」，但多一个状态要维护)
</answers>
</question_item>

<question>这一轮做到哪？</question>
<answers>
四处全做(含 excluded 从 pending 剔除，能立刻缓解计数器告警)
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 1, "limit": 135}]

[tool: search_file · *consolidat*]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 356, "limit": 45}]

[tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/tests/test_consolidation_p2.py"}]
assistant: 开始实现。先改 `note_consolidation.py`。

[tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "      cleans up [DELETED] soft-delete marker…
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "_VALID_ACTIONS = (\"created\", \"updated\", …
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "def _pending_confirmed_notes(output_dir: Pat…
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "        processed.append(\n            {\n  …
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "import json\nimport logging\nfrom pathlib im…
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 595, "limit": 70}]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "offset": 664, "limit": 40}]
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "                \"status\": \"error\",\n    …
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "            \"status\": \"completed\",\n    …
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "    \"(5) Call consolidate_notes(mode='submi…
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "                    \"(4) reject_note fully-…
assistant: Now `registry.py` 的 schema 与描述。

[tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/registry.py", "old_str": "            \"mode='submit' with report.scenarios=[{file, ac…
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/registry.py", "old_str": "                \"report\": {\n                    \"type\":…
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py", "offset": 1238, "limit": 22}]
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py", "old_str": "## 步骤 3：退役被吸收的笔记\n对被场景块**完全吸收**的源笔记调用 `reject_note(note_file=…
assistant: [tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "old_str": "    entries = report.get(\"scenarios\")\n   …
assistant: Now 补测试。

[tool: replace_in_file · {"filePath": "d:/repos/CodeWiki-CN/tests/test_consolidation_p2.py", "old_str": "def test_submit_capacity_exceeded_blocks_reset(tmp_pat…
assistant: [tool: read_lints · {"paths": ["d:/repos/CodeWiki-CN/codewiki/mcp/tools/note_consolidation.py", "d:/repos/CodeWiki-CN/codewiki/mcp/registry.py", "d:/repos/Code…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -m pytest tests/test_consolidation_p2.py -q --no-header 2>&1 | Select-Object -Last 4…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -m pytest tests -q --no-header 2>&1 | Select-Object -Last 30]
