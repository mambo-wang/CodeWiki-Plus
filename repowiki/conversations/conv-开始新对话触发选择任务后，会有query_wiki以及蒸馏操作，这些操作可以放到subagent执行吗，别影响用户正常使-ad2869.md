---
type: Conversation
title: "conversation 20260823T081059Z"
status: distilled
stale_after: 2026-11-21
generated: { by: codewiki/5.3.0, at: 2026-08-23T08:10:59Z }
captured_at: "2026-08-23T08:10:59Z"
content_hash: "sha256:d70c2d1bf7db80907287c2c469414dd1f19427e3c73deaf9c41488594f05fa09"
friction_score: 10
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=8"
keep_raw: false
link_to: ""
source_session: "6da96ff5cda94f1aa96ab7e33863a877"
task_id: "产品维护"
turn_count: 111
---

# Conversation Transcript

user: 开始新对话触发选择任务后，会有query_wiki以及蒸馏操作，这些操作可以放到subagent执行吗，别影响用户正常使用
user: <question>本会话是否关联一个任务？（跨会话任务记忆，关联后本会话采集的对话会自动带上 task_id）</question>
<answers>
产品维护(task_id: 产品维护)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 任务已绑定。检测到本任务有 2 条未蒸馏历史对话，先按流程补蒸馏，再回答你的问题。
assistant: 逐条提取知识。先检查已有笔记是否已覆盖「hook 支持范围」相关主题，避免重复提取。
assistant: 已确认没有重复笔记覆盖「hook 支持范围」主题。现在提交蒸馏结果。
assistant: JSON 参数需为合法字符串，重新压缩格式提交。
assistant: 工具需要 object 而非字符串，改用对象传参。
assistant: 工具要求 `arguments` 是 JSON 字符串。我直接传入字符串化的对象。
assistant: 让我重新查看工具的确切参数结构。
assistant: distilled 需为对象类型。将整个参数压缩为一行合法 JSON 字符串重新提交。
assistant: 让我先用最小对象测试 `submit` 参数格式，排除内容问题。
assistant: 明白了：`distilled` 的每个 value 可传 JSON 字符串。改用 value 为 JSON 字符串的形式提交。
assistant: 两条对话蒸馏完成。现在有一条草稿笔记与已有笔记产生冲突，读取候选笔记判断是否重复。
assistant: 候选笔记主题是「任务绑定维度决策」，与草稿「hook 支持范围」是不同知识，无实质重叠。确认 `store` 强制创建。
assistant: 笔记已入库。重新拉取任务上下文注入最新状态。
assistant: 任务上下文已拉取。先向用户展示补蒸馏产出的待确认项，同时并行查看相关实现代码来回答核心问题。
assistant: 现在查看蒸馏与任务上下文实现的细节，确认异步/后台能力。
assistant: 查看项目中是否已有 subagent 相关的讨论或实现，以及 query_wiki 的用法。
assistant: 查看相关设计文档中关于 subagent/后台执行的描述。
assistant: 让我查看会话开始时的任务引导注入实现，确认 query_wiki 与蒸馏在引导流程中的位置。
assistant: 让我查一下是否有关于「subagent 执行蒸馏」的已有讨论或笔记。
assistant: 让我看下 `task-workflow` 与 `distill-conversations` 这两个 MCP prompt 的完整内容，了解当前的引导设计。
assistant: 让我确认 hook 注入的引导内容与相关设计文档，同时查 CodeBuddy 的 subagent 能力文档。
assistant: 让我查 CodeBuddy 的 Subagents 与 MCP 权限文档，并看项目里是否有 subagent 蒸馏的相关设计。
assistant: 让我确认项目里是否已有 subagent 定义文件。
assistant: 让我看下现有的 settings.json 和 sessionStart 补蒸馏注入方案的设计文档。
assistant: 我已经完整了解了当前机制。回答你的问题：

## 结论：可以，而且设计上本来就是为 subagent/后台准备的

