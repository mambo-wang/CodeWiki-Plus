---
name: codewiki-add-workspace-repo
description: "按克隆 URL 把业务代码仓库登记进已初始化的 harness 工作区：目录名自动取仓库名，事务式同步 bootstrap.sh/ps1 登记表、.gitignore、repo-map.md，并默认克隆。重复登记同名同 URL 是空操作。"
disable-model-invocation: true
---

# 登记业务仓到多仓工作区

按克隆 URL 把业务代码仓库登记进已初始化的 harness 工作区：目录名自动取仓库名，事务式同步 bootstrap.sh/ps1 登记表、.gitignore、repo-map.md，并默认克隆。重复登记同名同 URL 是空操作。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="add-workspace-repo", arguments={"workspace_path": ".", "url": "<url>"})
```

可选开关参数（默认值即上述调用；用户调用本技能时附带的相关意愿，先映射进 arguments 再调用 get_prompt，不要丢弃）：
- clone：默认 true；用户明确表示只登记不克隆时传 "false"

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能是手动触发入口（disable-model-invocation: true），不占常驻上下文；由用户显式调用 /codewiki-add-workspace-repo 触发。
