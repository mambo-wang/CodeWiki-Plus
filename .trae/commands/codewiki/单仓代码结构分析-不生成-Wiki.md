# 单仓代码结构分析（不生成 Wiki）

仅解析代码结构、构建函数级调用图、查询依赖和评估修改影响范围，不生成任何 Wiki 文档。分析结果缓存在 SQLite 中，后续可随时继续生成 Wiki。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="code-analysis", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
