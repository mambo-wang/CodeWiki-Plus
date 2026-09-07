---
type: pitfall
title: "Server(...) 在 server.py 模块顶层构造，语言初始化必须早于它"
tags: ["pitfall"]
metadata:
  date: 2026-09-07
  task_id: 产品维护
  related_modules: ["mcp", "i18n"]
  severity: medium
  source_ref: "conversations/conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md"
  scene: "MCP 国际化"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.7.0, at: 2026-09-07T06:49:15Z }
stale_after: 2027-03-06
origin: conversation

---

## 背景

给 `_SERVER_INSTRUCTIONS` 接多语言时，需要确定语言初始化的时点。

## 事实

`codewiki/mcp/server.py:138` 的 `Server(...)` 在**模块顶层 import 时**就构造，`instructions=` 参数在那一刻定死；prompts/resources 的注册同样在 import 期完成。

## 正确做法

语言解析（读 config.json / env / locale）必须在 `Server(...)` 构造**之前**执行，解析一次并缓存即可——import 期之后改语言对已构造的 instructions 无效。同类约束适用于任何在 import 期定死的常量（registry、schema 描述、静态文案表等）：改语言/改配置后必须重启进程才生效。