`distill_conversation` 的设计文档里明确写有三种模式，其中 **Mode A（subagent 注入 `llm` 回调内联蒸馏）** 就是服务端 subagent 形态，**Mode C（prepare → 提取 → submit）** 可以完全由 subagent 走纯 MCP JSON。CodeBuddy 的 subagent 也支持 **`Tools MCP` 字段**（可为 subagent 单独授权 codewiki MCP server）。

## 当前真正的阻塞点

问题不在工具层，而在 **hook 注入的引导指令文本**（`task_session_start.py` 的 `_build_message`）写死了"硬性执行顺序"：

```
弹框 → 绑定 → get_task_context → 补蒸馏（prepare→逐条read_file→submit→重拉→展示确认）
全部完成后，才允许回答用户提问
```

这条指令要求**主 Agent 自己**逐条 read_file + 提取 + submit，全部做完才响应用户。所以：
- 蒸馏重活阻塞在用户提问之前，用户干等
- 主 Agent 上下文被 raw 原文占满（虽然用了 file-side-channel 逐条释放，但过程仍占主上下文）

## 落地方案（改 3 处引导即可）

1. **hook 指令文本**：把"补蒸馏必须在回答前完成"改为两段式——
   - 绑定 + `get_task_context` 后**立即开始响应用户**
   - 补蒸馏委托给「蒸馏 subagent」（spawn 一个授权了 codewiki MCP 的 subagent，走 Mode C prepare→submit），主 Agent 不读 raw 原文、不占上下文
   - 蒸馏结果在**自然停顿点**（任务告一段落/用户空闲时）展示待确认项，确认闸门不变

2. **AGENTS.md 任务段 + `prompts.py` 的 `_prompt_task_workflow`**：同步这个"委托 subagent"的新流程措辞

3. **新建 subagent 定义**：`.codebuddy/agents/` 下建一个"蒸馏 worker"（`Tools MCP: codewiki` 授权，agentic 模式），主 Agent 用 Task 工具 spawn 它

## 关键设计约束（要保持）

- 确认闸门不变：subagent 产出的是 draft 笔记 + pending 记忆，**确认前只读参考**，仍走 `confirm_note` / `confirm_task_memories`
- 若用户明确表示紧急，可先答复、会话结束前完成补蒸馏——这个豁免逻辑保留
- subagent 蒸馏时 `task_id` 过滤照常生效，不会蒸馏别的任务

需要我把这套改动落地吗？（涉及 `task_session_start.py` 双副本、AGENTS.md、prompts.py、新建 subagent 定义文件，以及相应测试）
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 开始新对话触发选择任务后，会有query_wiki以及蒸馏操作，这些操作可以放到subagent执行吗，别影响用户正常使用
- <question_answer> <questions> <question_item id="q-0"> <question>本会话是否关联一个任务？（跨会话任务记忆，关联后本会话采集的对话会自动带上 task_id）</question> <answers> 产品维护(task_id: 产品维护) </answers> </question_item> </questions> </question_answer>

Earlier assistant notes (truncated):
- 笔记已入库。重新拉取任务上下文注入最新状态。
- 任务上下文已拉取。先向用户展示补蒸馏产出的待确认项，同时并行查看相关实现代码来回答核心问题。
- 现在查看蒸馏与任务上下文实现的细节，确认异步/后台能力。
- 查看项目中是否已有 subagent 相关的讨论或实现，以及 query_wiki 的用法。
- 查看相关设计文档中关于 subagent/后台执行的描述。
- 让我查看会话开始时的任务引导注入实现，确认 query_wiki 与蒸馏在引导流程中的位置。
- 让我查一下是否有关于「subagent 执行蒸馏」的已有讨论或笔记。
- 让我看下 `task-workflow` 与 `distill-conversations` 这两个 MCP prompt 的完整内容，了解当前的引导设计。

Tools used before this summary: mcp_call_tool × 14, search_content × 10, read_file × 9, mcp_get_tool_description × 3, search_file × 2, ask_followup_question × 1, list_dir × 1
</cb_summary>

