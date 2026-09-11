---
type: Conversation
title: "conversation 20260911T010747Z"
status: distilled
stale_after: 2026-12-10
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:07:47Z }
captured_at: "2026-09-11T01:07:47Z"
content_hash: "sha256:c40523f88d73df46a5eae17baff95d282981d1cff50b8d5d22ba64a06e5238f0"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: ""
source_session: "a325cf319f544354ade874b17f19d8ad"
task_id: "技能提取"
turn_count: 14
---

# Conversation Transcript

user: 如何启用skill自动编译功能，是有环境变量控制吗？
assistant: [tool: ask_followup_question · {"questions": [{"question": "请先完成本次会话的「任务关联」（跨会话任务记忆）。请选择要关联的任务；若列表里没有想要的任务，可直接在弹框的输入框里输入新任务名称后回车。", "header": "任务关联", "options"…
user: <question>请先完成本次会话的「任务关联」（跨会话任务记忆）。请选择要关联的任务；若列表里没有想要的任务，可直接在弹框的输入框里输入新任务名称后回车。</question>
<answers>
技能提取
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"]]"}]

[tool: search_content · auto.?compile|自动编译|auto_compile|AUTO_COMPILE]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"a325cf319f544354ade874b17f19d8ad\",\"t…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"技能提取\",\"repo_path\":\"d:/repos/CodeWiki-CN\"}",…

[tool: search_content · CODEWIKI_[A-Z_]*SKILL|SKILL[A-Z_]*]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/src/skill_match.py", "offset": 230, "limit": 80}]

[tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py", "offset": 1290, "limit": 60}]

[tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/docs/skill-creator使用指南.md", "offset": 170, "limit": 60}]
assistant: [tool: search_content · CODEWIKI_[A-Z0-9_]+]

[tool: search_content · skill_hint|SKILL_HINT]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/_ide_hook.py", "offset": 380, "limit": 100}]
assistant: [tool: search_content · _ide_hook|install.hooks|install_hooks]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/cli/commands/install_hooks.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/hooks]
assistant: [tool: list_dir · {"target_directory": "d:/repos/CodeWiki-CN/codewiki/hooks"}]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/src/skill_match.py", "offset": 36, "limit": 25}]
assistant: ## 结论：没有「自动编译」，也没有控制它的环境变量 —— 这是有意设计

依据本次代码核对：**没有**任何 `CODEWIKI_SKILL_AUTO_COMPILE` 之类的开关，全仓 skill 相关逻辑里只有提示（hint），没有自动执行路径：

- `codewiki/src/skill_match.py:248` — `build_skill_hint` 的契约写明 "never compile, never install, never write"；产物只是一句 `（需你确认后执行；我不会自动编译）`（`skill_match.py:291`）
- `codewiki/mcp/prompts.py:1323` — skill-creator 提示词行为契约：「永不自动编译、永不自动 install；触发词出现先向用户确认再执行」
- `docs/skill-creator使用指南.md:202` — 三条提醒「只提示，绝不自动编译或安装」

对应团队信条里的「不自动蒸馏/聚合/刷新 Doctrine：触发永远显式」「确认闸门对等」。

## 现有的是三条自动**提醒**通道（不是自动编译）

| 通道 | 位置 | 触发条件 | 是否需开关 |
|---|---|---|---|
| UserPromptSubmit 匹配未安装草稿 | `codewiki/mcp/_ide_hook.py:389-432` | prompt 与 `status: draft` 技能 containment ≥0.5 且 prompt ≥8 token（`skill_match.py:47,51`） | 需 `install-hooks` 接线，命令已硬编码 `--enable`（`codewiki/cli/utils/ide_config.py:107`），**不用设环境变量** |
| L2 场景块像技能素材 | `codewiki/mcp/tools/note_consolidation.py:706-734` | 命令命中 ≥3（`DEFAULT_CMD_THRESHOLD`）且 ≥2 条笔记背书（`skill_match.py:56,60`） | 无开关，submit 返回里带 `skill_hint` |
| 蒸馏产出撞上草稿 | `codewiki/mcp/tools/distill_conversation.py:1846-1855` | 笔记标题命中草稿 | 无开关 |

## 你可能真正想找的那个环境变量

`CODEWIKI_TEAM_MEMORY_HOOK=1`（`codewiki/mcp/_ide_hook.py:71,470-479`）：它开的是**对话采集**总闸，不是编译。只有当你手工 `python -m codewiki.mcp._ide_hook` 时才需要它；走 `codewiki install-hooks` 接线的 wrapper 已经自带 `--enable`。

另一个容易混淆的：`CODEWIKI_RAW_TOOL_DETAIL`（`codewiki/src/tool_digest.py:145`）是采集**成功工具调用细节**的 kill switch（设 `0`/`off` 关闭）。它影响的是技能**素材质量**，跟自动编译无关——想让以后编译出的技能有完整步骤序列，反而要保证它是开的（默认开）。

## 想尽量省人工，可行的做法

1. 编译仍需显式调用：`skill_creator(mode="prepare", ...)` → 你写 → `submit` → 草稿落 `repowiki/skills/`；
2. `install` 后技能才进生效区 `.codebuddy/skills/`，之后**自动生效**（`docs/skill-creator使用指南.md:173`），不用每次提醒；
3. 若想让 Agent 见到 `skill_hint` 就主动推进，只能在你的指令/AGENTS.md 里写明「收到 skill_hint 时先问我是否编译」，工具侧不会替你点头；
4. 阈值（0.5 / 8 / 3 / 2）是代码常量，不是环境变量，要调只能改 `codewiki/src/skill_match.py`。

<!-- codewiki:referenced-docs: [] -->

顺便：本会话已绑定任务「技能提取」，该任务 `pending_raw_count=0`，无需补蒸馏。任务待办里仍挂着一条未完事项——`windows-python-release` 技能尚未 install（需重启 MCP server 让 registry 新 enum 生效后执行 `skill_creator(mode="install", name=windows-python-release)`），需要的话我可以接着处理。
