---
type: architecture
title: UserPromptSubmit 技能提示 hook 已实现并接线，但命中面窄（只匹配 draft）且真机通道未验证
tags:
- architecture
- codewiki
- userpromptsubmit
metadata:
  date: 2026-09-10
  task_id: 产品维护
  related_modules:
  - hook
  - skill
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-docs-articles-CodeWiki-Plus系列13：把知识编译成行.md
  scene: 产品维护 / 技能提示 hook
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:46:50+00:00
stale_after: '2027-09-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:11Z'
---

## Background
用户读《CodeWiki-Plus系列13》文章，以为「提交 prompt 的技能提示 hook 没加」。实际核对代码后发现：它已实现、接线、文档、测试四件套齐全，只是命中面窄到几乎为零。

## 事实（依据本次代码核对）
- `codewiki/cli/utils/ide_config.py:107` 定义 `PROMPT_HOOK_CMD = "python -m codewiki.mcp._ide_hook --enable"`（走 `python -m` 而非物理脚本，settings.json 随仓库共享可移植）。
- `ide_config.py:120-122` 注册 `UserPromptSubmit`，`matcher: ""`（每条指令都过匹配器）+ `timeout: 10`。
- `codewiki/mcp/_ide_hook.py:389-432` 为匹配逻辑，`:492-493` 在捕获前分发该事件（只读、不捕获、不安装）。
- `codewiki/hooks.yaml:29` 登记在 claude 家族（`user_prompt: [UserPromptSubmit]`），cursor/codex 事件名是归并猜测，故意不登记。
- `.codebuddy/settings.json:27-38` 本仓库已实际接线且已入库（`git ls-files` 命中）；提交 `0db5ae1 feat(cli): install-hooks 支持 UserPromptSubmit 技能提示事件`。
- 实测 `--enable` 跑通，install 指针带「需你确认」护栏。

## 两个「没感觉到它存在」的真实原因
1. **命中面窄**：匹配器只认 `status: draft`，而 `repowiki/skills/` 仅 1 份 draft，绝大多数 prompt 空转。
2. **真机通道未验证**（真正缺口）：CodeBuddy 是否给 UserPromptSubmit 喂 stdin、是否消费 stdout `hookSpecificOutput` 尚未真机证明；SessionStart 通道是活的（任务关联提示就是它注入），但 UserPromptSubmit 未证。

## 结论
不该再加触发点（三个触发点已是「只提示、永不自动执行」上限），该做的是**真机探针验证** + 可选空转优化。与文章第六节设计一致：install 永远是人点头。
