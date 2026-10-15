---
type: decision
title: init 命令「否」失效根因与定案：维持 opt-out，薄壳映射指引 + prompt 意愿闸门双通道修复
tags:
- decision
- sessionstart
metadata:
  date: 2026-10-09
  confidence_level: weak
  task_id: 产品维护
  source_session: 09354b56591d451e887b21cdc7d615c8
  related_modules:
  - codewiki/mcp/prompts
  - codewiki/cli/commands/sync_commands
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-9f00fb.md
  scene: init-wiki/init-workspace 命令接线默认值与用户意愿传递
status: stable
author: Administrator
generated:
  by: codewiki/5.14.1
  at: 2026-10-09 01:25:18+00:00
stale_after: '2027-10-09'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-09T01:26:53Z'
---

## Background

用户通过 `codewiki/初始化单仓Wiki工作区` 命令初始化 Wiki 工作区，在任务关联弹框中输入「否」（表示不启用任务管理），但 init 仍执行了步骤 2 接线（添加 SessionStart hook 等）。单仓 `init-wiki` 与多仓 `init-workspace` 两个 prompt 同构存在此问题。

## Root cause（意图传递链路断裂）

1. `sync-commands` 生成的命令薄壳（`.qoder/commands/codewiki/*.md`）把 `enable_task_management` 列入 `_SWITCH_ARGS`（`codewiki/cli/commands/sync_commands.py:42`）**故意不注入** arguments，薄壳只传 `arguments={"repo_path": "."}`；
2. 用户在弹框输入的「否」以自由文本附在命令后到达 Agent 上下文，但薄壳与 prompt 都没有告诉 Agent「用户表达不启用意愿时应映射为 `enable_task_management=false` 传给 `get_prompt`」；
3. Agent 按薄壳字面调用 → `prompts.py:268-272` 的 opt-out 默认值（仅显式 `false/0/no/off` 跳过）生效 → 步骤 2 被渲染执行。

即：**「opt-out 默认值 + 薄壳不传开关参数」组合下用户意愿没有结构化通道到达 prompt 渲染，用户无路可逃**。

## Decision（用户确认「动手实现」，已实现并验证：全量测试通过、ruff 无告警）

1. **维持 opt-out 默认**（理念：初始化 = 一次性把必要配置做好，含任务管理接线），不拆独立开关、不删除参数；
2. **a+b 双通道修复**：`_STUB_TEMPLATE` 对含开关参数的 prompt 追加映射指引（用户表达不启用意愿 → 传 `enable_task_management=false` 再调 `get_prompt`）+ `prompts.py` 两个 init prompt 步骤 2 正文加用户意愿闸门句（已表达不启用则跳过并提示可用 team-memory-hook 随时启用）——单通道已被本次事故实证会失效；
3. **sync-commands 升级为必做步骤**，去掉「跳过也无妨」措辞；
4. **两条管线维持「总开关 + capture 细开关」**（`enable_task_management` 砍整块、`capture=off` 只移除 SessionEnd），不拆成正交双开关——两条管线共享接线产物（hook 脚本拷贝、distill-worker、AGENTS.md 段落），完全正交会引入中间态、复杂度大于收益；
5. **历史已接线仓库不自动回滚**，用 `install-hooks --status` 查现状、`team-memory-hook action=disable` 自助清理。

## Rationale

本决策修正了 2026-09-21 笔记《init prompt 任务管理接线修复：接线目标恒为工作区根，公共块以 team-memory-hook 富版本为母本》中「拼错值宁可多接一次（幂等无害）」的 opt-out 理由——接线并非无害（改 settings.json、拷脚本、写 AGENTS.md 段落），默认保留 opt-out 是用户明确的产品理念选择，安全性靠双通道意愿闸门补偿而非改默认值。该旧笔记的其余结论（接线目标恒为工作区根、公共块单点收敛）仍有效，未被推翻。
