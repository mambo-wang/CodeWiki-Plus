---
name: codewiki-promote-note
description: "wiki_stats 出现 promotion_candidates 候选、某条 stable 笔记被反复采纳，或用户要求把笔记转正时使用。把候选笔记去个人化重写为正式 wiki 页面：类型路由（pitfall/bug_fix/workaround → query，lesson/decision/architecture → concept）→ write_doc_file 写新页面（必须 draft 状态，写完提醒 confirm）→ edit_doc_file 回标原笔记 metadata.promoted_to。原笔记不删除不降级，保留作审计轨迹锚点。"
# model-invocable
---

# 笔记晋升为正式 wiki 页面

wiki_stats 出现 promotion_candidates 候选、某条 stable 笔记被反复采纳，或用户要求把笔记转正时使用。把候选笔记去个人化重写为正式 wiki 页面：类型路由（pitfall/bug_fix/workaround → query，lesson/decision/architecture → concept）→ write_doc_file 写新页面（必须 draft 状态，写完提醒 confirm）→ edit_doc_file 回标原笔记 metadata.promoted_to。原笔记不删除不降级，保留作审计轨迹锚点。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="promote-note", arguments={"note_file": "<note_file>", "repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-promote-note 触发。