开始修改
assistant: 收到，开始落地。先并行读取需要修改的文件，确认现状。
assistant: 现在读取 hook 脚本（源副本 + 项目副本）与相关测试文件。
assistant: 现在需要确认 subagent 定义格式和现有测试内容，并行获取。
assistant: 现在我了解全部现状。先确认 `.codebuddy/hooks/` 副本是否存在，以及 `prompts.py` 中相关段落的具体内容。
assistant: 现在读取项目副本 hook 和 prompts.py 中需要修改的完整段落。
assistant: 现在我对所有需要修改的文件都有了完整了解。开始落地方案：

**修改点：**
1. `codewiki/hooks/task_session_start.py`（源）+ `.codebuddy/hooks/task_session_start.py`（项目副本）— 补蒸馏改为"委托 subagent，不阻塞回答"
2. `codewiki/mcp/prompts.py` — `_TASK_MEMORY_AGENTS_SECTION` + `_prompt_task_workflow` 同步措辞
3. `AGENTS.md` — 任务段同步
4. 新建 `.codebuddy/agents/distill-worker.md` — 蒸馏 worker subagent（授权 codewiki MCP）
5. `tests/test_task_session_start.py` — 更新断言

先改 hook 源副本：
assistant: 现在改补蒸馏段，委托 subagent 执行：
assistant: 现在读取 hook 当前完整内容，确认没有遗漏其他提到"补蒸馏阻塞"的措辞（如 friction hint）。
assistant: 修改 friction hint 措辞，同步委托 subagent 语义：
assistant: 现在将同样的修改同步到项目副本 `.codebuddy/hooks/task_session_start.py`：
assistant: 确认两个副本一致，并读取 prompts.py 与测试文件中需要修改的段落：
assistant: 现在读取 prompts.py 中需要修改的两个段落的具体内容：
assistant: 现在查看 `_prompt_task_workflow` 中补蒸馏的描述：
assistant: 现在修改 `prompts.py` 的两处补蒸馏描述。先改 `_TASK_MEMORY_AGENTS_SECTION`：
assistant: 现在改 `_prompt_task_workflow` 中的补蒸馏步骤：
assistant: 现在同步 AGENTS.md 中的任务段：
assistant: 现在创建蒸馏 worker subagent 定义。先确认 CodeBuddy subagent 定义格式：
assistant: 项目中没有现成 subagent 定义，重新获取 CodeBuddy subagent 定义格式文档：
assistant: 格式已确认。现在创建蒸馏 worker subagent 定义文件：
assistant: 现在更新测试，新增 subagent 委托相关的断言：
assistant: 检查测试文件其他断言是否引用旧措辞，以及 hook 其他部分是否还有需要同步的提示文本：
assistant: 测试已同步。现在检查项目其他文档是否引用旧措辞（如 team-memory-hook.md、其他测试、README）：
assistant: README.md 中还有旧措辞需要同步。更新：
assistant: 检查其他引用旧措辞的文档与测试：
assistant: team-memory-hook.md 路径不对，查找它：
assistant: docs/team-memory-hook.md 是接线文档，检查其中是否有需要同步的工作流描述：
assistant: 文档描述已与新模式兼容，无需改动。现在运行测试验证：
assistant: pyproject 中的 addopts 带了 cov 参数但未安装 pytest-cov，覆盖 addopts 重跑：
assistant: 测试通过。运行 hooks 相关的其他测试确保无回归：
assistant: 测试 `test_hook_friction_hint_for_high_score` 断言旧的 friction hint 文案。读取并更新：
assistant: 全部 47 个测试通过。检查 lint 与是否有其他遗漏：
assistant: lint 干净。最后确认两个 hook 副本一致并查看整体改动：
assistant: 改动完成，双副本一致，所有测试通过（47 passed）。

## 落地总结：蒸馏/检索委托 subagent，不再阻塞用户

