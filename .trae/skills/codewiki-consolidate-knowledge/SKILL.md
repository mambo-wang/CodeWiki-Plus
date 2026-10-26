---
name: codewiki-consolidate-knowledge
description: "lint_wiki 或 wiki_stats 提示 notes_since_last_consolidation 超阈值、出现 aggregation_hint，或用户要求「聚合笔记」时使用（执行前须先询问用户确认）。把已确认笔记聚合为 L2 工作方法场景块（wiki/scenarios/）：prepare 获取待聚合笔记与容量预警 → 撰写/更新场景块 → reject_note 退役被吸收笔记 → submit 记录溯源并归零计数器。"
# model-invocable
---

# 知识聚合（L2 场景块）

lint_wiki 或 wiki_stats 提示 notes_since_last_consolidation 超阈值、出现 aggregation_hint，或用户要求「聚合笔记」时使用（执行前须先询问用户确认）。把已确认笔记聚合为 L2 工作方法场景块（wiki/scenarios/）：prepare 获取待聚合笔记与容量预警 → 撰写/更新场景块 → reject_note 退役被吸收笔记 → submit 记录溯源并归零计数器。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="consolidate-knowledge", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-consolidate-knowledge 触发。
