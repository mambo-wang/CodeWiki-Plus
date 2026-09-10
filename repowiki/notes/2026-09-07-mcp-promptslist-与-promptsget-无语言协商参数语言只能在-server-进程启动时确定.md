---
type: architecture
title: MCP prompts/list 与 prompts/get 无语言协商参数，语言只能在 server 进程启动时确定
tags:
- architecture
- getpromptrequestparams
- listpromptsrequestparams
- paginatedrequestparams
- requestparams
metadata:
  date: 2026-09-07
  task_id: 产品维护
  related_modules:
  - mcp
  - i18n
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md
  scene: MCP 国际化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 06:50:50+00:00
stale_after: '2027-09-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:22Z'
---

## 背景

设计 prompt 国际化时，需要判断能否「按客户端语言每次请求动态返回不同语言」。核对 MCP SDK 类型定义（`.venv/Lib/site-packages/mcp/types.py:61-123`）：`RequestParams` 只有 `progressToken`；`ListPromptsRequestParams` 继承 `PaginatedRequestParams` 仅有 `cursor`；`GetPromptRequestParams` 只有 `name + arguments`。

## 结论

协议层没有语言协商通道，**无法按请求动态切语言**；语言只能在 server 进程启动时选定一次。该约束实际可接受：每个 IDE 会话对应一个独立 stdio 进程（`python -m codewiki.mcp.server`），语言粒度 = 单个 server 实例 = 单个用户配置。

## 影响

- 不要设计 per-request 的语言参数或扩展 handler 签名；语言是进程级常量（如 `i18n.current_lang()`）。
- 用户切换语言的方式：在 MCP 配置的 `env` 字段注入 `CODEWIKI_LANG`，server 端只读环境变量，不改启动入口。若改为 `args` 传参（`python -m codewiki.mcp.server --lang en`），需给 `main()` 加参数解析（`codewiki/mcp/server.py:258-265` 当前无任何参数解析），侵入更大，不推荐。
