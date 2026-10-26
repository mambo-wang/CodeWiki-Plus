---
name: codewiki-search-wiki
description: "需要检索 Wiki 知识库时使用：编码前查模块文档与架构约定、做决策前查已有 decision 笔记、改文件前查该文件的历史教训。策略指引：BM25 搜索、图谱扩展、深度阅读。"
# model-invocable
---

# 知识库搜索

需要检索 Wiki 知识库时使用：编码前查模块文档与架构约定、做决策前查已有 decision 笔记、改文件前查该文件的历史教训。策略指引：BM25 搜索、图谱扩展、深度阅读。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="search-wiki", arguments={"query": "<query>"})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-search-wiki 触发。
