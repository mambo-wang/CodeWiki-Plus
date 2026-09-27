# 更新单仓代码 Wiki

检测代码变更并增量更新受影响的 Wiki 模块文档

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="incremental-update", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
