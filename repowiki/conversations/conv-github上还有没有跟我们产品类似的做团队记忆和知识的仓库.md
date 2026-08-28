---
type: Conversation
title: "conversation 20260824T164218Z"
status: pending
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T16:42:18Z }
captured_at: "2026-08-24T16:42:18Z"
content_hash: "sha256:82529b53e621430d3865a792d87f9d10930f536a25f8d4c6095c0840cadccdee"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=5"
keep_raw: false
link_to: ""
source_session: "0fd47f5c1fc24de2b84f642a9763843f"
task_id: "产品维护"
turn_count: 17
---

# Conversation Transcript

user: github上还有没有跟我们产品类似的做团队记忆和知识的仓库
user: <question>是否关联到某个进行中的任务？</question>
<answers>
关联已有任务：产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 已绑定任务「产品维护」并拉取上下文。检测到 1 条未蒸馏积压，我先委托蒸馏 worker 后台补蒸馏，同时开始回答你的问题。
assistant: 我先在后台启动补蒸馏 worker，同时继续深入调研类似项目。
assistant: 蒸馏 worker 已在后台运行。继续深入调研最相关的几个项目。
assistant: 调研完成。以下是 GitHub 上与 CodeWiki 做「团队记忆 + 知识管理」最相近的仓库，按相似度分层：

## 1. 直接竞品（团队级记忆 + 知识资产，相似度最高）

**TencentDB Agent Memory** — `github.com/TencentCloud/tencentdb-agent-memory`
- 腾讯云开源，~19.9k stars，MIT
- 团队级 Agent 记忆中枢：把对话、文档、代码沉淀为**四种记忆资产**——Chat Memory、Skill、Wiki、CodeGraph
- 核心思路（L0~L3 分层记忆、自动捕捉 + 异步蒸馏、团队共享经验）与 CodeWiki 的「对话采集 → 蒸馏 → 知识飞轮」几乎一一对应：`CodeGraph` ↔ 你的 `repowiki` 代码知识、`Wiki` ↔ `query_wiki` 笔记、对话蒸馏 ↔ `capture/distill_conversation`、任务上下文 ↔ `task memory`

## 2. 理念同源（LLM Wiki 模式，CodeWiki 名字的灵感源头）

**Andrej Karpathy LLM Wiki**（2026-04 开源）— 提出「LLM 增量编译并维护持久 Markdown wiki」模式，区别于每次检索的 RAG；衍生实现：
- `github.com/nvk/llm-wiki` — "LLM-compiled knowledge bases for any AI agent"
- `github.com/peterstef1983/llm-wiki-agent`、`github.com/emakhov/llm-wiki-agent` — 个人 LLM Wiki 知识库
- `github.com/owenliang/llm-wiki` — 基于 Karpathy 理念的 Qoder skill 实现
- `github.com/gavischneider/awesome-llm-wiki` — 该类项目的汇总列表（含 adamziel 的 agent-skills 标准实现）

## 3. 通用 Agent 记忆层（低一层的通用框架，非代码库知识管理）

- **mem0** — 抽取事实的记忆 SDK（Apache-2.0），最流行的即插即用记忆层
- **Letta (MemGPT)** — 带记忆管理的 Agent 框架
- **Zep** — 长期记忆服务（Graphiti 时序知识图谱）
- **Cognee** — 知识图谱 + 向量双模记忆

## 与我们的差异点

| 维度 | TencentDB Agent Memory | CodeWiki |
|---|---|---|
| 代码库原生 | CodeGraph 偏向调用关系图 | 面向 Agent 阅读的 `repowiki` 架构文档 + OKF |
| 知识确认 | 偏自动沉淀 | **显式确认闸门**（draft → confirm） |
| 任务记忆 | 团队级共享 | 任务级有界记忆 + 压缩归档（ADR-0001/0002） |
| 对话蒸馏 | 异步提取 | 三态 Mode A/B/C，无状态工具 + LLM 外置 |

**结论**：最值得盯防/借鉴的是 **TencentDB Agent Memory**（同赛道、热度极高、多 Agent 团队记忆定位几乎重合）；**LLM Wiki 家族**是理念源头（可用作 README/对外表述的类比）；mem0/Letta 那批是通用记忆中间件，定位不同但设计可参考。

