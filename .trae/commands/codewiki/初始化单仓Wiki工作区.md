# 初始化单仓Wiki工作区

零配置初始化：创建目录结构、拷贝带注释的 schema.yaml 模板、写入 AGENTS.md（含使用建议和自我反思协议）。在开始任何 Wiki 生成或知识管理之前执行一次。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="init-wiki", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