**核心变更——补蒸馏从"主 Agent 回答前硬性执行"改为"委托 subagent 后台执行"：**

1. **`codewiki/hooks/task_session_start.py` + `.codebuddy/hooks/task_session_start.py`**（双副本同步，22 行改动）
   - 硬性顺序只剩：弹框 → 绑定 → `get_task_context`，完成后**立即响应用户**
   - 补蒸馏段改为：spawn「蒸馏 worker」subagent 走 Mode C（prepare → 逐条 read_file → submit），主 Agent 不读 raw 原文、不占上下文
   - 展示待确认项移到**自然停顿点**（任务告一段落/用户空闲）
   - friction hint 同步为"委托蒸馏 worker subagent（不阻塞本次工作）"

2. **`codewiki/mcp/prompts.py`**：`_TASK_MEMORY_AGENTS_SECTION` + `_prompt_task_workflow` 同步新流程措辞（13 行）

3. **`AGENTS.md` 任务段 + `README.md`**：同步"委托 subagent，不阻塞"语义

4. **新建 `.codebuddy/agents/distill-worker.md`**：蒸馏专用 subagent，授权 `ReadFile` + `toolsMCP: codewiki`，agentic 模式可自动运行；明确约束——只蒸馏、不 confirm/reject、不碰任务外文件、错误逐条跳过并汇报

5. **测试更新**：`test_task_session_start.py` 新增 4 条断言（蒸馏 worker / distill-worker.md / 不阻塞回答 / 自然停顿点），`test_friction.py` friction hint 断言兼容新文案，全部通过

**关键设计约束保持不变：**
- 确认闸门不变：subagent 产出仍是 draft 笔记 + pending 记忆，`confirm_note` / `confirm_task_memories` 确认前只读参考
- 紧急豁免保留：用户明确紧急时可先答复，蒸馏结果在会话结束前展示确认即可
- 只蒸馏当前任务（`task_id` 过滤由 prepare 保证）

一个待验证点：`distill-worker.md` 的 frontmatter（`toolsMCP` 字段名、agentic 模式下 Task 工具是否能直接 spawn）依赖 IDE 对 subagent 定义的解析，建议下次新会话观察 hook 是否成功把蒸馏委托出去；如果 IDE 解析方式有差异，只需调整该文件的 frontmatter 字段名即可，不影响其他改动。
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 开始修改

Earlier assistant notes (truncated):
- 现在需要确认 subagent 定义格式和现有测试内容，并行获取。
- 现在我了解全部现状。先确认 `.codebuddy/hooks/` 副本是否存在，以及 `prompts.py` 中相关段落的具体内容。
- 现在读取项目副本 hook 和 prompts.py 中需要修改的完整段落。
- 现在我对所有需要修改的文件都有了完整了解。开始落地方案：  **修改点：** 1. `codewiki/hooks/task_session_start.py`（源）+ `.codebuddy/hooks/task_session_start.py`（项目副本）— 补蒸馏改为"委托 subagent，不阻塞回答" 2. `codewiki/mcp/prompts.py` — `_TASK_MEMORY_AGENTS_SECTION` + `_prompt_task_workflow` 同步措辞 3. `AGENTS.md` — 任务段同步 4. 新建 `.codebuddy/agents/distill-worker.md` — 蒸馏 worker subagent（授权 codewiki MCP） 5. `tests/test_task_session_start.py` — 更新断言  先改 hook 源副本：
- 现在改补蒸馏段，委托 subagent 执行：
- 现在读取 hook 当前完整内容，确认没有遗漏其他提到"补蒸馏阻塞"的措辞（如 friction hint）。
- 修改 friction hint 措辞，同步委托 subagent 语义：
- 现在将同样的修改同步到项目副本 `.codebuddy/hooks/task_session_start.py`：

Tools used before this summary: read_file × 8, replace_in_file × 6, list_dir × 2, search_content × 2, search_file × 1, web_fetch × 1
</cb_summary>