需要我深入扒一下 TencentDB Agent Memory 的仓库结构或架构设计，跟 CodeWiki 做逐点对比吗？另外蒸馏 worker 正在后台补蒸馏「产品维护」任务的积压，完成后我会把待确认的草稿笔记清单带给你。
user: <question>是否关联到某个进行中的任务？</question>
<answers>
关联已有任务：产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-worker</from>
<summary>Message from distill-worker</summary>
<content>
「产品维护」补蒸馏完成（Mode C，task_id=产品维护）。

【蒸馏概况】
- 蒸馏对话数：1 条（conv-user_command-commands-codewiki-蒸馏对话提取记忆和经验-把已采集的对话（repowiki，186 turn，33KB）
- 该 raw 之前已被蒸馏过一次（已存在 2 条 stable 笔记且用户确认过），本次为补充蒸馏
- 新建笔记：2 条（draft，待确认）
- 更新笔记：1 条（并入已有 stable 笔记，补充 hook 硬注入决策）
- 去重抑制：1 条（schema.yaml 阈值配置笔记自动抑制，已有同主题笔记）
- 去重跳过：1 条（备份机制笔记，已有 stable 笔记更权威）
- 落盘任务记忆：6 条（memories_written=6，直写 repowiki/tasks/产品维护/memories.md，ADR-0002 无需确认）
- raw 已归档清理（archived_raw=conversations/conv-...-9477de.md）

【待确认草稿清单（建议在停顿点向用户展示，confirm_note 确认后才正式落盘）】
1. 「MCP 参数长度受限时蒸馏 submit 走文件侧通道：Python 脚本直接调 handle_distill_conversation」（workaround）
   → repowiki/notes/2026-08-25-mcp-参数长度受限时蒸馏-submit-走文件侧通道python-脚本直接调-handle-distill-conve.md
   要点：蒸馏 JSON 超 MCP 参数限制时写入临时文件，用 Python 脚本直接调 handle_distill_conversation 绕过。
2. 「蒸馏时无知识密度的对话也提交空结果，否则 raw 无法归档清理」（architecture）
   → repowiki/notes/2026-08-25-蒸馏时无知识密度的对话也提交空结果否则-raw-无法归档清理.md
   要点：对无知识密度对话也应提交空蒸馏结果，触发工具归档路径清空 raw 暂存区。
3. 「Team Doctrine 不自动注入上下文：SessionStart hook 硬注入 additionalContext」（architecture，已 update 进已有笔记）
   → repowiki/notes/2026-08-25-doctrine-不会自动注入-agent-上下文唯一通道是-query-wikimodeoverview.md
   要点：doctrine 原仅 query_wiki(mode='overview') 可注入；现 SessionStart hook 已通过 _load_doctrine 硬注入 additionalContext（跳过 frontmatter、缺失/超 20KB 降级；codewiki/hooks + .codebuddy/hooks + .qoder/hooks 三副本同步，测试 6 passed）。建议向用户确认该更新。

【任务记忆已落盘（可作上下文）】蒸馏闭环完成（23 对话→19 笔记确认→6 场景块聚合）；doctrine 阈值改由 schema.yaml conventions.aggregation 覆盖（25）；备份机制已移除（.backup 删除、索引重建 total_pages 46→45）；SessionStart hook 硬注入 doctrine；doctrine.md 已 confirm stable；后续 notes_since_last_doctrine 达 25 需刷新 doctrine。

未执行 confirm_note / reject_note（属主 Agent 与用户评审环节）。
</content>
</teammate-message>
</additional_input>
assistant: 蒸馏 worker 已汇报完成。我先确认绑定状态并拉取蒸馏后的最新任务上下文。
assistant: 任务绑定已确认，蒸馏积压已清零（`pending_raw_count=0`）。现在向你展示蒸馏 worker 产出的待确认草稿。

先让蒸馏 worker 收工：
assistant: 补蒸馏完成，蒸馏 worker 已收工。以下是本次蒸馏产出的**待确认草稿**（确认后才正式落盘）：

## 蒸馏汇报（1 条 186-turn 对话，产品维护任务）

**新建草稿笔记（2 条，draft）：**

1. **`MCP 参数长度受限时蒸馏 submit 走文件侧通道：Python 脚本直接调 handle_distill_conversation`**（workaround）
   - 蒸馏 JSON 超 MCP 参数限制时写入临时文件，绕过 MCP 通道直接调用 handler

