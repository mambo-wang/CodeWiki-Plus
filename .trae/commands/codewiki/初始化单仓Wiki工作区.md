# 初始化单仓Wiki工作区

零配置初始化：创建目录结构、拷贝带注释的 schema.yaml 模板、写入 AGENTS.md（含使用建议和自我反思协议），并默认启用任务管理接线（SessionStart/SessionEnd Hook + AGENTS.md 任务引导段）与编译宿主命令文件——初始化一次性把必要配置做好。在开始任何 Wiki 生成或知识管理之前执行一次。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="init-wiki", arguments={"repo_path": "."})
```

可选开关参数（默认值即上述调用；用户调用命令时附带的相关意愿，先映射进 arguments 再调用 get_prompt，不要丢弃）：
- enable_task_management：默认启用任务管理接线；用户明确表示不启用任务管理（如回答「否」/「不要」）时传 "false"
- capture：默认 on；用户明确表示关闭对话采集时传 "off"

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
