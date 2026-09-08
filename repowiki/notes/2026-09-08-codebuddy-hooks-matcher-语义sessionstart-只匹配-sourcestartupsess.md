---
type: pitfall
title: CodeBuddy Hooks matcher 语义：SessionStart 只匹配 source=startup、SessionEnd 只匹配 reason=other，空串匹配全部
tags:
- codebuddy
- pitfall
- sessionend
- sessionstart
metadata:
  date: 2026-09-08
  related_modules:
  - hooks
  severity: medium
  source_ref: conversations/conv-@settings.json-5-5-sessionStart和sessionEnd的matcher是否需要优化，发现某.md
  scene: hook 采集
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:02:10+00:00
stale_after: '2027-03-07'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-08T05:28:18Z'
---

## Background

用户反馈「某些情况不触发 hook」，怀疑 `.codebuddy/settings.json:3-26` 里 SessionStart/SessionEnd 的 matcher 取值需要优化。核对官方文档与本地注册骨架后的结论是：取值本身已是官方唯一合法值，不存在「换成更宽/更具体的值就能多覆盖官方场景」的写法。

## 事实

依据 CodeBuddy 官方 Hooks 文档，以及本地 `codewiki/cli/utils/ide_config.py:113-123` 的 `HOOKS_REGISTRATION`（`merge_settings_json` 用同一组常量，`tests/test_install_hooks.py:107-118` 有断言）：

- `matcher` 是**正则表达式**；空串 `""` 或 `"*"` = 匹配所有。
- `SessionStart` 的 matcher 匹配事件 JSON 的 `source` 字段，官方目前唯一支持值 `startup`。
- `SessionEnd` 的 matcher 匹配 `reason` 字段，官方目前唯一支持值 `other`。
- `UserPromptSubmit` / `Stop` 不使用 matcher，所有提交/停止均触发。

## 建议（**用户未回复确认，属待定，未落地**）

既然空串/`*` 语义为「匹配所有」，且本项目 hook 的语义本就是「每个新会话都注入任务引导」，可把 matcher 改为 `""` 作为零成本保险——未来 IDE 在恢复历史会话/重启恢复等场景派发非 `startup`/`other` 的值时也不会漏触发。改时必须同步三处，否则重跑 `install-hooks` 会被旧值覆盖回去：`settings.json`、`codewiki/cli/utils/ide_config.py`（`HOOKS_REGISTRATION` 与 `merge_settings_json`）、`tests/test_install_hooks.py` 的断言。

## 边界

进程被强杀、崩溃、断电**不派发 SessionEnd**，该会话 transcript 永远漏采——这不是 matcher 能解决的，只能靠事件补偿。