写一篇文档详细介绍subagent机制，讲讲它的好处（比如节省上下文），可以拿我们对于刚刚subagent的创建和使用举例
assistant: 按照任务关联流程，先弹出任务关联选择框：
user: <question>本会话要关联哪个任务？（本次任务是撰写 subagent 机制介绍文档）</question>
<answers>
产品维护(绑定到「产品维护」任务（task_id=产品维护）)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 用户选择了「产品维护」任务。现在建立绑定并拉取任务上下文：
assistant: 需要提供仓库路径，重新调用：
assistant: 任务「产品维护」绑定成功，上下文已拉取（1 条积压 raw：关于"开始新对话后的 query_wiki 和蒸馏操作能否放 subagent 执行"——正是本次 subagent 机制的背景）。

现在并行处理：① 后台 spawn 蒸馏 worker 补蒸馏（不阻塞回答）；② 读取我们刚创建的 subagent 定义和文档目录，为写文档收集素材。
assistant: 蒸馏 worker 已在后台执行。现在收集文档素材——查看 `docs/articles/` 文章风格和 `prompts.py` 中 subagent 相关描述：
assistant: 现在获取 CodeBuddy 官方 subagent 机制文档和项目内 agent 文档，确保文章内容准确：
assistant: 概述页指向 Subagents 专题页，继续获取细节：
assistant: 已获取官方 Subagents 文档。现在读取用户最初提出该需求的对话原文，以及 hook 中 spawn subagent 的实现段落，确保示例部分准确：
assistant: 素材齐了。先看一下现有系列文章的风格，保持文档一致性：
assistant: 素材齐全。现在撰写文档：
assistant: 文档已写好。现在拉取任务上下文，看看后台蒸馏 worker 的产出：
assistant: 文档已完成，当前是自然停顿点。后台蒸馏 worker 上次执行似乎没有生效（`pending_raw_count` 仍为 1），重新派发一次补蒸馏：
assistant: 蒸馏 worker 两次 spawn 均未实际执行工具调用（执行环境异常）。不再重复派发（避免循环），我直接在停顿点手动补蒸馏这条 raw。先获取 `distill_conversation` 参数说明：
assistant: 先执行 Mode C 的 prepare 阶段：
assistant: prepare 已就绪（1 条积压，内容我已完整读过）。执行 Mode C 的 submit 阶段提交提取结果：
assistant: 参数 JSON 结构有误，重新构造：
assistant: 提交成功，raw 已处理，但笔记触发了弱重复冲突。读取候选笔记判断去重策略：
assistant: 候选笔记是"IDE hook 同步采集+异步蒸馏"（已弃用/合并），与本次新笔记主题不同——本次是"主 Agent 会话启动时委托 subagent"的决策。采用 `store` 强制创建：
assistant: 蒸馏完成，笔记已落盘，raw 已归档。现在拉取待确认记忆清单，向用户展示：
assistant: 文档已写好，补蒸馏也顺手完成了。汇报一下：

## 文档已完成

**`docs/articles/CodeWiki-Plus系列7：Subagent机制详解-上下文隔离与专业化分工.md`**

内容结构：
1. **subagent 是什么**——与主 Agent 的职责对比（项目经理 vs 外包团队）
2. **如何定义**——存储位置（project/user 级）、两种模式（agentic/manual）、frontmatter 字段总表
3. **主 Agent 如何调用**——agentic 自动触发 + Task 工具显式派活
4. **五大好处**——上下文隔离（核心）、不阻塞主流程、专业化分工、权限控制、跨项目复用
5. **实战案例**——用我们刚创建的 `distill-worker` 完整举例：
   - 需求背景：你在历史对话里提的那句"这些操作可以放到 subagent 执行吗，别影响用户正常使用"
   - 创建：`distill-worker.md` 定义逐字段解读 + 完整源码
   - 使用：SessionStart hook → Task spawn → Mode C 蒸馏流程（含 Mermaid 时序图）
   - 好处落地对照 + 一个关键设计决策（评审闸门留在主 Agent）
