---
type: Conversation
title: "conversation 20260927T025509Z"
status: distilled
stale_after: 2026-12-26
generated: { by: codewiki/5.13.1, at: 2026-09-27T02:55:09Z }
captured_at: "2026-09-27T02:55:09Z"
content_hash: "sha256:fe254f5d2efcffba0d7f5e25a6f789d89371dc4adf57a17b2083145bd3b9c2e5"
friction_score: 10
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=11"
keep_raw: false
link_to: ""
source_session: "d66c8f4336854d4e993cc7be40a0ef77"
task_id: "他山之石"
turn_count: 92
---

# Conversation Transcript

user: <working_memory_content>
The following is the existing working memory for this project. Use it as context.

# 长期记忆 (MEMORY.md)



## 环境偏好 / 约定



### npm 镜像源

- 当前环境（推测国内网络）使用 npm 官方源 `registry.npmjs.org` 下载**大体积原生二进制**（如 `@next/swc-darwin-x64`、better-sqlite3 预编译包）时速度极慢（<1KB/s，曾卡死 25+ 分钟）。

- 改用 `https://registry.npmmirror.com` 镜像源后速度约快 6 倍，全局安装 `npm install -g <pkg> --registry=https://registry.npmmirror.com` 是稳妥做法。

- 注意：npm 11 已不再识别 `--disturl` / `--prebuild-install-binary-host-mirror` 这类 CLI flag（会报 unknown config 警告），原生模块的二进制镜像需改用 `.npmrc` 配置。



## 已安装工具

- `omniroute`（AI 网关，v3.8.48，全局 npm 安装）：Dashboard `http://localhost:20128`，API `http://localhost:20128/v1`。编码工具 Base URL 指向 `/v1`、Model 用 `auto` 即可走免费后端。要求 Node ≥ 22.22.2（本机 v25.8.1 满足）。
</working_memory_content>

https://github.com/rohitg00/agentmemory  调研项目
assistant: [tool: ask_followup_question · {"questions": "[{\"header\": \"任务关联\", \"multiSelect\": false, \"options\": [{\"description\": \"task_id=产品维护\", \"label\": \"产品…
user: <question>本次会话要关联哪个任务？（列表里没有想要的任务时，可直接在弹框的输入框里输入新任务名后回车）</question>
<answers>
他山之石
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"set_session_task\"], [\"codewiki\", \"get_task_context\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\": \"d66c8f4336854d4e993cc7be40a0ef77\", \…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\": \"他山之石\"}"}]
assistant: 任务已关联「他山之石」。检测到 1 条本任务待蒸馏积压，先发异步蒸馏 worker（不阻塞），同时开始调研 agentmemory。

[tool: task · {"subagent_name": "distill-worker", "description": "补蒸馏他山之石积压", "prompt": "执行 Mode C（纯 MCP JSON）补蒸馏流程，清空任务「他山之石」的全部待蒸馏积压（不设条数上限）：\n\n1. 调用 codewi…

[tool: execute_command · if (Test-Path "D:\repos\agentmemory") { git -C D:\repos\agentmemory fetch --all 2>&1 | Out-Null; git -C D:\repos\agentmemory log -1 --…
assistant: [tool: execute_command · git -C D:\repos\agentmemory log -1 --format="%H %ci"; git -C D:\repos\agentmemory log --oneline -10; Get-ChildItem D:\repos\agentmemor…
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\README.md", "limit": 150}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\DESIGN.md", "limit": 200}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\package.json"}]
assistant: DESIGN.md 是网站视觉设计文档，与架构无关。继续看源码结构。

[tool: execute_command · Get-ChildItem D:\repos\agentmemory\src -Recurse -File | Resolve-Path -Relative -RelativeBasePath D:\repos\agentmemory | Select-Object …

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\AGENTS.md", "limit": 120}]
assistant: [tool: execute_command · Get-ChildItem D:\repos\agentmemory\src -Recurse -File | ForEach-Object { $_.FullName.Replace('D:\repos\agentmemory\','') } | Select-Ob…
assistant: [tool: execute_command · Get-ChildItem D:\repos\agentmemory\src -Recurse -File | ForEach-Object { $_.FullName.Replace('D:\repos\agentmemory\','') } | Select-Ob…
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\observe.ts", "limit": 120}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\crystallize.ts", "limit": 150}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\remember.ts", "limit": 120}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\compress.ts", "limit": 130}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\consolidation-pipeline.ts", "limit": 150}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\auto-forget.ts", "limit": 120}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\auto-forget.ts", "offset": 120, "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\eval\\self-correct.ts", "limit": 120}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\hooks\\pre-compact.ts", "limit": 80}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\context.ts", "limit": 150}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\state\\hybrid-search.ts", "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\smart-search.ts", "limit": 120}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\reflect.ts", "limit": 120}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\lessons.ts", "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\skill-extract.ts", "limit": 120}]
assistant: -

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\working-memory.ts", "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\retention.ts", "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\governance.ts", "limit": 100}]
assistant: -

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\eval\\quality.ts", "limit": 80}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\README.md", "offset": 150, "limit": 230}]
assistant: [tool: search_content · D:\repos\agentmemory\README.md]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\hooks\\session-start.ts", "limit": 60}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\compress-synthetic.ts", "limit": 90}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\slots.ts", "limit": 70}]
assistant: [tool: execute_command · Get-ChildItem D:\repos\agentmemory\src\state, D:\repos\agentmemory\src\server -File | ForEach-Object { $_.FullName.Replace('D:\repos\a…
assistant: [tool: search_content · D:\repos\agentmemory\src\state\schema.ts]

[tool: search_file · *.ts]
assistant: -

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\state\\schema.ts", "limit": 100}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\evict.ts", "limit": 80}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\crystallize.ts", "limit": 80}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\consolidation-pipeline.ts", "limit": 100}]

[tool: execute_command · Get-Content D:\repos\agentmemory\package.json | Select-Object -First 60]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\package.json", "limit": 80}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\observe.ts", "offset": 40, "limit": 80}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\routines.ts", "limit": 60}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\sentinels.ts", "limit": 60}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\functions\\mesh.ts", "limit": 60}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\state\\search-index.ts", "limit": 60}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\eval\\runner\\longmemeval.ts", "limit": 60}]

