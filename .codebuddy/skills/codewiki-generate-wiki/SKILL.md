---
name: codewiki-generate-wiki
description: "完整的代码仓库 Wiki 生成流水线：分析→聚类→逐模块撰写→总览→质检→关闭会话"
disable-model-invocation: true
---

# 生成单仓代码 Wiki

完整的代码仓库 Wiki 生成流水线：分析→聚类→逐模块撰写→总览→质检→关闭会话

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="generate-wiki", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能是手动触发入口（disable-model-invocation: true），不占常驻上下文；由用户显式调用 /codewiki-generate-wiki 触发。