2. **`蒸馏时无知识密度的对话也提交空结果，否则 raw 无法归档清理`**（architecture）
   - 无知识密度的对话也应提交空蒸馏结果，触发工具归档路径清空 raw 暂存区

**更新已有笔记（1 条）：**
3. **Team Doctrine 不自动注入 Agent 上下文：SessionStart hook 硬注入 additionalContext**（并入已有 stable 笔记）
   - doctrine 原仅 `query_wiki(mode='overview')` 可注入；现 SessionStart hook 通过 `_load_doctrine` 硬注入 additionalContext（跳过 frontmatter、缺失/超 20KB 降级；三份 hook 副本同步，测试 6 passed）

**其他：** 去重抑制 1 条（已有同主题）、去重跳过 1 条（已有 stable 更权威）；**6 条任务记忆已直写落盘**（ADR-0002 无需确认）；raw 已归档清理。

---

另外注意到 `compaction_due=true`（任务记忆已达 44 条，超 40 条压缩阈值）——记忆压缩走两段式无状态流程，需要你确认后我再执行。

请确认：
- 上述 **2 条新草稿 + 1 条更新** 是否确认落盘（`confirm_note`）？
- 是否顺带执行 **`compact_task_memories`** 压缩过期记忆？
user: <question>是否关联到某个进行中的任务？</question>
<answers>
关联已有任务：产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-worker</from>
<summary>Message from distill-worker</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1787589606242","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"distill-worker","timestamp":"2026-08-24T16:40:07.671Z"}
</content>
</teammate-message>
</additional_input>
assistant: 任务关联确认：已绑定「产品维护」，蒸馏 worker 已收工并清理完毕。

当前状态：
- **蒸馏积压已清零**（`pending_raw_count=0`），6 条任务记忆已直写落盘，2 条新草稿 + 1 条更新等待确认
- **记忆压缩待定**：`compaction_due=true`（44 条记忆超 40 条阈值），需要你确认后执行 `compact_task_memories`

你还没有对上面的确认问题表态。请回复：
- **确认** → 我执行 `confirm_note` 落盘 2 条草稿 + 1 条更新
- **拒绝** → 我执行 `reject_note` 丢弃草稿
- 记忆压缩是否一并执行？

另外，之前调研 GitHub 类似项目时提到可以深扒 **TencentDB Agent Memory** 的架构与 CodeWiki 逐点对比，需要的话随时说。
user: 确认，记忆压缩一并执行
assistant: 好的，我执行「确认落盘 + 记忆压缩」。先获取相关工具参数并确认笔记状态。
assistant: 用户已确认。我先读取相关笔记确认状态，并同时发起记忆压缩的 prepare 阶段。
assistant: 笔记状态确认：2 条新草稿（workaround + architecture）待确认；doctrine 那条已是 `stable` 且已含 hook 硬注入决策（此前已确认过）。现在执行确认落盘 + 记忆压缩提交。
assistant: 全部完成。汇总如下：

## 执行结果

**草稿确认（3 条全部落盘）**
- ✅ `MCP 参数长度受限时蒸馏 submit 走文件侧通道`（workaround）→ `stable`，verified by human:wangbao
- ✅ `蒸馏时无知识密度的对话也提交空结果`（architecture）→ `stable`，verified by human:wangbao
- ✅ `doctrine 不自动注入 Agent 上下文`（architecture）→ 该笔记此前已是 `stable`，蒸馏 worker 已将 hook 硬注入决策 update 进笔记内容

**记忆压缩**
- ✅ `compact_task_memories`：压缩 **24** 条早期记忆 → 保留最近 **20** 条全文，原文归档至 `memories-archive.md`（append-only 可回溯），`memories_total` 44 → 20，`compaction_due` 已解除

## 当前任务「产品维护」状态

- 蒸馏积压清零，任务记忆 20 条 + 压缩归档，6 条新记忆已直写
- 新增 3 条 stable 笔记（含 1 条更新），均带 `task_id` 关联
- 之前关于 GitHub 类似项目的调研结论已给出（重点盯 **TencentDB Agent Memory**、**LLM Wiki 家族**）

需要的话我可以继续深扒 TencentDB Agent Memory 的架构做逐点对比，或执行 `lint_wiki` 验证压缩后 Wiki 健康度。
