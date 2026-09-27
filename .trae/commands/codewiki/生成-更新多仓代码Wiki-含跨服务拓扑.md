# 生成/更新多仓代码Wiki（含跨服务拓扑）

扫描父目录下的多个 git 仓库，为每个生成独立 Wiki 并自动执行跨服务分析：RouteNode 匹配（HTTP+MQ，覆盖 Py/Java/JS/TS/Go）、Mermaid 服务拓扑图、基础设施扫描（docker-compose/.env/application.yml）。可搭配 codebase-memory-mcp 做语义级深度追踪。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="workspace-analysis", arguments={"workspace_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