[tool: execute_command · (Get-ChildItem D:\repos\agentmemory\src -Recurse -Filter *.ts | Get-ChildItem).Count; (Get-ChildItem D:\repos\agentmemory\test -Filter…
assistant: -

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\src\\state\\kv.ts", "limit": 60}]

[tool: search_content · iii-engine|three primitives]
assistant: [tool: search_content · D:\repos\agentmemory\README.md]
assistant: [tool: read_file · {"filePath": "D:\\repos\\agentmemory\\README.md", "offset": 972, "limit": 90}]

[tool: read_file · {"filePath": "D:\\repos\\agentmemory\\README.md", "offset": 400, "limit": 60}]
assistant: 源码已读完，信息足够。按「他山之石」任务惯例（调研存档→`write_doc_file(page_type="query")`），先获取写文档工具的参数。

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"write_doc_file\"]]"}]
assistant: [tool: write_to_file · {"filePath": "D:\\repos\\CodeWiki-Plus\\repowiki\\wiki\\queries\\agentmemory-调研.md", "content": "# agentmemory 调研（rohitg00/agentmemory）\…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "write_doc_file", "arguments": "{\"content_file\": \"D:\\\\repos\\\\CodeWiki-Plus\\\\repowiki\\\\…
assistant: 文件路由冲突（我先手写了同路径文件）。改为：把内容挪到临时文件，删除目标文件，再让 `write_doc_file` 正式建档。

[tool: execute_command · Move-Item "D:\repos\CodeWiki-Plus\repowiki\wiki\queries\agentmemory-调研.md" "D:\repos\CodeWiki-Plus\.codebuddy\tmp-agentmemory-调研.md" -…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "write_doc_file", "arguments": "{\"content_file\": \"D:\\\\repos\\\\CodeWiki-Plus\\\\.codebuddy\\…
assistant: [tool: delete_file · {"target_file": "D:\\repos\\CodeWiki-Plus\\.codebuddy\\tmp-agentmemory-调研.md", "explanation": "删除已消费的临时内容文件"}]

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\": \"他山之石\", \"content\": \"完成 agentmemory（rohitg00/a…
assistant: [tool: execute_command · Remove-Item "D:\repos\CodeWiki-Plus\.codebuddy\tmp-agentmemory-调研.md" -Force]
assistant: 调研完成，存档已落盘：`repowiki/wiki/queries/agentmemory-调研.md`（152 行，带代码行号依据）。

## agentmemory 调研摘要

**项目定位**：给 AI 编码 agent 做持久记忆的 TypeScript 项目（v0.9.29，~42K LOC，264 函数，1,674 测试）。核心理念是「agentmemory 本身就是一个运行中的 iii 实例」——全部运行时由 iii-engine 三原语（worker/function/trigger）组合，不装 Postgres/Redis/Express。

**架构要点**（均经源码核对）：
- **采集**：Claude Code 等 harness 的 9 类 hook 全量自动采集 → SHA-256 去重 → 隐私过滤 → 默认零 LLM 合成压缩 → BM25/向量索引
- **四层巩固**：Working（raw 观察）→ Episodic（会话摘要）→ Semantic（事实，`<fact confidence>` 标签提取）→ Procedural（工作流），带 Ebbinghaus 式衰减（每周期 strength×0.9）与三策略自动驱逐
- **检索**：BM25（自实现，含 CJK 分词降级）+ 向量 + 知识图，RRF(k=60) 融合，会话多样性约束；被 supersede 的版本从所有检索路径剔除但保留版本链
- **MCP 面**：54 工具；MCP 包是薄 shim，连不上 server 时降级为 7 工具本地集

**三项借鉴候选全部不立项**：

| 候选 | 去向 | 理由 |
|---|---|---|
| 合成压缩（零 LLM） | absorbed | 与确认闸门冲突，仅作未来降本备选认知 |
| 记忆衰减/自动驱逐 | deferred | 与「候选必有去向」Doctrine 冲突，等 lint_wiki low_adoption 数据再评估 |
| slots 固定槽位 | excluded | MEMORY.md + AGENTS.md + 任务记忆三件套已覆盖同等语义 |

**总体判断**：agentmemory 是「重运行时、全自动」路线的极致样本；CodeWiki 是「轻文件、显式确认」路线。哲学相反，直接移植任何组件都会破坏 CodeWiki 的架构前提。本次调研的核心价值是**确认边界**：自动采集/自动巩固/自动驱逐这条全自动路线，CodeWiki 明确不走。

另外：任务记忆已直写「他山之石」（含去向结论）；后台蒸馏 worker 正在处理 1 条积压，待确认草稿会在下个停顿点展示。
user: <question>本次会话要关联哪个任务？（列表里没有想要的任务时，可直接在弹框的输入框里输入新任务名后回车）</question>
<answers>
他山之石
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-worker-0924</from>
<summary>Message from distill-worker-0924</summary>
<content>
任务「他山之石」补蒸馏完成，积压已清空。

**处理情况**：
- 处理 raw：1 条（conv-working_memory_content-The-following-is-the-existing-working-2，164K 字符 / 167 轮，friction_score 45）
- 提交草稿笔记：5 条（memories 按通道互斥跳过，memories_written=0）
- 去重裁决：1 条 update（替换 2026-09-20 的 deferred 方案笔记）、0 条 skip/merge；首轮 2 条直接 ingested，次轮 3 条（2 ingested + 1 update）
- raw 已归档至 conversations/

**待确认草稿清单**（建议在停顿点向用户展示，经 confirm_note 后正式落盘）：
1. `notes/2026-09-24-adr-0015-落地agentsmd-托管块瘦身与注入通道收敛改产品模板而非本仓文件.md` — ADR-0015 落地决策：改产品模板而非本仓文件，D1/D2/D3 三处瘦身，本仓刷新用产品渲染器
2. `notes/2026-09-20-主动沉淀-100-生效的机制分析与-userpromptsubmit-薄触发方案deferred.md`（update 原地替换）— UserPromptSubmit active-settle 薄触发已实施并真机验证，混合措辞一行两职，deferred 状态解除
3. `notes/2026-09-24-subagentstart-hook-评估定案不做沉淀责任留主-agentsubagent-只报告沉淀原料.md` — SubagentStart hook 不做，subagent 只报告沉淀原料，沉淀责任留主 Agent
4. `notes/2026-09-24-workspace-conventions-模板接入清单收敛为工具指针adr-0015-同款双通道重复病灶.md` — Workspace Conventions 接入清单 8→2 行收敛为工具指针
5. `notes/2026-09-24-hook-注册命令用-python--m-包内入口脚本内部改动无需改-settingsjson源码环境自动生效.md` — hook 注册用 python -m 包内入口，脚本改动无需改 settings.json

**skill_hint**（只汇报，不执行）：笔记 5（hook 注册命令 python -m 包内入口）命令密度 4（阈值 3），读起来像可执行行为指令，可能值得编译成技能。如需评估：`skill_creator(mode="prepare", sources=["notes"])`——需用户确认后执行。
</content>
</teammate-message>
</additional_input>
assistant: 任务「他山之石」本会话已绑定过，无需重复。蒸馏 worker 已回报完成——按 Doctrine「子代理自报须独立复核」，先拉取任务上下文核实草稿实际落盘状态。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\": \"他山之石\"}"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\.codebuddy\\memory\\2026-09-24.md"}]
assistant: 任务上下文已核实：`pending_raw_count=0`，5 条草稿笔记全部实际落盘，worker 自报与复核一致。另外检测到任务记忆压缩预警（红色，50 条超阈值），工具已给出压缩指令——按其契约「压缩直写落盘，无需用户确认」执行。先重新确认会话绑定并获取压缩工具参数。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\": \"d66c8f4336854d4e993cc7be40a0ef77\", \…

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"compact_task_memories\"]]"}]
assistant: 会话绑定已确认。现在按 prepare 返回的指令撰写压缩摘要（覆盖旧摘要 + 新增 09-11~09-19 条目，保留作废警告标记），提交压缩。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "compact_task_memories", "arguments": "{\"task_id\": \"他山之石\", \"mode\": \"submit\", \"repo_path\…
assistant: 压缩完成（30 条→摘要，保留最近 20 条，原文已归档）。补写今日工作记忆，然后向你汇报。
assistant: ## 蒸馏结果复核与待确认草稿

任务上下文已核实：`pending_raw_count=0`，worker 自报与实际落盘一致。**5 条草稿笔记待你确认**：

| # | 笔记 | 主题 |
|---|---|---|
| 1 | `2026-09-24-adr-0015-落地agentsmd-托管块瘦身与注入通道收敛改产品模板而非本仓文件.md` | ADR-0015 落地：改产品模板而非本仓文件，D1/D2/D3 三处瘦身 |
| 2 | `2026-09-20-主动沉淀-100-生效的机制分析与-userpromptsubmit-薄触发方案deferred.md`（update 原地替换） | active-settle 薄触发已实施并真机验证，deferred 状态解除 |
| 3 | `2026-09-24-subagentstart-hook-评估定案不做沉淀责任留主-agentsubagent-只报告沉淀原料.md` | SubagentStart hook 不做，subagent 只报告沉淀原料 |
| 4 | `2026-09-24-workspace-conventions-模板接入清单收敛为工具指针adr-0015-同款双通道重复病灶.md` | 接入清单 8→2 行收敛为工具指针 |
| 5 | `2026-09-24-hook-注册命令用-python--m-包内入口脚本内部改动无需改-settingsjson源码环境自动生效.md` | hook 注册用 `python -m` 包内入口 |

**skill_hint**（只汇报不执行）：笔记 5 命令密度 4（阈值 3），读起来像可执行行为指令，可能值得编译成技能——如需评估请确认。

另外顺手处理了两件事：
- **任务记忆压缩**：50 条触发红色预警，已按工具指令压缩 30 条为摘要（保留最近 20 条，原文归档 `memories-archive/iamwangbao-163-com.md`，可回溯）。
- **会话绑定**：本会话已重新确认绑定「他山之石」。

请告知 5 条草稿的裁决（全部确认 / 逐条指定 confirm 或 reject），以及是否评估 skill_hint。
user: 确认全部草稿  ，评估skill hint
assistant: 收到：确认全部 5 条草稿 + 评估 skill hint。先获取两个工具的参数。

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"confirm_note\"], [\"codewiki\", \"skill_creator\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"note_file\": \"2026-09-24-adr-0015-落地agentsmd-托管块瘦身与注入通道收敛改产品模板而…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"note_file\": \"2026-09-20-主动沉淀-100-生效的机制分析与-userpromptsubmit-薄触发…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"note_file\": \"2026-09-24-subagentstart-hook-评估定案不做沉淀责任留主-agents…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"note_file\": \"2026-09-24-workspace-conventions-模板接入清单收敛为工具指针adr…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"note_file\": \"2026-09-24-hook-注册命令用-python--m-包内入口脚本内部改动无需改-set…
assistant: 5 条草稿全部确认落盘（stable）。现在评估 skill hint——用 `skill_creator(mode="prepare")` 查候选材料、冲突预检与容量水位。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "skill_creator", "arguments": "{\"mode\": \"prepare\", \"repo_path\": \"d:/repos/CodeWiki-Plus\",…
assistant: 5 条草稿已全部确认（stable）。现在评估 skill hint：候选清单里同主题的 `2026-09-18-全局-codewikiexe-无法-import-本地包` 标记 `worth_compiling: true`，与 hint 指向的笔记同属「源码环境 hook 注册」主题。先读齐材料再裁决。

[tool: search_file · *hook-注册命令*]

[tool: read_file · {"filePath": "D:\\repos\\CodeWiki-Plus\\repowiki\\notes\\2026-09-18-全局-codewikiexe-无法-import-本地包install-hooks-需用-python--m-codew.md"}]

[tool: read_file · {"filePath": "D:\\repos\\CodeWiki-Plus\\repowiki\\skills\\windows-dev-env\\SKILL.md"}]
assistant: [tool: read_file · {"filePath": "D:\\repos\\CodeWiki-Plus\\repowiki\\notes\\2026-09-24-hook-注册命令用-python--m-包内入口脚本内部改动无需改-settingsjson源码环境自动生效.md"}]
assistant: 材料已读齐。评估结论如下，先提交裁决（空报告为合法轮次）并沉淀，同时关闭已完工的蒸馏 worker。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "skill_creator", "arguments": "{\"mode\": \"submit\", \"repo_path\": \"d:/repos/CodeWiki-Plus\", …

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"content\": \"skill hint 评估裁决（2026-09-25）：蒸馏 worker 提示笔记「hook …

[tool: send_message · {"type": "shutdown_request", "recipient": "distill-worker-0924", "content": "你的补蒸馏成果已全部复核确认：5 条草稿笔记已由用户确认转 stable，任务记忆压缩也已完成。你的工作全部结束，请关闭…
user: 继续
assistant: [tool: team_delete]
assistant: [tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\.codebuddy\\memory\\2026-09-25.md", "content": "# 2026-09-25\n\n## 蒸馏草稿确认 + skill hint 评估（他山之石）\…
assistant: 全部收尾完成：

**草稿确认**：5 条蒸馏草稿全部 confirm 转 stable——
1. ADR-0015 落地（改产品模板而非本仓文件）
2. active-settle 薄触发已实施，deferred 状态解除（update 原地替换）
3. SubagentStart hook 不做，沉淀责任留主 Agent
4. workspace-conventions 接入清单收敛为工具指针
5. hook 注册用 `python -m` 包内入口

**skill hint 评估**：裁决**不编译**（`no_action` 已提交），理由：
- hint 指向的笔记是 **architecture 类型**，不在 skill 素材边界内（素材只收 scenarios + stable 的 pitfall/lesson/decision）
- 内容是结构认知（回答「hook 行为更新要不要改 settings.json」），非可触发行为指令，编译无触发场景

顺带发现：prepare 标记 `worth_compiling: true` 的同主题 pitfall「全局 codewiki.exe 无法 import 本地包」→ **deferred**：信息量单薄（一条命令选择），单独成技能碎片化，等同类素材积累后并入。

**其他**：蒸馏 worker 已关闭、团队已删除；裁决已写入任务记忆与今日工作记忆。注意任务记忆 hot 层又到 21 条（软限 5），下次会话可先压缩。
user: 记忆衰减/自动驱逐	-  这个是怎么做的，另外agentmemory的记忆是如何保存的，是markdown还是数据库
assistant: 两个问题都基于已读源码直接回答（依据：D:\repos\agentmemory v0.9.24 源码核对）。

## 一、记忆衰减/自动驱逐怎么做

agentmemory 用**四套互补机制**，分布在不同函数：

**1. 强度衰减（applyDecay，`src/functions/consolidation-pipeline.ts:21-43`）**

巩固管线运行时对 semantic/procedural 记忆打分衰减：距上次访问超过 `decayDays` 后，每过一个周期 `strength × 0.9`，下限 0.1。访问会刷新 `lastAccessedAt`，从而重置衰减计时。

**2. 保留分分层（retention.ts:20-95）**

更精细的数学模型：`retention = min(1, salience × e^(−λ·Δt) + reinforcementBoost)`——时间指数衰减（λ=0.01）+ 访问强化加成（每次访问按 `1/距今天数` 累加 × σ）。按阈值分三档：hot ≥0.7 / warm ≥0.4 / cold ≥0.15，冷记忆优先被驱逐。

**3. 自动遗忘（auto-forget.ts:24-206）**

三条独立策略，支持 `dryRun`：
- **TTL 过期**：记忆带 `forgetAfter` 字段，到期即删（含审计日志 + 索引清除）
- **矛盾检测**：按 concept 建索引，同 concept 的记忆两两算 Jaccard，相似度 >0.9 判定为矛盾 → **旧的标记 `isLatest=false`**（软退役，不物理删除，版本链保留）
- **低价值清理**：observation 年龄 >180 天且 importance ≤2 → 物理删除

**4. 容量驱逐（evict.ts:16-30）**

兜底上限：stale session 30 天、低重要度（<3）observation 90 天、每项目 observation 上限 10,000 条，超限先尝试恢复（补跑会话巩固）再驱逐。

另外工作记忆有自己的评分公式（`working-memory.ts:25-32`）：`importance×0.5 + recency×0.3 + log2(accessCount)×0.2`，用于 token 预算内选块注入。

## 二、记忆怎么存：数据库，不是 Markdown

**SQLite 数据库**，经 iii-engine 的 KV 抽象访问：

- **存储链路**：所有读写走 `StateKV`（`src/state/kv.ts:3-47`）→ `sdk.trigger({function_id: 'state::get/set/list'})` → iii-engine 的 StateModule → **文件型 SQLite**（`data/state_store.db`，AGENTS.md:8 明确写明）
- **数据组织**：50 个 KV scope（`src/state/schema.ts:4-76`），按类型分域——`mem:memories`（显式记忆）、`mem:obs:<sessionId>`（按会话分域的观察）、`mem:semantic`、`mem:procedural`、`mem:lessons`、`mem:crystals`、`mem:graph:nodes/edges` 等，scope 内是 key→JSON value
- **数据目录**：平台默认位置（Windows 为 `%APPDATA%\agentmemory`），可用 `--data-dir` 覆盖
- **索引**：BM25 倒排索引和向量索引是**进程内存结构**，增量维护 + 定期持久化（`index-persistence.ts`）；lessons 有独立的内存 BM25 索引 + 记录缓存（`lessons.ts:17-20`），召回零 KV 往返

与 CodeWiki 的对照：CodeWiki 是「Markdown 即真相、git 版本化、人可读可编辑」；agentmemory 是「SQLite 即真相、程序可检索、人不可直接读」。这也是我此前调研把它判为「架构前提相反、组件不可移植」的核心原因之一——它的衰减/驱逐机制全部建立在 KV 数据库的原子更新和内存索引之上，搬到 Markdown 文件体系上没有落点。
user: PreCompact	压缩前重注入记忆  ，值不值得借鉴？
assistant: **结论：不值得——这项已在 2026-09-21 的 grill 拷问中裁决过，定案「PreCompact 不做」**（任务记忆 #y1a8，ADR-0015 后续轮）。

## agentmemory 的做法

`src/hooks/pre-compact.ts`：Claude Code 触发 PreCompact 事件时，hook 调 `/agentmemory/context`（预算 1500 tokens），把召回的记忆写到 stdout，由 Claude Code 注入——压缩后记忆不丢。

## 为什么 CodeWiki 不借

**1. UserPromptSubmit 薄触发是超集（当轮裁决理由 Q1）**

压缩丢上下文的恢复窗口只到「下一次用户提问」——而 CodeWiki 已实现的 active-settle 薄触发恰好在每个用户 prompt 时注入提醒，Agent 随即可 `get_task_context` 拉回任务上下文。PreCompact 能覆盖的场景，UserPromptSubmit 全覆盖，且多覆盖了「非压缩的普通上下文漂移」。

**2. 两者的记忆模型不同**

agentmemory 的注入是**被动**的——Agent 不知道记忆存在，只能靠 hook 塞；不重注入就真丢了。CodeWiki 是**Agent 驱动**的——MCP 工具随时可拉，恢复路径本来就在，PreCompact 只是提前一个事件时机的优化，收益边际。

**3. 架构前提不符（Doctrine）**

- CodeBuddy 是否支持 PreCompact 事件**未真机验证**（与 SubagentStart 同样的坑）；
- 竞品盘点已收敛的共识：**路由层极简化，多事件采集是反面教材**（草稿笔记 2026-09-20）——agentmemory 挂 12 个 hook 是重运行时路线的产物，CodeWiki 的 hook 面要收敛不要扩张。

**4. token 成本方向相反**

agentmemory PreCompact 每次注入 1500 tokens 实体记忆；CodeWiki 薄触发只注入一行提醒，按需拉取。前者是「预防性全量」，后者是「按需最小」——后者符合「成本可见性优先」的 Doctrine。

## 去向

**excluded**（维持 2026-09-21 定案，本次为再确认，非新决策）：触发时机被 UserPromptSubmit 超集覆盖；被动注入模型与 Agent 驱动模型前提相反；hook 面扩张违背路由层极简化共识。
user: <manually_attached_skills>
Please use the use_skill tool to invoke this skill.

name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
</manually_attached_skills>

@d:\repos\CodeWiki-Plus\repowiki\wiki\queries\agentmemory-调研.md  @command://grill-with-docs  再看下有没有值得借鉴的，哪怕是很小的优化也可以了，比如记忆的存储格式，检索优化等等
assistant: [tool: use_skill · grill-with-docs]
assistant: -

[tool: use_skill · grilling]
assistant: -

[tool: use_skill · domain-modeling]
assistant: -

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\repowiki\\wiki\\queries\\agentmemory-调研.md"}]
assistant: 收到，进入 grill 模式。按规矩：事实我自己查，决策问你要。先把「小优化候选」相关的事实从两边代码里核出来——agentmemory 侧我已读过，现在核对 CodeWiki 侧的检索实现，确认哪些是真缺口、哪些本仓已有等价。

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki]

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki]

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\codewiki\\src\\retrieval.py"}]
assistant: 进入 grill 模式。设计树根节点：「agentmemory 还有哪些**小优化**值得借」。我先把三个候选相关的事实从本仓代码核出来（事实是我的活），再向你提问。

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\tools\capture_conversation.py]

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\tools\task_manager.py]

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\registry.py]
assistant: [tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\tools\task_manager.py]

