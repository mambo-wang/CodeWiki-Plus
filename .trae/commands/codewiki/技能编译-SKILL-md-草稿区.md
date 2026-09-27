# 技能编译（SKILL.md 草稿区）

把已确认知识（场景块 + stable 笔记 + 技能 open issues）编译为 SKILL.md 行为指令草稿（repowiki/skills/，两区制草稿区：进索引进 lint、不生效）：prepare 取候选素材/冲突预检/容量预警/写作规范 → Agent 撰写 → submit 校验落盘并写双向溯源。install/retire 为后续工单。适用于「生成技能」「把经验编成 SKILL」等场景。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="skill-creator", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
