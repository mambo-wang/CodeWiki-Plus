---
name: codewiki-skill-creator
description: "用户要求「生成技能」「把经验编成 SKILL」，或 skill_hint 提示某笔记反复被采纳适合编译时使用。把已确认知识（场景块 + stable 笔记 + 技能 open issues）编译为 SKILL.md 行为指令草稿（repowiki/skills/，两区制草稿区：进索引进 lint、不生效）：prepare 取候选素材/冲突预检/容量预警/写作规范 → Agent 撰写 → submit 校验落盘并写双向溯源。install/retire 为后续工单。"
# model-invocable
---

# 技能编译（SKILL.md 草稿区）

用户要求「生成技能」「把经验编成 SKILL」，或 skill_hint 提示某笔记反复被采纳适合编译时使用。把已确认知识（场景块 + stable 笔记 + 技能 open issues）编译为 SKILL.md 行为指令草稿（repowiki/skills/，两区制草稿区：进索引进 lint、不生效）：prepare 取候选素材/冲突预检/容量预警/写作规范 → Agent 撰写 → submit 校验落盘并写双向溯源。install/retire 为后续工单。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="skill-creator", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-skill-creator 触发。
