---
type: Conversation
title: "conversation 20260819T091155Z"
status: distilled
stale_after: 2026-11-17
generated: { by: codewiki/5.3.0, at: 2026-08-19T09:11:55Z }
captured_at: "2026-08-19T09:11:55Z"
content_hash: "sha256:0d96769e3b8c1ff5f0e5e1745a60febea506885cfa5e7490fbd77bcfece70fa4"
keep_raw: false
link_to: ""
source_session: "4525265355a94af4bfacaf7be3e6918b"
task_id: "产品维护"
turn_count: 7
---

# Conversation Transcript

user: @prompts.py:1294-1308  这个prompt是做什么用的
assistant: 我先处理「任务关联」流程，然后再回答你关于 `task-workflow` prompt 的问题。
user: <question>本次会话要关联哪个任务？</question>
<answers>
产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 任务绑定成功（`产品维护`），且 `pending_raw_count = 0`，无积压对话需补蒸馏。现在回答你的问题，我先读一下这个 prompt 的完整定义和它对应的内容。
assistant: `prompts.py:1294-1308` 这段是 MCP Server 里注册的一个 **Prompt 模板定义**（`Prompt` 对象），名为 `task-workflow`，标题「任务记忆工作流」。

## 它是什么

它是一个「工作流指引」型 prompt，通过 MCP 的 `prompts/list` / `prompts/get` 对外暴露。用户选中这段代码里定义的只是「元信息」（名称、标题、描述、入参），真正的指引正文在 `_prompt_task_workflow` 函数（`prompts.py:957`），由注册映射表在 `prompts.py:1349` 关联起来：

```1344:1351:codewiki/mcp/prompts.py
"workspace-analysis": _prompt_workspace_analysis,
"cross-service-trace": _prompt_cross_service_trace,
"ingest-note": _prompt_ingest_note,
"team-memory-hook": _prompt_team_memory_hook,
"distill-conversations": _prompt_distill_conversations,
"task-workflow": _prompt_task_workflow,
"consolidate-knowledge": _prompt_consolidate_knowledge,
```

## 它做什么用

它给 Agent 一份**跨会话任务记忆的完整 SOP**，对应项目里的「Task memory（任务记忆）」能力。触发场景是用户说「继续上一个任务」「接着做 XX 任务」「切换任务」等需要延续长线工作上下文的场合。

指引正文（`_prompt_task_workflow`）分四段：

1. **会话开始——关联任务（可选但推荐）**：`list_tasks` 列任务 → 用户选择关联或 `create_task` 新建 → `set_session_task` 建绑定 → `get_task_context` 拉上下文 → 若 `pending_raw_count > 0` 先补蒸馏。
2. **会话进行中**：采集对话带 `task_id`，蒸馏时 LLM 双轨产出 `notes`（通用经验）和 `memories`（任务进度，先进 pending 待确认）。
3. **会话结束**：`complete_task` / `delete_task`；进度记忆只由蒸馏产出并经 `confirm_task_memories` 确认，不许直调 `add_task_memory` 绕过评审闸门。
4. **检索与约束**：`query_wiki(task_id=...)` 按任务过滤；`task_id` 由标题 slugify 生成、不可变、无重命名。

它本身只带一个可选入参 `repo_path`（仓库根目录，默认当前目录）。

简单说：**这是把「任务记忆层」这套机制（task 的创建/关联/采集/蒸馏/确认/检索全流程）翻译成一份 Agent 可直接照做的操作指引**，与你项目根目录 `AGENTS.md` 里 `<!-- TEAM-MEMORY-TASK:START/END -->` 那段是同一套约定的两个载体——一个是静态文档，一个是 MCP 可查询的 prompt。
user: 好的明白了，其实不是给人用的，是给AI看的
assistant: 对，你的理解是对的。这类 prompt 本质是「给 AI 的可执行工作流指引」——正文里全是给 Agent 看的操作步骤、工具调用顺序、设计约束，而不是给人看的文档。

稍微精确一点说，它的触发链条是：

- **人**（或上层 Agent）通过 `prompts/list` 发现它、`prompts/get` 拉取；
- **AI** 拿到 `_prompt_task_workflow` 展开的正文后，照里面的步骤去执行。

所以它和 `AGENTS.md` 里那段 `TEAM-MEMORY-TASK` 的区别，不在于「人看 vs AI 看」，而在于**载体形态**：

| 载体 | 形态 | 用途 |
|------|------|------|
| `AGENTS.md` | 静态文档 | 每次会话自动注入到 AI 上下文，兜底常驻 |
| `task-workflow` prompt | MCP 可按需查询 | 需要时主动拉取，`repo_path` 等参数可动态注入 |

两者内容同源，只是分发方式不同：一个常驻、一个按需。
