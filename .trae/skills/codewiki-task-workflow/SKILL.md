---
name: codewiki-task-workflow
description: "用户表示「继续上一个任务」「接着上次的干」等跨会话延续工作，或需要创建/关联任务、按 task_id 检索任务上下文时使用。覆盖创建/关联任务、采集对话绑定 task_id、蒸馏时双轨产出笔记与任务记忆、按 task_id 检索与聚合。"
# model-invocable
---

# 任务记忆工作流

用户表示「继续上一个任务」「接着上次的干」等跨会话延续工作，或需要创建/关联任务、按 task_id 检索任务上下文时使用。覆盖创建/关联任务、采集对话绑定 task_id、蒸馏时双轨产出笔记与任务记忆、按 task_id 检索与聚合。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="task-workflow", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-task-workflow 触发。
