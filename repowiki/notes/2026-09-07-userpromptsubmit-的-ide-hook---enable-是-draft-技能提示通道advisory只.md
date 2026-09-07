---
type: architecture
title: UserPromptSubmit 的 _ide_hook --enable 是 draft 技能提示通道（advisory）：只提示不捕获，无 draft
  技能时空转
tags:
- architecture
- codewiki
- userpromptsubmit
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - mcp
  - ide-hook
  - skill-creator
  severity: medium
  source_ref: conversations/conv-@settings.json-27-38-是不是有问题，python-m-codewiki.mcp._ide_hook.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 02:56:41+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:20Z'
---

## 背景

`.codebuddy/settings.json` 中 `python -m codewiki.mcp._ide_hook --enable`（install-hooks 三件套之一，PROMPT_HOOK_CMD，codewiki/cli/utils/ide_config.py）是 UserPromptSubmit 事件上的「草稿技能提示」通道（skill-creator §10，advisory）：从 stdin 读事件载荷，把 prompt 与 `repowiki/skills/*/SKILL.md` 中 `status: draft` 的未安装技能做 containment 匹配（阈值 0.5、≥8 token，codewiki/src/skill_match.py），命中则往 stdout 写 `hookSpecificOutput.additionalContext` 由 IDE 注入提醒「有草稿技能可用」。只提示、不捕获、不安装。`--enable` 是 opt-in 开关（等价 `CODEWIKI_TEAM_MEMORY_HOOK=1`）。

## 关键事实

1. 匹配只认 `status: draft`；草稿区无 draft 技能时该 hook 每条消息空转（白启一次 python，timeout 10s，实测 stdout 为空 exit 0）。短期无 draft 技能可删掉该配置段（SessionStart/SessionEnd 采集不受影响）。
2. 诊断输出必须走 stderr：stdout 只允许两种输出——UserPromptSubmit 命中的 hookSpecificOutput JSON、捕获完成的 print(result)。2026-09-07 已把无载荷/disabled/envelope 诊断/无 turns 四处 print 定向 sys.stderr，保证「未命中/无载荷时 stdout 为空、注入零噪音」的设计前提成立。
3. CodeBuddy 是否喂 stdin、是否消费 stdout 的 hookSpecificOutput 尚未真机验证；docs/team-memory-hook.md 事件表只登记了已实测的 SessionStart/SessionEnd。

## 适用范围

codewiki/mcp/_ide_hook.py、codewiki/src/skill_match.py、.codebuddy/settings.json、codewiki/hooks/
