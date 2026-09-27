# 初始化多仓WIKI工作区

把当前工作目录初始化（或重新同步）为多仓工作区：生成 bootstrap 克隆脚本、.gitignore、repo-map 导航骨架、AGENTS.md 工作区约定与产品级 repowiki。首次初始化必须先询问用户知识布局（colocated/centralized）再带 layout 调用，布局记录写入 repowiki/.meta/workspace.json；重跑零配置幂等——痕迹齐备时为 clone-only 接管（只补缺业务仓克隆，不触碰骨架与 AGENTS.md），骨架有缺失才补齐产物并强制刷新约定块。业务仓登记走 add_workspace_repo。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="init-workspace", arguments={"workspace_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
