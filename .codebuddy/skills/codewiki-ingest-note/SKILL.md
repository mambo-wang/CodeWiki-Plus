---
name: codewiki-ingest-note
description: "完成重要决策、多步调试定位到根因、被用户纠正/吐槽、发现可复用模式后，需要把经验沉淀进知识库时使用。将设计决策、经验教训、架构 rationale、踩坑记录等归档为 8 种笔记类型，自动 BM25 索引，可通过 query_wiki 检索。"
# model-invocable
---

# 经验知识归档

完成重要决策、多步调试定位到根因、被用户纠正/吐槽、发现可复用模式后，需要把经验沉淀进知识库时使用。将设计决策、经验教训、架构 rationale、踩坑记录等归档为 8 种笔记类型，自动 BM25 索引，可通过 query_wiki 检索。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="ingest-note", arguments={"repo_path": ".", "note_type": "<note_type>"})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-ingest-note 触发。