[tool: search_content · def _collect_related_notes|def _related|related_notes]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\codewiki\\mcp\\tools\\task_manager.py", "offset": 955, "limit": 50}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\codewiki\\mcp\\tools\\task_manager.py", "offset": 1005, "limit": 60}]
assistant: [tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\tools\wiki_search.py]

[tool: search_content · d:\repos\CodeWiki-Plus\codewiki\mcp\cache.py]
assistant: 事实核完了。现在按 grill 规矩提问——每题给推荐答案，等你裁决。

---

## Round 1：小优化候选清单（frontier 全集）

先交代事实基础（我逐条核过本仓代码）：

- **同义词扩展**：本仓已有 `ontology.yaml` 同义词扩展（`retrieval.py:281-345`），agentmemory 的「同义词扩展」**已有等价**，排除。
- **CJK 分词**：本仓已有 jieba 可选依赖 + regex 降级（`retrieval.py:197-238`），**已有等价**，排除。
- **会话多样性约束**（每 session 最多 3 条）：本仓检索无此机制（`wiki_search.py`/`cache.py` 全文无 diversity 约束），**真缺口**。
- **RRF 融合**：本仓是单流 BM25（+authority/heat 乘法因子），无多路召回融合，**真缺口**。
- **MCP 工具面裁剪**（`AGENTMEMORY_TOOLS=core` 裁到 8 个）：本仓 registry 60+ 工具全量暴露，无裁剪开关，**真缺口**。
- **related_notes 按任务过滤**：本仓 `get_task_context` 的 related_notes 是**按 frontmatter task_id 精确匹配**（`task_manager.py:979-993`），无语义召回，**真缺口**——但注意这是「任务上下文注入」场景，不是检索场景，语义召回会引入 LLM 依赖，违背「工具不持模型」。
- **SHA-256 去重窗口**：本仓 capture 已有 content_hash 去重（`capture_conversation.py:14,394-428`），**已有等价**，排除。
- **BM25 参数**：本仓 k1=1.5/b=0.75（`retrieval 33-34`），agentmemory k1=1.2/b=0.75——参数微调无实测数据支撑，**不值得**，排除。
- **BM25 参数微调**：无实测数据支撑，按 Doctrine「先实测计数再下结论」排除。
- **合成压缩**：已裁决 absorbed（认知），维持。
- **衰减/驱逐**：已裁决 deferred，维持。
- **slots**：已裁决 excluded，维持。
- **PreCompact**：已裁决 excluded（UserPromptSubmit 超集），维持。
- **crystallize**：与 CodeWiki 的 ingest_note 同构，维持不立项。

