---
type: Conversation
title: "conversation 20260910T121420Z"
status: distilled
stale_after: 2026-12-09
generated: { by: codewiki/5.9.0, at: 2026-09-10T12:14:20Z }
captured_at: "2026-09-10T12:14:20Z"
content_hash: "sha256:974e4464f6cf672a9ddbc31749aad487bed7232146026e3d663105fff62c6162"
friction_score: 5
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=4"
keep_raw: false
link_to: ""
source_session: "92a50859e4b1421a88f9584d9d412b7f"
task_id: "产品维护"
turn_count: 34
---

# Conversation Transcript

user: 我发现sessionStart hook弹框选择任务列表的时候，经常会弹多个框，能不能限制只弹一个框，把所有进行中任务就在这只框里全部显示
assistant: [tool: ask_followup_question · {"questions": [{"question": "本会话要关联到哪个任务？", "options": ["CodeWiki 架构深化分析", "产品维护", "发版本", "技能提取", "统一知识存储层（KnowledgeStore 动词式门面）…
user: <question>本会话要关联到哪个任务？</question>
<answers>
产品维护
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"],[\"codewiki\",\"distill_conversati…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\": \"92a50859e4b1421a88f9584d9d412b7f\", \…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\": \"产品维护\", \"repo_path\": \"d:/repos/CodeWiki-CN\"…
assistant: [tool: search_file · task_session_start.py]

[tool: search_content · d:/repos/CodeWiki-CN]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/hooks/task_session_start.py"}]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/tests/test_task_session_start.py"}]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN]

[tool: search_content · d:/repos/CodeWiki-CN/AGENTS.md]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py]
assistant: [tool: search_content · d:/repos/CodeWiki-CN/.codebuddy/settings.json]

[tool: search_content · d:/repos/CodeWiki-CN/codewiki/mcp/ide_config.py]
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/.codebuddy/settings.json"}]
assistant: [tool: search_content · d:/repos/CodeWiki-CN]

[tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py", "offset": 1225, "limit": 40}]
assistant: 现在改 hook 注入文案（源副本），把「多框」改成「单框列全」。
assistant: Now 同步 AGENTS.md 标记块与三份 hook 副本。

[tool: execute_command · Copy-Item -Path "d:\repos\CodeWiki-CN\codewiki\hooks\task_session_start.py" -Destination "d:\repos\CodeWiki-CN\.codebuddy\hooks\task_s…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; python -m pytest tests/test_task_session_start.py tests/test_install_hooks.py -q 2>&1 | Select-Object -Last 2…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; $env:PYTHONUTF8='1'; '{"session_id":"92a50859e4b1421a88f9584d9d412b7f","cwd":"d:/repos/CodeWiki-CN","hook_eve…

[tool: execute_command · cd d:\repos\CodeWiki-CN; python -m pytest tests -q -k "prompt or i18n or task" 2>&1 | Select-Object -Last 15]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; $env:PYTHONUTF8='1'; $out = '{"session_id":"92a50859e4b1421a88f9584d9d412b7f","cwd":"d:/repos/CodeWiki-CN","h…
assistant: [tool: read_lints · {"paths": ["d:/repos/CodeWiki-CN/codewiki/hooks/task_session_start.py", "d:/repos/CodeWiki-CN/codewiki/mcp/prompts.py", "d:/repos/CodeWiki-…
assistant: [tool: read_file · {"filePath": "d:/repos/CodeWiki-CN/codewiki/hooks/task_session_start.py", "offset": 318, "limit": 30}]
assistant: 可以，已经改成「单框列全」。

## 根因（依据本次代码核对）

1. `ask_followup_question` 的 schema 写着 **options 2-4 个**，Agent 会照做把 9 个任务拆进多个 question 或分多次调用 → 多框。
2. 旧注入文案里有一条 `【新建任务两步弹框】`，明确要求"选择「新建任务」后**必须**再次调用弹框"，这是第二/第三个框的直接来源（`codewiki/hooks/task_session_start.py` 旧版 341-347 行）。

不是 hook 被注册了两次：`.codebuddy/settings.json:3-13` 只有一条 `SessionStart`（matcher `startup`）。

## 改动

**SessionStart 注入文案**（`codewiki/hooks/task_session_start.py:321-347`，已实测输出）：
- 只允许 **1 次** `ask_followup_question`，`questions` 里只放 **1 个 question**（标题「任务关联」，`multiSelect=false`）
- 这一个 question 的 options 一次性列全：全部进行中任务 + 「新建任务…（在输入框直接输入名称）」+「跳过」
- 显式覆盖 schema 建议：**严禁**因「2-4 options」拆成多 question 或多次调用
- 「新建任务两步弹框」降级为兜底：只有选了「新建任务…」却没给名字时才允许弹第二次；用户直接输入的名字（自由文本）直接 `create_task`，不再弹框

**同步四处**（避免副本漂移）：`.codebuddy/hooks/`、`.qoder/hooks/` 已重拷贝；`codewiki/mcp/prompts.py:47-51`（AGENTS.md 注入模板）与 `_prompt_task_workflow`（1239 起）改写一致；仓库 `AGENTS.md:165-169` 同步。

**测试**：新增 `tests/test_task_session_start.py::test_active_tasks_listed_in_one_chooser_box`（断言单框约束、全部 active 任务在同一个 options 块、旧「两步弹框」文案消失）。`tests/test_task_session_start.py` + `test_install_hooks.py` 50 passed；prompt/task 相关 113 passed 1 skipped。

实跑 hook 的输出现在长这样（9 个任务全在一个框的 options 里）：

```341:346:codewiki/hooks/task_session_start.py
    lines.append("  该 question 的 options（按顺序）：")
    if active:
        for t in active:
            lines.append(f"    - {t.get('title') or t.get('id')}（task_id={t.get('id')}）")
    lines.append("    - 新建任务…（在输入框直接输入名称）")
    lines.append("    - 跳过（本次不做任务关联，直接开始干活）")
```

注意：本会话收到的还是旧文案（注入发生在会话启动那一刻），**下一个新会话**才会拿到单框版本。

要不要把「弹框类工具的 options 条数建议会诱导 Agent 拆框，需在注入文案里显式覆盖」这条写成一条 pitfall 笔记？确认后我再 `ingest_note`。
user: 好的 记笔记并确认
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"ingest_note\"],[\"codewiki\",\"confirm_note\"],[\"codewiki\",\"query_wiki\"]]"}]

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"query\": \"ask_followup_question 弹框 多框 options 条数\", \"mode\": \"c…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "ingest_note", "arguments": "{\"repo_path\": \"d:/repos/CodeWiki-CN\", \"note_type\": \"pitfall\"…
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "confirm_note", "arguments": "{\"repo_path\": \"d:/repos/CodeWiki-CN\", \"note_file\": \"2026-09-…
assistant: 已入库并确认。

- 笔记：`repowiki/notes/2026-09-10-弹框工具的-options-条数建议会诱导-agent-拆成多框须在注入文案里显式覆盖.md`
- 类型 `pitfall` / 严重度 `medium` / 状态已 `stable`（verified by `human:wangbao`）
- 挂载：`task_id=产品维护`，`related_modules=[mcp, hooks]`，另加 5 个别名（ask_followup_question 多框、任务关联弹框、单框列全、SessionStart 弹框、options 条数建议）

写入时 `ingest_note` 报了 2 条相似笔记（`2026-09-07-i18n 方案定案`、`2026-09-05-ingest_source 冲突闸门四层`），我判断它们是不同知识（中文语料方案、导入去重闸门），未做退役处理——如果你觉得需要合并，我再处理。

本轮改动汇总：hook 单框文案（三份副本）+ `prompts.py` 两处 + `AGENTS.md` 标记块 + 新增测试（50 passed / 113 passed 1 skipped）。下一个新会话起，任务关联只会弹一个框。
user: 提交推送代码
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git --no-pager status --short; git --no-pager diff --stat]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git --no-pager diff -- README.md repowiki/wiki/log-2026-09.md]
assistant: [tool: write_to_file · {"filePath": "d:/repos/CodeWiki-CN/.git/COMMIT_MSG_TMP", "content": "fix(hooks): SessionStart 任务关联只弹一个框，一框列全部进行中任务\n\nask_followup_quest…

[tool: execute_command · cd d:\repos\CodeWiki-CN; git add .codebuddy/hooks/task_session_start.py .qoder/hooks/task_session_start.py codewiki/hooks/task_session…
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git --no-pager status --short; git commit -F .git/COMMIT_MSG_TMP]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git --no-pager log -1 --stat; Remove-Item .git/COMMIT_MSG_TMP -Force]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git push origin develop]
assistant: 已提交并推送。

- commit `0c9fc2e`（`develop`），`14787c7..0c9fc2e develop -> develop`
- 8 个文件，+183/−62：三份 hook 副本、`codewiki/mcp/prompts.py`、`AGENTS.md`、`tests/test_task_session_start.py`、新笔记、`repowiki/wiki/log-2026-09.md`

两点需要你知道：

1. `README.md` 的「第 11 篇」文章链接是之前会话遗留的改动，与本次无关，**我没提交**，仍留在工作区。要一起推我再补一个 commit。
2. 工作区还有 5 个未跟踪的 `repowiki/conversations/conv-*.md` 和 `.codebuddy/skills/repowiki-conclusion-update/`，也未纳入本次提交。