6. **最佳实践 checklist** + 结语

文章以"上下文经济学"为主线：主 Agent 窗口有限、脏活无限，把"读得多、产出小"的活下沉到 subagent，窗口预算留给真正需要判断力的地方。

---

## 顺带完成的补蒸馏

后台蒸馏 worker 两次 spawn 均未实际执行（执行环境异常），我在停顿点手动走完 Mode C 流程：

- **已落盘 1 条笔记**：`repowiki/notes/2026-08-23-会话启动时的-query-wiki蒸馏等重操作委托-subagent-执行避免阻塞用户正常使用.md`（decision，priority 88），raw 已归档
- **5 条待确认记忆**（来自本任务的历史对话），需要你确认后才写入 `memories.md`：

| 来源 | 内容摘要 |
|------|---------|
| 文档质量审计对话 | 用户曾发起全量 Wiki 质量审计（lint_wiki）请求，被任务引导打断，尚未执行 |
| 文档质量审计对话 | 同上（另一条会话记录，5 步审计流程待续） |
| hook 机制对话 | hook 支持范围已写入 README「仅接线支持 CodeBuddy」，底层已做 CodeBuddy/Claude-Code 兼容解析 |
| 本次 subagent 对话 | "补蒸馏委托 subagent"决策已落地（distill-worker + hook/AGENTS/prompts 同步） |
| 本次 subagent 对话 | 已撰写系列7文档（即你刚看到的这篇） |

其中 **前两条** 提醒你：之前发起的**文档质量审计任务还没执行**，需要的话可以现在继续。

需要我：
1. **确认以上 5 条记忆落盘**（`confirm_task_memories`）？
2. 还是先**继续文档质量审计**（lint_wiki）？
3. 或者直接结束，文档保持现状即可？
user: 确认记忆落盘
assistant: 用户确认落盘，确认全部 5 条待确认记忆：
assistant: 5 条记忆已全部确认落盘到 `memories.md`，pending 区已清空。

## 本次会话成果汇总

**主任务（文档撰写）**
- `docs/articles/CodeWiki-Plus系列7：Subagent机制详解-上下文隔离与专业化分工.md` — 详细介绍 subagent 机制 + 蒸馏 worker 实践案例

**补蒸馏（任务记忆闭环）**
- 1 条 decision 笔记落盘：`repowiki/notes/2026-08-23-会话启动时的-query-wiki蒸馏等重操作委托-subagent-执行避免阻塞用户正常使用.md`
- 5 条任务记忆已确认写入 `memories.md`
- 对应 raw 已归档

另外提醒：`list_pending_memories` 里显示你之前发起过一次**文档质量审计**（lint_wiki 全量检查）被任务引导打断，尚未执行。需要现在继续吗？
user: 不用
assistant: 好的，文档质量审计先搁置。本次会话的任务（撰写 subagent 机制文档）已完成，相关笔记和记忆也已落盘。有需要随时找我。
user: @d:\repos\CodeWiki-CN\.codebuddy\agents\distill-worker.md  这个md在codewiki源码目录中应该保存，当设置hook的时候，把md拷贝过来
assistant: 用户要求：把 `distill-worker.md` 存到 CodeWiki 源码目录，并在设置 hook 时自动拷贝到 `.codebuddy/agents/`。先探索现有 hook 安装机制：
assistant: 现在了解 hook 安装机制。搜索所有涉及拷贝 hook 脚本的位置，以及打包配置：
assistant: 现在读取 distill-worker.md 完整内容、prompts.py 两处拷贝逻辑的上下文，以及相关测试：
assistant: 现在了解测试断言和包内是否已有 agents 目录：
assistant: 现在查看 `prompts.py` 中 `_prompt_init_wiki` 是否也有 hook 安装步骤，以及 `_prompt_team_memory_hook` 的完整定义：
assistant: 现在读取 `_prompt_init_wiki` 中任务管理启用段落，确认是否也有拷贝脚本的逻辑：
assistant: 我需要确认 `pyproject.toml` 的 package-data 配置和 `_prompt_team_memory_hook` 中拷贝段的完整上下文。重新读取：
assistant: 方案明确。执行三步：① 在 `codewiki/agents/` 存放源文件；② 修改两处 hook 启用 prompt 增加拷贝逻辑；③ `pyproject.toml` 打包声明。