**真正值得讨论的候选只有 4 个**，逐题问：

---

❓ **Q1** - **会话多样性约束（每 session 最多 3 条）**：agentmemory 在 RRF 融合后加「每 session 最多 3 条」约束，防止单一会话霸屏。CodeWiki 的 query_wiki 场景是「搜知识库」，语料是笔记/wiki，不是会话记录——但本仓有 `raw/`（对话存档）和 `notes/`（按日期命名），同一天的多条笔记可能高度相似（比如同一天 3 条蒸馏笔记都关于 hook 注册）。要不要在 query_wiki 排序后加「同前缀日期/同目录」多样性约束？

➡️ **推荐：deferred**。理由：① 本仓语料以笔记/wiki 为主，单源霸屏问题未实测出现（Doctrine：先实测计数再下结论）；② 实现成本低但收益不明，等 lint_wiki 的 low_adoption/重复笔记数据积累后再看。

---

❓ **Q2** - **RRF 多路召回融合**：agentmemory 用 RRF(k=60) 融合 BM25+向量+图三路。CodeWiki 目前单流 BM25。要不要借 RRF？

➡️ **推荐：excluded**。理由：① RRF 的前提是**多路召回**，本仓只有一路 BM25，没有第二路可融合——为 RRF 而 RRF 是伪需求；② 若未来加向量检索（deferred 项），RRF 是那时的融合方案，现在立项为时过早；③ Doctrine「成本可见性优先于新造能力」。

