---
type: Conversation
title: "conversation 20260910T225317Z"
status: distilled
stale_after: 2026-12-09
generated: { by: codewiki/5.9.0, at: 2026-09-10T22:53:17Z }
captured_at: "2026-09-10T22:53:17Z"
content_hash: "sha256:90b1cade9013699a81adc7f9fbd1be5116d7b930ded7a956adb0279a00725a27"
friction_score: 10
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=11"
keep_raw: false
link_to: ""
source_session: "c9253615a4a04beb97dbc506d1c2bfe7"
task_id: "Cli能力"
turn_count: 64
---

# Conversation Transcript

user: <manually_attached_skills>
Please use the use_skill tool to invoke this skill.

name: grill-me
description: A relentless interview to sharpen a plan or design.
</manually_attached_skills>

@command://grill-me  现在cli的能力比较弱，没有和mcp对齐，我觉得可以增强cli的能力，这样智能体用起来会比mcp更加节省token
assistant: [tool: use_skill · grilling]

[tool: ask_followup_question · {"questions": [{"question": "本次会话要关联到哪个任务？（列表里没有想要的，可直接在输入框输入新任务名后回车）", "header": "任务关联", "options": ["CodeWiki 架构深化分析", "OpenWi…
user: <question>本次会话要关联到哪个任务？（列表里没有想要的，可直接在输入框输入新任务名后回车）</question>
<answers>
Cli能力
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"create_task\"],[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"]]"}]

[tool: task · {"subagent_name": "code-explorer", "description": "摸清 CLI 与 MCP 能力差", "prompt": "这是一个只读调研任务，不要修改任何文件。\n\n背景：CodeWiki 项目（d:\\repos\\CodeWiki-CN）既有…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "create_task", "arguments": "{\"title\":\"Cli能力\",\"description\":\"增强 CLI 能力，使其对齐 MCP 工具集，让智能体用 …
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"c9253615a4a04beb97dbc506d1c2bfe7\",\"t…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"Cli能力\",\"repo_path\":\"d:/repos/CodeWiki-CN\"}"…
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\cli\\main.py"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\cli]
assistant: 任务已建并绑定：**Cli能力**（`pending_raw_count=0`，无补蒸馏积压）。

先摆我查到的事实（不占用你的回答额度）：

- **CLI 现状**：8 个顶层动词 + 4 个 `config` 子命令 = 12 个（`codewiki/cli/main.py:25-49`、`commands/config.py`）。
- **MCP 现状**：49 个工具，单一事实源在 `codewiki/mcp/registry.py:58`，分发在 `registry.py:2967`，每工具一个 `handle_x(arguments, store)` 于 `codewiki/mcp/tools/*.py`。
- **已有复用先例**：`codewiki/cli/commands/query.py:160` 直接调 `handle_query_wiki`，`migrate_team_layout.py:30` 直接导 tools 模块 → CLI 不需要第二套业务逻辑。
- **已定调**：`docs/Hook多智能体支持设计方案.md:176` 写了「CLI 是 handler 的投影层，不实现第二套检索」——我把它当**已 settle 的前提**，不再问。
- **两个硬缺口（已复核）**：CLI 无 `--json`（全仓仅 `config.py:287` 一处），`query.py:55-84` 的渲染函数**完全没渲染 `est_tokens`**，而 MCP 端有（`registry.py:1056`）→ 走 CLI 的 agent 看不见展开成本。

下面是设计树的第一轮前沿。请逐条答，答完我重算前沿再问下一轮。

---

❓ **Q1** - **「更省 token」到底省在哪（这是验收口径，不定这个后面全是空谈）**

候选三条，收益来源完全不同：
- (a) **消灭 schema 常驻**：MCP 的 49 份 `inputSchema` + 描述每次请求都进上下文，CLI 则不进；
- (b) **输出体积**：定界文本 vs JSON 的引号/括号/转义开销，加上 `--top`/`--expand` 裁剪、`est_tokens` 可见；
- (c) **减少往返**：一条命令干完 MCP 需要两次调用的事（如 `query --expand` 一次拿全）。

另外有个反直觉点请你判断：CLI 相对 MCP 有一项**隐性劣势**——agent 不知道有什么命令， discovery 要么靠 `--help`（一次调用几百 token）要么靠写进 `AGENTS.md`（那就等于把 schema 又常驻了一遍）。所以「更省」只在**会话内调用次数足够多**时才成立。

➡️ 推荐：以 **(a)+(b) 为主**，(c) 顺带；并且**先做一次基线测量**（同一批任务分别走 MCP / CLI，量真实 token），用数据决定优先做哪批命令。没有基线，「更省」永远是一个无法证伪的断言。

❓ **Q2** - **对齐范围：49 个全量，还是分层**

- 全量 49 个对齐；
- 只做高频 ~12 个（query / ingest / capture / distill / task 几个）；
- 分层：高频手写精调 + 其余自动投影兜底。

➡️ 推荐：**分层**。手写 49 个命令在维护上是灾难（以后每加一个 MCP 工具就要改两处），但只要高频那十来个的手感好，就能拿到 80% 收益。

❓ **Q3** - **投影机制：从 registry 自动生成，还是手写**

`registry.py` 已经持有完整 `inputSchema`（含约 30 处 `enum`），理论上可以机械生成子命令与参数（`enum` → `click.Choice`）。风险是嵌套 object / 复杂类型映射不干净，以及 CLI 与 MCP schema 演进从此耦合（改 schema 会同时打断两边）。

➡️ 推荐：**自动生成，且投影器必须容忍未知 schema 形状**——遇到嵌套 object 就退化成一个 `--foo-json` 字符串参数而不是报错。先「跑通全覆盖」，再对高频命令逐个用手工命令**覆盖**自动投影（显式命令优先于生成命令）。

❓ **Q4** - **输出契约：默认给谁看**

三个子问题：默认文本还是 JSON？`est_tokens` 是否常显？退出码是否语义化？

➡️ 推荐：**agent 优先，人读性次要**——默认紧凑定界文本（省 JSON 语法开销）、`est_tokens` 常显（否则 agent 会在大结果上盲展开）、`--json` 作为全量开关；退出码语义化（0=有结果 / 1=空结果 / 2=参数错），让 agent 不用解析 stderr 就能分支。

❓ **Q5** - **发现成本怎么办（CLI 唯一的相对劣势，必须先解决）**

- (a) `codewiki --help` 分级：顶层只列 8 行，子命令详情按需取；
- (b) 自动生成 `AGENTS.md` 速查段（**我强烈反对**：等于把 schema 又常驻一遍，正好抵消 Q1(a) 的收益）；
- (c) `codewiki capabilities --compact`：一行一命令，控制在 500 token 内，agent 首次调用一次即可。

➡️ 推荐：**(a)+(c)**，顶层 help 硬上限 30 行；明确禁止把全量命令清单写进 `AGENTS.md`。

❓ **Q6** - **本次范围要不要含这些非功能项**

- Python 冷启动延迟（每次 CLI 调用 vs MCP 常驻进程）——token 不亏但**时间**亏；
- 无 shell 权限的运行环境（云端沙箱可能用不了 CLI）；
- **Windows/PowerShell 的引号与编码**（中文参数、多行正文，`codewiki` 的 ingest/capture 类命令很可能踩）。

➡️ 推荐：冷启动**本次不解决**（只记录）；无 shell 环境**不解决**（MCP 继续兜底，两者并存而非替代）；**Windows 引号/编码当作硬门槛**——这项不过，agent 根本调不起来，前面省多少 token 都归零。

---

回完这 6 条，下一轮我会问到：参数校验在哪层（复用 registry 校验还是 Click 自己来）、生成命令与手工命令的优先级与命名冲突、`_PUSH_ON_WRITE` 那类副作用在 CLI 下的行为、以及测试/文档单一事实源怎么保证不腐化。
user: 你觉得我们要不要完善CLI呢，收益怎么样
assistant: [tool: task · {"subagent_name": "distill-worker", "description": "蒸馏 Cli能力 积压对话", "prompt": "你按 d:\\repos\\CodeWiki-CN\\.codebuddy\\agents\\distill-worker.md 的…

[tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -c "import sys,json,subprocess;from codewiki.mcp.registry import get_all_tools;t=get…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -c "import sys,json,subprocess;from codewiki.mcp.registry import get_all_tools;t=lis…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\registry.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp]
assistant: 先给结论：**该做，但「完善 CLI」这个框架本身是错的——CLI 单独做，一个 token 都省不下来。**

## 实测数据（我刚在本机跑的）

| 项 | 值 |
|---|---|
| MCP `tools/list` 载荷 | **88,727 字符**（49 个工具）→ 约 **22k–35k tokens** |
| 单工具平均定义 | 1.8k 字符 ≈ 500–700 tokens |
| CLI `codewiki --help` | **915 字符** ≈ 300 tokens |

关键在于：这 25k+ 的 schema **每个 API 请求都要发一次**，跟 agent 到底调不调 MCP 无关。所以一个 30 轮的会话，光工具定义就累计约 **750k input tokens**（有 prompt caching 的话计费打一折，但上下文占用照旧）。

而 CLI 路径：discovery 一次性几百到 1-3k tokens，之后每次只有命令输出。

**所以真正的杠杆不是「加 CLI 命令」，是「砍 MCP 暴露面」。** 只要你 IDE 里还挂着 49 个工具，agent 改用什么都省不了——顺带说一句，我此刻就在付这个成本，我这轮请求里就带着那 49 份 schema。

## 三条路径的 ROI（我按性价比排序）

**P1 — 精简 MCP schema（半天，零架构风险，省 40–60%）**
把 1.8k 字符/工具的 description 瘦身，长说明外移到文档。不用碰任何架构。风险是描述变短后 agent 可能选错工具。
➡️ 我建议**立刻做**，它是唯一「今天投入明天见效」的。

**P3 — CLI 自动投影层（3–5 天，本身不省 token）**
从 `registry.py:58` 自动生成 49 个子命令，不手写。CLI 已有复用先例（`cli/commands/query.py:160` 直接调 `handle_query_wiki`），`docs/Hook多智能体支持设计方案.md:176` 也已定调「CLI 是 handler 的投影层」。
➡️ 它的价值**不是省 token，而是让 P2 可行**——没有 CLI 兜底，砍掉的 37 个工具就没人能调了。它是 P2 的**前置依赖**，不是独立收益项。

**P2 — 分层暴露面（1–2 天，省 70%+，收益主力）**
MCP 默认只暴露 core ~12 个工具（常驻降到 6–8k），其余走 CLI。

⚠️ 这里我要纠正自己上一轮的一个猜测：我原本以为 `registry.py:50` 的 `mode` 字段能直接当分层钩子用——**不能**，它是执行模式（`main_thread`/`thread`/`async`，见 `registry.py:8-10`），跟工具面无关。分层需要给 `ToolDef` 新增一个维度字段 + 在 `server.py:106` 的转发处加过滤。成本比我上一轮暗示的高一点。

## 明确不建议的

- **手写 49 个 CLI 命令**：双份维护，以后每加一个 MCP 工具要改两处，必然腐化。`docs/agents/` 里的 SOP 已经写了「新增 MCP 工具改 handler + registry 两处」，再加第三处会破坏单点收敛。
- **把命令清单写进 `AGENTS.md`**：等于把 schema 又常驻一遍，正好抵消收益。
- **解决冷启动 / 无 shell 环境**：不解决。MCP 继续兜底，两者是**并存而非替代**。

## 一个可以直接拿数据的点

`repowiki/.meta/telemetry/*.jsonl` 里应该有工具调用记录——选哪 12 个进 core，不该拍脑袋，应该按实测调用频次选。这个我可以先跑出来再谈。

---

下一轮前沿（R2，前提已 settle：收益来自收缩暴露面）：

❓ **R2-Q1** - **接受「CLI 单独做不省 token，必须与收缩 MCP 暴露面绑定」这个前提吗？** 如果接受，那「完善 CLI」的验收标准就要从「命令数量对齐」改成「MCP 常驻 token 下降 X%」，这是两套完全不同的验收口径。

➡️ 推荐：接受，验收口径改成后者；否则这个项目会做成「49 个命令都补齐了，但省了 0 token」的经典失败。

❓ **R2-Q2** - **core 面怎么选**：按 telemetry 实测频次取 Top N ／ 按功能域人工圈定 ／ 两者结合（频次定候选，人工裁决）。

➡️ 推荐：两者结合，且先跑 telemetry——「直觉根因必须被数据证伪」是你们 Doctrine 里的原文，这条正好适用。

❓ **R2-Q3** - **被砍掉的 37 个工具，agent 怎么知道它们存在**：靠 `codewiki capabilities --compact` 按需查 ／ 靠报错提示（agent 调 MCP 得到「该工具已移至 CLI，请执行 xxx」）／ 靠分组 MCP server（第二个 server 挂全量，按需连接）。

➡️ 推荐：**报错提示 + 按需查**双通道。方案三（第二个 server）会让工具定义换了个地方常驻，属于自欺欺人。

❓ **R2-Q4** - **默认暴露面谁来定**：硬编码 core 列表 ／ 用户配置（`codewiki config set mcp.surface=core|full`）——注意 `config` 命令组已存在（`main.py:41`、`commands/config.py`）。

➡️ 推荐：配置化，默认 `core`，`full` 留给需要全量的场景。硬编码会把这个决策钉死，而这套系统显然还在演进。

答完 R2，下一轮我会问：投影命令与手工命令的冲突消解、est_tokens/退出码契约（R1-Q4 你还没答）、以及这个决策落盘到哪里（`docs/` 方案 vs `repowiki/notes/` 结论——按 2026-09-10 那条笔记的分工，现在这个阶段应该先在 `docs/`）。

另外：本任务有 1 条待蒸馏对话积压，我刚才派了蒸馏 worker 但它空转了，需要的话我在这个话题告一段落时重派一次。
user: Q1 不接受，我们可以把CLI和skill或者command结合起来做渐进式披露或者默认禁用skill不自动加载进上下文;command会不会自动进上下文你帮我查一下？  Q2
assistant: [tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\.codebuddy"}]

[tool: web_search · CodeBuddy 斜杠命令 slash command 自定义命令 是否自动加载进上下文]

[tool: web_search · CodeBuddy skills 技能 加载机制 渐进式披露 description 常驻上下文]
assistant: [tool: web_fetch · https://www.codebuddy.ai/docs/zh/ide/Features/Skills]

[tool: web_fetch · https://www.codebuddy.ai/docs/zh/cli/slash-commands]

[tool: list_dir · {"target_directory": "C:\\Users\\Administrator\\.codebuddy"}]
assistant: [tool: read_file · {"filePath": "C:\\Users\\Administrator\\.codebuddy\\mcp-disabled-tools.json"}]

[tool: search_content · C:\Users\Administrator\.codebuddy\mcp.json]
assistant: 先认账：**Q1 我错了，但只错在「唯一性」，没错在「前提」。**

我把「收缩 MCP 暴露面」当成了唯一手段。你说的渐进式披露是**另一条独立手段，而且更优**。但有个东西没变：只要 codewiki MCP server 在会话里是 `disabled: false`，那 25–35k token 就每轮常驻——跟 agent 到底走 CLI 还是走 MCP 无关。所以不是前提被推翻，是**达成同一前提有两条手段，你那条常驻成本更低**。

## 你要我查的：command 会不会自动进上下文

**会，默认会。**（来源：CodeBuddy Code 官方 slash-commands 文档）

- 自定义命令放 `.codebuddy/commands/*.md`（项目级）或 `~/.codebuddy/commands/*.md`（全局）。
- 文档原文：frontmatter 设 `disable-model-invocation: true` 时「**命令不会出现在 Skill 工具中，只能通过 `/command-name` 手动触发**」——反过来读就是：**不设这个开关，命令会以 Skill 形式暴露给模型**，即它的 name/description 常驻上下文。
- 所以你的担心完全成立：如果真把 49 个能力做成 49 个 command 且不 disable，常驻成本又变成 49 条 description ≈ 几千 token，等于把 MCP schema 换了个马甲常驻。

> 一个不确定性：这是 `/docs/zh/cli/slash-commands`（CodeBuddy Code）的文档，IDE 端我**没有独立验证过**。你本会话里 `@command://grill-me` 的实际行为是「调用时把内容注入上下文」，跟文档描述的「可作为 Skill 暴露」至少不矛盾，但严格结论要实测。

## 三个现成开关（我刚在你机器上翻到的）

| 开关 | 位置 | 粒度 |
|---|---|---|
| MCP server 禁用 | `~/.codebuddy/mcp.json:27-34` 每 server `disabled` | 整 server |
| MCP 单工具禁用 | `~/.codebuddy/mcp-disabled-tools.json:2` `disabledTools: {}`（当前空） | 单工具 |
| Skill/Command 禁用 | skill frontmatter `disable: false`；command frontmatter `disable-model-invocation: true` | 单个 |

`codewiki` server 现在是 `disabled: false`（`mcp.json:34`），另外 4 个 server 是 `true`。**也就是说你要的「默认不进上下文」机制，IDE 已经原生支持了，不用改一行 registry。** 这直接砍掉我上一轮 P2 里「给 `ToolDef` 新增字段」那 1–2 天的活。

## 量级对比（用官方口径重算）

| 方案 | 常驻成本 | 按需成本 |
|---|---|---|
| 现状 MCP 49 工具 | ~25–35k token | 0 |
| 我的 A：收缩到 core 12 | ~6–8k token | 0 |
| 你的 B：skill 渐进披露 + MCP 关 | **~100 词（skill metadata）** | <5k 词（触发时） |

你赢了两个数量级。前提是执行层得有东西接住——**那就是 CLI**。所以正确的模型不是「CLI 对齐 MCP」，而是三层：

> **披露层**（skill/command，~100 词常驻）→ **执行层**（CLI）→ **后端**（MCP，可开关）

## 但你要付三笔代价

1. **可靠性换 token**：skill 触发靠模型读 description 判断。description 写歪 → 不触发 → 这个能力对 agent 等于不存在。MCP 工具是「在就在」。
2. **body 有硬上限**：官方写 SKILL.md body <5k 词。49 个工具的参数说明**大概率装不进一个 skill**，必须拆成多个 skill，或把细节塞 `references/`（第三级按需加载）。
3. **disable 之后 agent 完全无感**：设了 `disable-model-invocation` 就只能人肉 `/xxx`，hook / subagent 这类自动化场景会断。

## 我建议你先做一个动作：把估算换成实测

这个 IDE 自带两个测量命令，正好做 Q1 的基线：

- `/context all` —— 计算当前会话上下文 token 分布，展开 Memory / **Skills** / Agents 明细
- `/skills` —— 列出已加载 skills 并显示**预估 token 数量**

跑一下把 MCP 那块的实际 token 贴给我。我上一轮的 88,727 字符是我从 `get_all_tools()` 量的**载荷体积**，不是 IDE 实际注入量——这两者可能差很多（IDE 可能截断、改写或缓存）。**在拿到这个数之前，我不该再拿 25–35k 说事。**

## R2-Q2 在新框架下形态变了

原来是「core 面留哪 12 个」。现在取决于一个还没定的事：**默认会话里 MCP server 到底开不开**。

- 关 → 不存在 core 面问题，只剩「49 个能力怎么切进 N 个 skill」
- 开 + `disabledTools` 精禁 → core 面问题原样保留，telemetry 选 Top N 仍然适用

---

❓ **R3-Q1** - **三层分工（披露层 skill/command / 执行层 CLI / 后端 MCP 可开关）这个模型你接受吗？** 如果接受，「完善 CLI」的范围就从「对齐 49 个工具」缩成「让 CLI 能完整执行 skill 里承诺的动作」——验收标准完全不同。

➡️ 推荐：接受。这样 CLI 只需要补齐 skill 会引导 agent 去做的那批动作，而不是 49 个。

❓ **R3-Q2** - **默认会话里 codewiki MCP server 开还是关？**（`mcp.json:34` 现在是 `false`＝开）
- 关：省到极致，但 /context 里工具数是 0，agent 只能靠 skill + CLI
- 开 + `disabledTools` 精禁到 ~10 个：保留 MCP 的类型校验与 IDE 侧展示，常驻降到 ~5k

➡️ 推荐：**先开 + 精禁**做过渡，跑一段时间拿到 telemetry 再决定要不要全关。一刀切关掉会同时失去 schema 校验，而你们 Doctrine 里明确写了「不绕过 dispatch/schema 校验直连 handler」。

❓ **R3-Q3** - **披露粒度**：一个 `codewiki` 大 skill（body 有 5k 词硬上限，可能装不下 49 个能力）／ 按域拆 5–8 个 skill ／ 一个极薄 skill + `references/` 按需加载。

➡️ 推荐：**1 个薄 skill（能力索引 + 触发规则）+ 按域的 `references/`**。理由：description 命中率随单个 skill 职责变窄而提高，而大 skill 的 description 必然写得很泛，正好踩中代价 1。

❓ **R3-Q4** - **怎么验收触发可靠性**：description 命中率要不要做实测（造 20 条典型 query，看 skill 是否被触发）。

➡️ 推荐：要。这是路径 B 唯一的真正风险点，而它是可测的——不测的话省下的 token 会以「该用没用」的形式悄悄还回去。

R2-Q4（默认暴露面硬编码 vs 配置化）在新框架下变成「`disabledTools` 谁来维护」，我下一轮再问。

<!-- 待办：本任务 1 条待蒸馏对话积压，本话题告一段落时我重派一次蒸馏 worker -->
user: /context all
assistant: 我没看到 `/context all` 的输出——它跑在你的终端里，结果没进我这边的上下文。麻烦把输出贴过来。

我具体要这三个数：

1. **MCP / Tools 那一块的 token**（如果有细分，最好到 `codewiki` 这个 server）
2. **Skills 那一块的 token**（常驻的 metadata 部分）
3. **总上下文 / 已用占比**——用来判断 25–35k 在 200k 窗口里到底占多少，是不是真值得为它动架构

（顺带说：`/context` 是 CodeBuddy **Code** 文档里列的命令，IDE 端能不能用我没验证过。如果你这边提示命令不存在，别折腾，直接用下面的替代方案。）

## 替代方案：端到端实测，比静态估算可信

同一个小任务跑两遍，用 `/cost` 对比 input token：

- **A 组**：现状（MCP 开，49 工具，走 MCP 调 `query_wiki`）
- **B 组**：`mcp.json:34` 改成 `disabled: true` + 一个薄 skill 引导走 CLI

任务就用这次的真实场景：查一条笔记 + 写一条 draft。两组的**输出**应该一样，差值就是纯 schema 常驻成本。

这个测法有个好处：它同时把 Q1 那个争议点一起验证了——如果 A/B 差值接近我估的 25k/轮，那路径 B 的收益就是真的；如果差值只有 2–3k（比如 IDE 侧做了缓存或压缩），那我们这四轮讨论的整个前提都得推翻，**那就该收手不做**。

贴数过来我就不再拿估算说事了。

[User Cancelled]
user: 是不是可以加跟mcp工具一比一数量一致的skill或者command?
assistant: 短答：**不建议 1:1，但你的直觉对了一半——要分「给 agent 用」还是「给人用」。**

## 先算账：1:1 不是消灭常驻，是换了个计量单位

官方口径：skill metadata **始终在上下文，约 100 词/个**（`Skills` 文档「渐进式披露设计原则」）。

- 49 个 skill × 100 词 ≈ **4,900 词常驻**
- 中文的「100 词」token 化比英文差，粗估 1 词 ≈ 1.5–3 token → **7–15k token 常驻**

对比一下：我上一轮估的「MCP 收缩到 core 12 个」是 6–8k。**1:1 skill 跟路径 A 基本打平，甚至更贵。**

收益不是来自「1:1」，是来自「描述比 schema 短」。而如果真要短，**1 个薄 skill ≈ 130 token**，比 49 个又省两个数量级。

## 三个更硬的反驳

**1. skill 不执行，它只是注入一段话。** 1:1 skill 的本质是：把「结构化 schema + IDE 侧校验」换成「让模型读一段散文，然后自己拼命令行字符串」。拼错了就是 bash 报错，没有必填校验、没有枚举约束。你们 Doctrine 白纸黑字写了「不绕过 dispatch/schema 校验直连 handler」——1:1 skill + CLI 正好是这条反模式的规模化版本。

**2. 触发是乘法风险，不是加法。** 49 个语义相近的 description（`query_wiki` / `query_cross_service` / `read_code_components`…）互相竞争，模型每次要从 49 个里挑一个。误触发率不是 49 个独立的小概率，是每次调用都要过一次 49 选 1。

**3. 1:1 恰好放弃了 skill 唯一的增量价值。** MCP 的粒度是原子操作，skill 的粒度应该是**工作流**。一个 skill 能写「先 capture → 再 distill → 再 confirm」，这是单工具 description 写不下、写进去就膨胀 schema 的东西。1:1 把 skill 降级成 MCP 的镜像——那为什么不直接用 MCP？

## 我认为对的粒度：按工作流聚合，8–12 个

- `wiki-query` 一个 skill 吃掉 `query_wiki` 的 check/overview/detail 多 mode
- `knowledge-capture` 一个吃掉 `capture_conversation` + `distill_conversation` + `ingest_note` + `confirm_note` 整条流水线
- 参数细节丢进 `references/`（第三级，按需加载）

常驻 ≈ 1.2k 词 ≈ **2–3k token**，比 1:1 再省 3–5 倍，而且每个 skill 职责窄 → description 好写 → 命中率高。

## 但对「人」来说，1:1 command 是纯赚

`command` + `disable-model-invocation: true` → **常驻 0**（文档：不出现在 Skill 工具中，只能 `/name` 手动触发）。

49 个 command 一对一映射，成本是 0 token 常驻，收益是人不用记 CLI 参数。**这才是 1:1 的正确落点**——尤其适合低频、危险、agent 容易搞砸的操作（`compact_task_memories`、`refresh_doctrine`、`retract_source` 这类）。

所以收敛成一条：**给 agent 的按工作流聚合（8–12 个 skill），给人的可以 1:1（49 个 command，全部 disable-model-invocation）。**

## 剩下的问题：维护

1:1 意味着每加一个 MCP 工具要同步改 skill/command 文件，49 → 98 处。这直接撞 Doctrine 的「单点收敛：同构逻辑只留一份」。

**除非 skill/command 也从 registry 生成**——同一个生成器，产出三份投影：MCP schema、CLI 子命令、skill/command 文件。这样单点收敛保住了，1:1 的维护成本归零。生成器本身我认为该做；但即使维护免费，常驻 7–15k 和触发竞争那两个问题还在，所以我仍然不推荐给 agent 用 1:1。

---

❓ **R4-Q1** - **接受「给 agent 的按工作流聚合 8–12 个，给人的 1:1 command 且全部 disable-model-invocation」这个拆分吗？**

➡️ 推荐：接受。它把「省 token」和「好用」两件事解耦了——前者靠聚合，后者靠 0 常驻的手动命令，互不牺牲。

❓ **R4-Q2** - **skill/command 要不要从 `registry.py` 自动生成？**（与 CLI 投影共用一个生成器 vs 手写维护）

➡️ 推荐：生成。这不是为了省事，是为了满足「单点收敛」——否则 49 个能力会有 MCP schema / CLI / skill 三份手写真相，必然腐化。注意这条会让 R3-Q1 的三层模型里多出一个「生成器」角色。

❓ **R4-Q3** - **8–12 个工作流 skill 怎么切？** 按现有知识管线阶段切（采集 / 蒸馏 / 归档 / 治理 / 检索）／ 按使用频次切 ／ 按「谁在用」切（日常高频 vs 维护低频）。

➡️ 推荐：**按管线阶段切**，切完再看 telemetry 合并低频的。按频次切会导致每次新增工具都要重划边界，边界不稳定。

❓ **R4-Q4** - **`/context all` 那个数还测吗？**（上一轮你跑了但我没看到输出）

➡️ 推荐：测。上面所有 token 数字除了 88,727 字符那个是实测，其余全是估算——包括「100 词」那个官方口径在中文下的真实 token 数。在拿到真实分布前，这整棵设计树都建在沙子上。
user: 暂时先不做这个需求，你先把当前方案归档吧。
assistant: [tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\docs\\adr"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\agents\\domain.md"}]

[tool: search_file · *设计文档落盘分工*]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\repowiki\\notes\\2026-09-10-设计文档落盘分工docs-存正在想的事方案adrrepowiki-存想明白的结论notequerycomparison.md"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\adr\\0004-skill-scenario-split-two-zone-gate.md"}]
assistant: [tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\docs", "ignore_globs": ["**/adr/**"]}]
assistant: [tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\docs\\plans"}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\plans\\knowledge-store-rfc.md", "limit": 30}]

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"add_task_memory\"]]"}]
assistant: [tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\plans\\cli-capability-progressive-disclosure.md", "content": "# Plan: CLI 能力增强——用渐进式披露替换 MCP…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"Cli能力\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: 归档完成。

## 落盘位置

**`docs/plans/cli-capability-progressive-disclosure.md`**（Status: deferred）

按 `repowiki/notes/2026-09-10-设计文档落盘分工...md:30-40` 的分工放的 `docs/plans/`——这是「正在想的事」，还没到「想明白的结论」，所以没进 repowiki。文档含：

- **Problem**：49 工具 vs 12 动词、88,727 字符实测、CLI 两个真实缺口（`--json` 缺失、`est_tokens` 未渲染）
- **核心认知**：收益来源是常驻，不是输出；「完善 CLI」本身不产生收益
- **三层模型** + IDE 侧已有开关清单（`mcp.json` / `mcp-disabled-tools.json` / skill `disable` / `disable-model-invocation`）
- **已 settle D1–D4 / 未 settle O1–O6**（恢复时直接接续）
- **被排除的候选及原因**（Doctrine 要求候选必有去向）
- **可信度边界**：除 88,727 字符外全是估算，逐条标注了未验证项
- **恢复条件**：判定线写死了——差值接近 22k–35k/轮就继续，只有 2–3k 就整个推翻收手

**任务记忆**已写入 `Cli能力`（ADR-0002 直写，无需确认闸门），含恢复条件与「实测前不要再拿估算推进设计」这条约束。

## 要不要再沉一条 repowiki 笔记？

有两块是**跨任务可复用的通用经验**，不只属于这个任务：

**候选 A（decision）—「完善 CLI」的收益不在 CLI，在让 MCP 工具定义不再常驻**
背景：用户提「CLI 对齐 MCP 更省 token」→ 追问发现只要 MCP server 启用，工具定义每轮都进请求，与 agent 用不用无关。结论：CLI 增强只是让「关掉 MCP」可行，收益必须用「常驻 token 下降 X%」验收，不能用「命令数量对齐」验收。根因：把手段（加命令）当成了目标（卸掉常驻）。

**候选 B（pitfall）— skill 一对一映射 MCP 工具的三个陷阱**
① 常驻不是 0：N × 100 词，49 个 ≈ 7–15k token，与「收缩到 core 12 个」打平；② skill 只注入指令不执行，等于用「模型拼命令行字符串」替换 schema 校验；③ 放弃工作流粒度这个 skill 唯一的增量价值。

按闸门规则这两条都得你点头才落盘。要哪条、都要、还是都不要？

另外：本任务还有 1 条待蒸馏对话积压（就是这次会话），要我现在派 worker 跑掉吗？
user: 我觉得可以先优化一下当前mcp方法的描述等信息， @prompts.py:502-513  比如把prompts.py的大段大段中文改为英文、简化各个工具的描述信息等。也可以精简工具
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_measure_tools", "content": "import json, sys, os\nsys.path.insert(0, r\…

[tool: execute_command · cd d:/repos/CodeWiki-CN; Get-Content repowiki/.meta/telemetry/iamwangbao-163-com.jsonl -TotalCount 3]
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_measure_tools.py", "content": "import json, sys, os\nsys.path.insert(0,…

[tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -c "import json,collections;c=collections.Counter();[c.update([json.loads(l).get('t'…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe C:\Users\Administrator\AppData\Local\Temp\cw_measure_tools.py]
assistant: [tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py]
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe C:\Users\Administrator\AppData\Local\Temp\cw_measure_tools.py 2>&1 | Select-Object -…
assistant: 方向对，但你举的例子和「中译英」这个手段，实测下来**收益接近 0**。先看数据。

## 88,629 字符的拆解（我刚跑的）

| 部分 | 字符 | 占比 |
|---|---|---|
| 工具级 `description` | 38,980 | **44%** |
| 参数级 `description` | 22,839 | **26%** |
| `enum` 取值 | 2,011 | 2% |
| 结构开销（JSON 键名/类型/嵌套） | 24,799 | 28% |

**CJK 字符：20 个 / 88,629。工具定义已经是全英文了。** 中译英在工具侧没有收益——这条从方案里划掉。

## 你举的 prompts.py:502-513 为什么省不了

那一段在 `_prompt_search_wiki` 里，走的是 MCP `prompts/get`——**按需返回，不进每轮请求**。改英文省的是「被调用那一次」的开销，不是常驻。

而且**正确做法也不是改成英文**：`codewiki/mcp/i18n.py` 已经有双语机制（`locales/zh.yaml` 源 + `en.yaml` 全覆盖），prompts.py 的 title/description 走的是 `_i18n.t(...)`（`prompts.py:1479-1488`）。问题是 `_prompt_search_wiki` 这类把正文**内联写死中文**，绕过了 i18n——所以 `lang=en` 对它们无效。

两个更省事的做法：
- **零改动**：`~/.codewiki/config.json` 设 `lang: en`，已 i18n 化的部分立刻切英文（解析顺序见 `i18n.py:152-155`）
- **治本**：把内联中文外移到 `locales/*.yaml`，这才符合 `prompts.py:1427-1428` 注释自己声明的设计

## 真正的靶心：描述占 70%，而且高度集中

- **Top 8** = 29,298 字符 = **33%**（`query_wiki` 5,655、`distill_conversation` 4,623、`skill_creator` 3,984、`ingest_source` 3,957、`lint_wiki` 3,832、`write_doc_file` 3,723、`ingest_note` 3,524）
- **Top 15 = 54%**
- 中位 1,545，最大 5,655，最小 525

描述类文本砍半 ≈ **省 31k 字符 ≈ 7.7k token/轮**（总 22k → 14.3k，-35%）。

## 但「精简工具」这条要泼冷水

**Bottom 15 个工具加起来只有 11,960 字符 = 13.5%。** 砍掉 15 个能力只换 13.5% —— 这是所有手段里性价比最差的。

原因很直白：体积跟工具数量**不成正比**，跟参数数量和描述长度成正比。`query_wiki` 一个工具（18 个参数）就比最小的 10 个工具加起来还大。

所以优先级反过来：**先瘦身大工具的描述和参数，别先砍工具。**

## 还有一个我上轮的错误要纠正

我说过「用 telemetry 实测频次选 core 面」——**telemetry 里没有 MCP 工具调用数据**。我查了 `repowiki/.meta/telemetry/iamwangbao-163-com.jsonl`，只有 3 种记录：`hit` 429 / `by_file` 24 / `adopted` 8，全是 wiki 检索命中，不含工具调用。所以「按频次砍/留工具」目前**无数据支撑**，只能人工判定。

---

以上已追加进 `docs/plans/cli-capability-progressive-disclosure.md`（新增「体积拆解实测」一节）。

❓ **R5-Q1** - **P1 的动手范围**：只动 Top 15（54% 体积，改 15 处）／ 全量 49 个（70% 描述，改 49 处）／ 只动 Top 8（33%）。

➡️ 推荐：**Top 8 先做**，拿到实测反馈再决定要不要推到 Top 15。理由：8 个工具里 4 个的 description 超过 2,000 字符（`lint_wiki` 2,470、`ingest_source` 2,269、`skill_creator` 2,155、`init_workspace` 1,855），这些明显是把使用文档钉进了 schema，砍到 300–400 字符完全够用且风险最低。

❓ **R5-Q2** - **瘦身到什么程度**：只留「何时用 + 关键约束」／ 保留 1 行示例／ 保留 `mode` 枚举说明。

➡️ 推荐：**只留「何时用 + 关键约束 + 必填语义」**，示例与长说明外移到 `docs/` 或 MCP prompt。风险是 agent 用错工具——所以这题跟下一题绑定。

❓ **R5-Q3** - **怎么防止瘦身导致 agent 用错**（这是 P1 唯一真实风险）：靠回归测试（造 N 条 query 看工具选择）／ 靠保留 `mode` 等易错参数的枚举说明 ／ 靠报错信息里回带正确用法。

➡️ 推荐：**保留易错参数的枚举说明 + 造 20 条 query 做人工前后对比**。纯靠测试不够——工具选择错误是语义问题，不是崩溃，跑测试发现不了。

❓ **R5-Q4** - **`query_wiki`（18 参数）和 `distill_conversation`（14 参数）要不要顺带收参数？** 这俩是体积冠亚军，参数合并能同时压掉 prop description 和结构开销两块的 28%。

➡️ 推荐：**先不动参数**。改参数 = 改契约，会打断所有调用方，风险远高于改描述。描述瘦身是纯收益，参数收缩要单独评估——而且你们 Doctrine 写了「改契约先分清校验层」。

❓ **R5-Q5** - **prompts 内联中文要不要一并处理？**（外移到 yaml vs 保持现状）

➡️ 推荐：**保持现状，本次不动**。它不常驻，收益不在这一轮 Priority 里；真要做应该按 `prompts.py:1427-1428` 的设计意图外移到 yaml，那是独立的小任务。

答完 R5 我就有足够信息开始改 `registry.py` 的 Top 8 描述了。要我现在就动手，还是先把 Q1 定下来？
user: 可以精简AGENTS.md里自动加的内容，你觉得呢
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_measure_agents.py", "content": "import sys\np = r\"d:\\repos\\CodeWiki-…

[tool: search_content · d:\repos\CodeWiki-CN]
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe C:\Users\Administrator\AppData\Local\Temp\cw_measure_agents.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\agents_md.py]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\cli\utils\ide_config.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: 可做，而且**单位字符收益比 MCP 那 88k 更高**。但有个前提必须先讲，否则你改了也白改。

## 先说最重要的一条：79% 是生成器托管的

| 块 | 字符 | 占比 | 归属 |
|---|---|---|---|
| `<!-- CodeWiki LLM Wiki -->` | 3,499 | 34% | `agents_md.py:68,121-139` |
| `<!-- TEAM-MEMORY-TASK -->` | 3,286 | 32% | `ide_config.py:249-259`（`install-hooks` 时 upsert） |
| `<!-- CODEWIKI-QWENWORK -->` | 1,222 | 12% | `ide_config.py:261-273` |
| `## Team memory fusion` | 1,713 | 17% | 手写 |
| `## Agent skills` | 395 | 4% | 手写 |

`_upsert_marked_section`（`agents_md.py:35-59`）的行为是**只替换标记内的内容，标记外原样保留**。所以直接编辑 AGENTS.md，下次 `install-hooks` 或 `generate` 一跑就冲掉了。**要持久生效必须改模板和常量，不是改文件。**

## 我的判断：值得做，但风险性质和 MCP 完全不同

**收益侧**：AGENTS.md 10,175 字符，粗估 4–6k token 常驻。绝对值比 MCP 的 ~22k 小，但它是**纯散文、零结构开销**——MCP 那 88,629 字符里有 24,799（28%）是 JSON 键名和嵌套，砍不掉；AGENTS.md 每个字符都是有效载荷。

**风险侧**：MCP 描述删多了，最坏是 agent 选错工具、会报错、能发现。AGENTS.md 装的是**行为契约**——标注依据、确认闸门、任务关联、不自动蒸馏。删掉**不会报错，只会静默退化**：agent 不再标来源、不走过闸门、不做任务关联。这正好撞 Doctrine 的「不静默失败」。

所以这一刀要按「铁律 vs 说明书」切，不能按字数切。

## 我建议的三刀（按性价比）

**第一刀：QwenWork 块 1,222 字符（12%），风险 0**
它只在 `--ide qwenwork` / prompt 模式下才有意义（`ide_config.py:316-318`）。你在 CodeBuddy 里跑，这 12% 是纯粹的噪声。

**第二刀：Task memory 块 3,286（32%）外移**
里面是给 agent 的**操作剧本**——弹框流程、`set_session_task` 参数、压缩阈值、目录布局。这类「怎么做」正是最适合渐进式披露的内容：留一句「会话开始先做任务关联，细节按需加载」，剧本挪进 skill 或 `references/`。

**第三刀：CodeWiki LLM Wiki 块 3,499（34%）去重**
里面「使用建议 / 路由表 / 采纳声明示例」跟 MCP 那 38,980 字符的工具描述**高度重复**。Doctrine 明写「避免重复：信息应存在于一处，不要两处都有」。这一刀和 P1（MCP 描述瘦身）会互相放大——重复信息两边都留着，等于付两次钱。

**不该动的**：确认闸门对等、回答时显式标注依据、不自动蒸馏/聚合。这几条短，但是 Doctrine 的落点，删了就是行为退化。

---

以上已追加进 `docs/plans/cli-capability-progressive-disclosure.md`。

❓ **R6-Q1** - **三刀的顺序和范围**：只做第一刀（QwenWork，12% 零风险）／ 第一+二刀（44%）／ 三刀全做（78%）。

➡️ 推荐：**先只做第一刀并验证生成器链路**。理由：这一刀的价值不在省 12%，而在于**验证「改模板→重新 upsert→AGENTS.md 生效且不被回冲」这条链路通不通**。链路不通，后面两刀都是白干。

❓ **R6-Q2** - **Task memory 剧本外移到哪**：MCP prompt（已有 `prompts.py` 的 `task-workflow` prompt）／ skill + `references/` ／ `docs/` 纯文档。

➡️ 推荐：**外移到已有的 MCP prompt `task-workflow`**（`prompts.py:1232`）——它本来就是这个内容的家，AGENTS.md 里只留一行指针。新建 skill 会引入第三种资产类型，而 prompt 已经是现成且按需加载的。

❓ **R6-Q3** - **去重后，「怎么用 CodeWiki」的真相放哪边**：放 MCP 工具描述（agent 调用时必然看到）／ 放 AGENTS.md（常驻但占 token）／ 放 prompt（按需）。

➡️ 推荐：**放 MCP 工具描述 + prompt 两级，AGENTS.md 只留铁律和指针**。理由：MCP 描述是 agent 决定调不调时才看，prompt 是决定怎么用后才取，两者都是按需；常驻层只放「必须无条件遵守」的东西。

❓ **R6-Q4** - **手写段（Team memory fusion 1,713 + Agent skills 395）要不要一起瘦？** 这 21% 改了不会被覆盖，但内容是实现入口和 SOP 清单，删了会丢上下文。

➡️ 推荐：**本次不动**。它们不受生成器管辖，随时可改，不占用这次的链路验证；而且 `## Agent skills` 只有 395 字符，性价比低。

❓ **R6-Q5** - **验收方式**：改完怎么确认没退化？

➡️ 推荐：**造 5 条检查项**（是否标注来源、是否走确认闸门、是否做任务关联、是否自动蒸馏了、是否知道 CLI 存在），改前改后各跑一次。这跟 R5-Q3 是同一类风险——行为退化不报错，只能主动探测。

先定 Q1，我就去改 `ide_config.py` 那一处并跑一次 upsert 验证链路。
user: 按你推荐来，本次只改AGENTS.md写入内容
assistant: 按推荐来：本次只做第一刀（QwenWork 块），并验证生成器链路。先确认写入逻辑。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\cli\\utils\\ide_config.py", "offset": 240, "limit": 100}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\AGENTS.md", "offset": 183, "limit": 32}]
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_verify_agents.py", "content": "import sys\nfrom pathlib import Path\n\n…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe C:\Users\Administrator\AppData\Local\Temp\cw_verify_agents.py]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\tests]
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -m pytest tests/test_install_hooks.py tests/test_strip_system_injection.py -q 2>&1 |…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"Cli能力\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: 第一刀落地，只动了 AGENTS.md 内容，没碰生成器代码。

## 结果

| 项 | 改前 | 改后 |
|---|---|---|
| 字符 | 10,175 | **8,952**（-1,223，**-12.0%**） |
| 行数 | 214 | 186 |

删除 `<!-- CODEWIKI-QWENWORK:START/END -->` 块（1,222 字符）。

## 链路验证（这一步才是本刀的重点）

- `upsert_agents_section` 连续调用两次，均返回 `False`（无变更）
- `CODEWIKI-QWENWORK` 标记**未回冲**
- `TEAM-MEMORY-TASK` 与 `CodeWiki LLM Wiki` 两块原样保留
- 文件尾部正常收在 `<!-- TEAM-MEMORY-TASK:END -->`

**不会回冲的依据**：`upsert_qwenwork_protocol` 只在 `wiring == "prompt"` 分支被调用（`cli/utils/ide_config.py:315-318`），hook 模式的 `install-hooks` 只调 `upsert_agents_section`（`:386-387`）。

**可逆**：QwenWork 用户重跑一次 `--ide qwenwork` 接线，协议段自动写回，不需要手工恢复。

## 测试

`tests/test_install_hooks.py` + `tests/test_strip_system_injection.py` —— **46 passed**。

## 归档

- `docs/plans/cli-capability-progressive-disclosure.md` 新增「执行记录」一节，含结果、验证过程、不回冲依据、可逆性
- 任务记忆已写入 `Cli能力`，含一条后续别踩的约束：**AGENTS.md 79% 由生成器托管，持久改动必须改模板或常量**——本刀能只改文件，纯属 QwenWork 块只在 prompt 模式写入

## 剩下的两刀（等你定）

- **第二刀 32%**：Task memory 剧本外移到已有的 MCP prompt `task-workflow`（`prompts.py:1232`），AGENTS.md 只留一行指针 → 需要你确认 R6-Q2
- **第三刀 34%**：Wiki 块与 MCP 那 38,980 字符的工具描述去重 → 需要你确认 R6-Q3

另外提醒一句：这一刀省下的 1,223 字符是**本仓库**的收益。同样的 AGENTS.md 块也写进了你其他接线的仓库，如果要全局生效，得改 `_QWENWORK_CAPTURE_SECTION` 常量或做一次批量清理——要我做吗？
user: 修改向AGENTS.md写内容的相关代码
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_file · *.tpl]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\agents_md.py", "offset": 196, "limit": 55}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\injection_budget.py"}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 36, "limit": 60}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 1232, "limit": 40}]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\tests]
assistant: 现在改写入代码。先精简 Task memory 段（`prompts.py:40-67`），把实现细节外移到已有的 `task-workflow` prompt。
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_verify_agents2.py", "content": "import sys\nfrom pathlib import Path\n\…
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe C:\Users\Administrator\AppData\Local\Temp\cw_verify_agents2.py]
assistant: [tool: execute_command · cd d:/repos/CodeWiki-CN; .venv/Scripts/python.exe -m pytest -q 2>&1 | Select-Object -Last 18]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "add_task_memory", "arguments": "{\"task_id\":\"Cli能力\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: 第二刀落地，改的是生成器本体，全局生效。

## 改了什么

**`codewiki/mcp/prompts.py:40` — `_TASK_MEMORY_AGENTS_SECTION`**

3,286 → **836 字符（-74.6%）**

- **保留**：5 条运行时铁律——弹框只弹一次/一框列全、`set_session_task` 绑定、`get_task_context` 拉上下文、`pending_raw_count > 0` 委托 subagent 后台补蒸馏、草稿须 `confirm_note` 而任务记忆直写（ADR-0002）
- **外移**：存储布局、task_id 不可变、绑定文件一次性消费、分层有界（20/5）、压缩阈值（40 条/24KB）、`compact_task_memories` 两段式 → 全部搬进同文件的 `_prompt_task_workflow`（MCP prompt `task-workflow`），新增「存储布局与实现约束（改代码 / 排查时查阅）」段，**内容一条没丢**
- **指针**：段尾加 `get_prompt(name="task-workflow")`

**联动生效**：这个常量同时被 `prompts.py` 里两处安装/卸载指令引用（告诉 agent 往 AGENTS.md 写什么），改一处三处同时变短，没有第二份真相。

## 结果

| | 改前 | 改后 |
|---|---|---|
| Task memory 段 | 3,286 | **836** |
| 本仓库 AGENTS.md | 10,175 | **6,473**（-3,702，**-36.4%**） |

链路验证：`upsert_agents_section` 第一次返回 `True`（替换旧块），第二次 `False`（幂等）；QwenWork 标记未回冲，Wiki 块与指针均在位。

**测试：全量 `pytest` 924 passed, 2 skipped。**

## 为什么第三刀没动

Wiki 块（3,499 字符，文案在 `locales/{zh,en}.yaml` 的 `artifacts.agents_md.main`）要和 MCP 那 38,980 字符的工具描述**去重**。但现在两边都还是原样，先砍哪边都可能删掉「另一边也没有」的信息。正确顺序是：**先做 P1（MCP 描述瘦身）定下「信息归谁」，再回头砍 AGENTS.md 的重复部分**。顺序反了就会丢东西。

`_QWENWORK_CAPTURE_SECTION`（933 字符）也保持不动——它只在 prompt 模式注入，是千问办公平台的协议正文，砍了那个平台就没法用了。

## 一个还没解决的数字问题

上面全是**字符**口径。`injection_budget.py:90-99` 的 `estimate_tokens` 按 `chars/4` 折算，但它自己的 docstring 写着「zh ~1.5 tokens/char, en ~0.25」——**中文按 /4 会严重低估**。AGENTS.md 以中文为主，所以 6,473 字符的真实 token 大概率远高于 1.6k。

意味着：**这次实际省下的 token 比 36.4% 更多**，但具体多少得用 `/context all` 或真实 tokenizer 才能定。那个数你还没给我，我暂时不下结论。

要我现在顺手把 P1（MCP Top 8 工具描述瘦身）做掉吗？做完第三刀就有依据了。