先创建源码副本：
assistant: 源码副本已保存。现在修改两处 hook 启用 prompt，增加 `distill-worker.md` 的拷贝逻辑：
assistant: 现在修改第二处（`_prompt_team_memory_hook` 步骤 2A）：
assistant: 现在同步 2B 关闭步骤的说明（关闭时可保留也可删除 distill-worker.md），以及 `pyproject.toml` 打包声明。先看 2B 段落：
assistant: 现在更新 `pyproject.toml`，把 `agents/*.md` 加入打包声明：
assistant: 现在检查是否有测试或其他文档断言了这两处拷贝逻辑的文本（避免破坏测试）：
assistant: 测试不受影响。确认 `repowiki/team-memory-hook.md` 实际位置及 AGENTS.md 中是否也有拷贝描述：
assistant: 检查 `docs/team-memory-hook.md` 中是否有拷贝逻辑需要同步：
assistant: `docs/team-memory-hook.md` 是采集接线文档，不涉及拷贝逻辑，无需改。顺手把 `_prompt_init_wiki` 中步骤 2 的导语同步一下措辞：
assistant: 验证改动：编译检查 prompts.py，并运行相关测试：
assistant: 测试运行需要 pytest-cov，换用 `-p no:cacheprovider` 方式或直接 `--no-cov`：
assistant: `pyproject.toml` 的 addopts 强制了 `--cov`，但 pytest-cov 未安装。用 `-o addopts=''` 覆盖：
assistant: 4 个测试全部通过。现在读取 lints 确认无新错误：
assistant: 改动完成。最后确认源文件与项目内现有副本是否一致（源文件为权威版本）：
assistant: 项目内副本与源码副本内容一致，改动完整。总结本次修改：

## 已完成：distill-worker 源码化 + hook 安装时自动拷贝

**1. 源码副本（新文件）**
- `codewiki/agents/distill-worker.md` — 随 `codewiki` 包发布的权威版本，与项目内 `.codebuddy/agents/distill-worker.md` 内容一致

**2. hook 启用时自动拷贝（`codewiki/mcp/prompts.py`）**
- `_prompt_init_wiki`（init 流程）与 `_prompt_team_memory_hook`（步骤 2A）两处拷贝逻辑均已更新：
  - 创建 `.codebuddy/agents/` 目录
  - 从包内 `agents/distill-worker.md` 强制拷贝到目标项目 `.codebuddy/agents/distill-worker.md`
  - 校验命令增加 `assert` 确认 md 存在且以 `---` 开头
  - 回退逻辑（`CODEWIKI_HOME`）同步支持 agents 拷贝
- 步骤 2B（关闭）说明同步：`distill-worker.md` 可保留也可删除，重新启用自动补回

**3. 打包声明（`pyproject.toml`）**
- `package-data` 增加 `"agents/*.md"`，确保 pip 安装时 `.md` 文件随包发布（否则非 `.py` 文件默认不打包）

**验证**
- `prompts.py` 语法 OK
- `tests/test_task_session_start.py` 4 个测试全部通过
- 无 lint 错误

现在机制是：**源码只在 `codewiki/agents/` 存一份，任何项目启用 hook（init 或 team-memory-hook）时自动拷贝到目标项目的 `.codebuddy/agents/`**，和 `hooks/*.py` 的安装方式完全对称。

需要我把这条设计决策（"subagent 定义随包发布、hook 启用时拷贝"）沉淀为 Wiki 笔记吗？