---

❓ Q3 - **MCP 工具面裁剪开关**：agentmemory 的 `AGENTMEMORY_TOOLS=core` 可把 54 工具裁到 8 个核心。CodeWiki registry 60+ 工具全量暴露，每个工具的 schema 都占 IDE 上下文。要不要加一个 `CODEWIKI_TOOLS=core` 环境变量裁剪开关？

➡️ **推荐：立项（P2）**。理由：① 真缺口——本仓工具面确实大，schema 注入成本可见（每个工具 description 都进 system prompt）；② 实现成本低（registry 加个 filter）；③ agentmemory 的「core 8 个」清单可参考但需按本仓场景重定义；④ 与「成本可见性」Doctrine 正向。

---

❓ Q4 - **related_notes 语义召回**：agentmemory 的检索是语义的，CodeWiki task context 的 related_notes 是 frontmatter task_id 精确匹配。要不要升级为语义召回？

➡️ **推荐：excluded**。理由：① 「任务上下文注入」与「知识检索」是两个场景，前者要**确定性**（哪些笔记属于这个任务，由 ingest 时显式标记），后者才需要语义。把检索场景的语义召回搬到注入场景，会把「哪些笔记属于这个任务」变成概率性的，违背「显式优于缓存」；② 语义召回需要 embedding，违背「工具不持模型」。

