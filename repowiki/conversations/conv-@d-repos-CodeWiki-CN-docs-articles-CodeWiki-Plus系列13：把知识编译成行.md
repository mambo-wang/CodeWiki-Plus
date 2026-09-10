---
type: Conversation
title: "conversation 20260910T013722Z"
status: distilled
stale_after: 2026-12-09
generated: { by: codewiki/5.8.0, at: 2026-09-10T01:37:22Z }
captured_at: "2026-09-10T01:37:22Z"
content_hash: "sha256:c592b43b937e7a6702c8bbf2c928b3ea303f53bebbb0fe8dcf7725ccdfa508e4"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=3"
keep_raw: false
link_to: ""
source_session: "1cf5e2225cbe4c21b9aae3569b922e75"
task_id: "产品维护"
turn_count: 25
---

# Conversation Transcript

user: @d:\repos\CodeWiki-CN\docs\articles\CodeWiki-Plus系列13：把知识编译成行为——从WikiSkill论文到skill-creator的两区制闸门.md  文章里写的提交prompt的hook我们其实没加吧，你觉得可以加吗
assistant: [tool: ask_followup_question · {"questions": [{"question": "本次会话要关联哪个任务？（关联后会拉取该任务的跨会话上下文）", "options": ["跳过（本次会话不做任务关联，直接干活）", "CodeWiki 架构深化分析", "技能提取", "产品维…
user: <title>任务关联</title>

<question>本次会话要关联哪个任务？（关联后会拉取该任务的跨会话上下文）</question>
<answers>
产品维护
</answers>
</question_item>

<question>如果需要新建任务，请直接输入任务名称（例如「技能提取-提交Hook」）；不需要可忽略</question>
<answers>
临时任务
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\",\"set_session_task\"],[\"codewiki\",\"get_task_context\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"1cf5e2225cbe4c21b9aae3569b922e75\",\"t…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"产品维护\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\docs\\articles\\CodeWiki-Plus系列13：把知识编译成行为——从WikiSkill论文到skill-creator的两区制闸门.md"}]
assistant: [tool: search_content · d:\repos\CodeWiki-CN]

[tool: search_content · d:\repos\CodeWiki-CN]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\repowiki\\notes\\2026-09-07-userpromptsubmit-的-ide-hook---enable-是-draft-技能提示通道advisory只.md"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\hooks.yaml]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\cli\utils\ide_config.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\_ide_hook.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\.codebuddy\\settings.json"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\hooks.yaml"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\repowiki\\notes\\2026-09-08-codebuddy-hooks-matcher-语义sessionstart-只匹配-sourcestartupsess.md"}]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; git ls-files .codebuddy/settings.json; git --no-pager log --oneline -5 -- codewiki/cli/utils/ide_config.py]

[tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\repowiki\\skills"}]
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; Get-Content repowiki/skills/maintain-fork-pr-merge/SKILL.md -TotalCount 12; Get-Content repowiki/skills/windo…
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\_ide_hook.py]
assistant: [tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\.tmp-hook-probe.json", "content": "{\n  \"hook_event_name\": \"UserPromptSubmit\",\n  \"prompt\": …
assistant: [tool: execute_command · cd d:\repos\CodeWiki-CN; $out = & .venv\Scripts\python.exe -m codewiki.mcp._ide_hook --enable --conversation .tmp-hook-probe.json 2>$n…
assistant: [tool: delete_file · {"target_file": "d:\\repos\\CodeWiki-CN\\.tmp-hook-probe.json", "explanation": "删除实测用的临时载荷文件"}]

[tool: search_content · d:\repos\CodeWiki-CN\repowiki\wiki\log-2026-09.md]
assistant: 结论先说：**这个 hook 其实已经加了，而且代码、接线、文档、测试四件套都齐了**——但它有两个"你可能没感觉到它存在"的真实原因，下面分开说。

## 一、它确实在代码里

依据本次代码核对：

- `codewiki/cli/utils/ide_config.py:107` 定义了 `PROMPT_HOOK_CMD = "python -m codewiki.mcp._ide_hook --enable"`（走 `python -m` 而非物理脚本，settings.json 随仓库共享可移植）
- `codewiki/cli/utils/ide_config.py:120-122` 在 `HOOKS_REGISTRATION` 注册了 `UserPromptSubmit`，`matcher: ""`（每条用户指令都过匹配器）+ `timeout: 10`
- `codewiki/mcp/_ide_hook.py:389-432` 的 `_handle_user_prompt` 是匹配逻辑；`:492-493` 在捕获逻辑之前分发该事件（只读、不捕获、不安装）
- `codewiki/hooks.yaml:29` 登记在 claude 家族（`user_prompt: [UserPromptSubmit]`），且注释明确写了 cursor/codex 的事件名是归并猜测，**故意不登记**
- `.codebuddy/settings.json:27-38` 本仓库已实际接线，且该文件已入库（`git ls-files` 命中）
- 提交记录：`0db5ae1 feat(cli): install-hooks 支持 UserPromptSubmit 技能提示事件——advisory 接线一键化`

我还实测跑了一遍（用 `windows-python-release` 这份 `status: draft` 草稿构造载荷）：

```
STDOUT={"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
 "additionalContext": "适用技能草稿 `windows-python-release`：当在 Windows 上手动发布 Python 包…
  如需启用：skill_creator(mode=\"install\", name=\"windows-python-release\")
  （需你确认后执行；我不会自动 install）"}}   EXIT=0
```

脚本侧是通的，install 指针也带了"需你确认"的护栏，符合文章第六节的设计。

## 二、为什么你会觉得没加

1. **命中面窄到几乎为零**。`repowiki/skills/` 现在只有 2 份：`maintain-fork-pr-merge` 是 `stable`（已安装，不匹配），只有 `windows-python-release` 一份是 `draft`。匹配器只认 `status: draft`，所以日常绝大多数 prompt 都是空转，你自然没见过它冒出来。
2. **真机通道未验证**（这是真正的缺口）。笔记 `repowiki/notes/2026-09-07-userpromptsubmit-的-ide-hook---enable-是-draft-技能提示通道advisory只.md` 第 38 行写明：CodeBuddy 是否给 UserPromptSubmit 喂 stdin、是否消费 stdout 的 `hookSpecificOutput`，尚未真机验证；`docs/team-memory-hook.md` 事件表只登记了已实测的 SessionStart/SessionEnd。脚本能跑通 ≠ IDE 真的注入了。

## 三、我的判断：不该"加功能"，该"补验证"

再叠加新触发点我反对——三个触发点（UserPromptSubmit / L2 submit / 蒸馏 submit）在文章里已经是"只提示、永不自动执行"的上限，再加就偏离"install 永远是人点头"这条底线了。真正缺的是两件小事：

1. **把真机验证做掉**（优先级最高）。SessionStart 那条通道是活的（本次会话开头的任务关联提示就是它注入的），说明 CodeBuddy 会消费 stdout 的 `additionalContext`；但 UserPromptSubmit 是否真的收到 prompt 载荷还没被证明。建议临时把该条 command 换成一段"把 stdin 原样落到 `.meta/` 的探针"，重启会话发一条明显命中 `windows-python-release` 的 prompt（比如"我在 Windows 上发 Python 包，dist 残留被一起上传了"），看有没有落盘 + 有没有注入提示。结论无论真假都有价值：通了就把 `hooks.yaml` 的 verified 状态坐实；不通就该在文章和接线里把它标成"claude 家族理论支持"，别让它每条 prompt 白起一个 python 进程。
2. **空转优化**（可选，约几行）。草稿区没有 `draft` 技能时，`install-hooks` 可以不注册 UserPromptSubmit，或者 hook 内部在 skills 目录为空时更早退出现在每次都要起进程 + 读目录。

要我现在动手做第 1 步的真机探针验证吗？改 `.codebuddy/settings.json` 一条 command，验证完立刻恢复。
user: 文章中说可以给技能反馈问题，如何反馈
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\":\"1cf5e2225cbe4c21b9aae3569b922e75\",\"t…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\":\"产品维护\",\"repo_path\":\"d:/repos/CodeWiki-CN\",\"…

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: [tool: task · {"subagent_name": "distill-worker", "description": "补蒸馏产品维护积压对话", "prompt": "你是蒸馏 worker。本仓库 d:/repos/CodeWiki-CN 的任务「产品维护」有 1 条未蒸馏的 raw 对话积压（rel…

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\registry.py]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\registry.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\skill_creator.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\skill_creator.py", "offset": 329, "limit": 32}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\issue_tracker.py]
assistant: [tool: search_content · d:\repos\CodeWiki-CN]

[tool: search_content · d:\repos\CodeWiki-CN\docs\skill-creator使用指南.md]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\issue_tracker.py", "offset": 100, "limit": 60}]

[tool: execute_command · cd d:\repos\CodeWiki-CN; if (Test-Path repowiki/.meta/issues.json) { (Get-Content repowiki/.meta/issues.json -Raw).Length; Get-Content…
assistant: ## 怎么反馈：一句话就行，但有两个参数必须写对

直接对 Agent 说「这个技能漏了 X 情况 / 给了错指引」，它会调 `flag_issue`。实际调用形态（依据 `docs/skill-creator使用指南.md:178`）：

```
flag_issue(
  repo_path="d:/repos/CodeWiki-CN",
  page_path="skills/<name>/SKILL.md",     # ← 最容易写错的一个
  issue_type="custom",                     # ← 文章里那个 skill-ineffective 不在枚举里
  description="漏了 X 情况：……",
  severity="warning"
)
```

写入位置 `repowiki/.meta/issues.json`，ID 是 `FNV-1a(issue_type::page_path)` 稳定哈希（`codewiki/mcp/tools/issue_tracker.py:34-37`），同类型同页面重复打标**幂等**：不新建条目，只 `occurrences+1` 并把新描述追加进 `updates`，原文保留（`:146-155`）。

闭环：下次 `skill_creator(mode="prepare")` 的 `open_issues_by_skill` 字段会按技能名聚合这些 open issues（`codewiki/mcp/tools/skill_creator.py:329-352`）→ Agent 把反馈折进正文 → `submit(action="updated")` → 你确认 → reinstall。

## 三个真实的坑

1. **`page_path` 必须指向草稿区，写生效区会被静默丢弃。** 分组逻辑要求路径至少 3 段且首段等于 `skills`（`skill_creator.py:340-342`）。技能装上后物理位置在 `.codebuddy/skills/<name>/SKILL.md`，但反馈**仍然要写** `skills/<name>/SKILL.md`——写生效区路径不报错，只是永远进不了 prepare，反馈石沉大海。
2. **`issue_type="skill-ineffective"` 会被降级成 `custom`。** 枚举只有 9 个值（`registry.py:1985-1995`），handler 对未知类型打 warning 后强制改写为 `custom`（`issue_tracker.py:110-112`）。功能上不影响聚合（分组不过滤类型），但"这是技能无效反馈"这个语义丢了。要么统一用 `custom`，要么把该值加进枚举——**注意要改两处**：`registry.py` 的 schema enum 和 `issue_tracker.py:99-109` 的 `valid_types`，只改一处会前后不一致。
3. **没有"关闭 issue"的工具。** 注册表里只有 `flag_issue`，没有 `resolve_issue`。修订完、skill 更新了，那条 issue 还是 `open`，会继续出现在每次 prepare 里当素材。目前唯一的关闭手段是手动把 `.meta/issues.json` 里该条 `status` 改成非 open（`skill_creator.py:338` 只认 `open`）。这是我认为最该补的一个洞。

## 仓库里已经有一条真反馈

`repowiki/.meta/issues.json` 的 `2ceafde2`：

```
page_path:   skills/maintain-fork-pr-merge/SKILL.md
issue_type:  custom          ← 打的应该是语义类型，被降级了
description: 适用条件漏了 draft PR：mergeStateStatus=DRAFT 时探测冲突无意义，需先等 CI 出结果再判断
status:      open
```

链路是通的，正好也印证了坑 2 和坑 3：类型被降级成 `custom`，且至今仍 open。

---

顺带两件事：

- 上一步的**蒸馏 subagent 没跑成**——它自检发现拿不到 `distill_conversation` 工具就停了（符合 `2026-09-08-蒸馏-worker-启动前先自检-mcp-可见性` 那条笔记的约定，没退让去直连 handler）。「产品维护」现在有 1 条积压 raw（就是上一轮这篇对话）。要我现在自己走 Mode C 补掉吗？
- 上面三个坑里，**1 和 3 值得沉淀成一条 pitfall 笔记**（2 属于文档笔误，顺手改 `docs/skill-creator使用指南.md:178` 和文章第六节即可）。草稿要点：技能反馈的 `page_path` 是草稿区路径、生效区路径静默失效；issue 无关闭工具、修订后仍 open。要我写成 `ingest_note` 草稿给你确认吗？