---

请对 Q1-Q4 裁决（同意推荐 / 修改去向 / 补充约束）。
user: 按推荐
assistant: 全部按推荐锁定。收尾动作：更新调研文档处置表、给 Q3 立项建工单、沉淀记忆。先取工具参数。

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"edit_doc_file\"], [\"codewiki\", \"flag_issue\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "edit_doc_file", "arguments": "{\"command\": \"str_replace\", \"filename\": \"agentmemory-调研.md\"…
assistant: 编辑失败——工具提示 write_doc_file 落盘后会注入交叉链接改变内容，需先重读。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "view_repo_file", "arguments": "{\"filename\": \"agentmemory-调研.md\", \"page_type\": \"query\", \…
assistant: -

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"view_repo_file\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "view_repo_file", "arguments": "{\"file_path\": \"repowiki/wiki/queries/agentmemory-调研.md\", \"ma…
assistant: -

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "edit_doc_file", "arguments": "{\"command\": \"str_replace\", \"filename\": \"agentmemory-调研.md\"…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "view_repo_file", "arguments": "{\"file_path\": \"repowiki/wiki/queries/agentmemory-调研.md\", \"ma…
assistant: 超时但实际已写入（152→166 行）。验证尾部内容确认编辑成功。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "view_repo_file", "arguments": "{\"file_path\": \"repowiki/wiki/queries/agentmemory-调研.md\", \"ma…
assistant: [tool: execute_command · Get-Content "D:\repos\CodeWiki-Plus\repowiki\wiki\queries\agentmemory-调研.md" -Tail 30]
assistant: [tool: read_file · {"filePath": "D:\\repos\\CodeWiki-Plus\\repowiki\\wiki\\queries\\agentmemory-调研.md", "offset": 127, "limit": 40}]
assistant: 文档更新成功（超时是假警报，内容已写入）。继续收尾：Q3 立项建工单 + 沉淀记忆。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"content\": \"agentmemory Round 2 小优化 grill 定案（2026-09-25，用户裁决…
user: 继续
assistant: 继续补上刚才失败的两个收尾动作（任务记忆 + 今日工作记忆）。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"content\": \"agentmemory Round 2 小优化 grill 定案（2026-09-25，用户裁决…
assistant: 任务记忆其实上次已写入成功（去重校验证实 0.99 相似——「No result found」只是结果回传丢失，落盘已发生）。补今日工作记忆。
assistant: Round 2 grill 全部收尾完成：

**定案汇总**（已写入调研文档第六节 + 处置表，任务记忆与工作记忆已沉淀）：

| 候选 | 去向 |
|---|---|
| MCP 工具面裁剪开关 `CODEWIKI_TOOLS=core` | **立项（P2）**，归产品维护 |
| 会话多样性约束 | deferred（等 lint_wiki 重复笔记数据） |
| RRF 多路融合 | excluded（单流 BM25 无第二路可融） |
| related_notes 语义召回 | excluded（注入场景要确定性） |
| 同义词扩展 / CJK 分词 / SHA-256 去重 | 本仓已有等价，无需行动 |

**唯一立项项**：工具面裁剪开关——60+ 工具 schema 全量注入上下文是真缺口，registry 加 filter 成本低。这个落在「产品维护」任务下，下次做产品维护工作时可顺手实现。

另记一个流程坑：`edit_doc_file` 超时但实际写入成功，超时≠失败，须读文件验证后再决定是否重试。
user: 先存档，先不实施
assistant: 收到：只存档、不实施。定案已全部落盘（调研文档 §六 + 处置表、他山之石任务记忆、今日工作记忆）。唯一需要补的动作：立项项归「产品维护」任务，把待办记到那边，避免下次做产品维护时丢失。

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"content\": \"待办（P2，来自 agentmemory 调研 Round 2 grill 定案 2026-09…
assistant: 存档完成，未实施任何代码改动。最终状态：

**已落盘的存档**：
1. 调研文档 `repowiki/wiki/queries/agentmemory-调研.md`——第六节 Round 2 定案 + 处置表 8 行（含行号依据）
2. 「他山之石」任务记忆——四题裁决 + 本仓等价物核对结论
3. 「产品维护」任务记忆——P2 待办（`CODEWIKI_TOOLS=core` 裁剪开关），下次做产品维护时可见
4. 今日工作记忆 `.codebuddy/memory/2026-09-25.md`——含 `edit_doc_file` 超时假警报的坑

**未实施**：工具面裁剪开关只立项不写码，等你在产品维护任务下排期。
