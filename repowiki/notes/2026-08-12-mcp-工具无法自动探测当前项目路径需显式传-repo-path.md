---
type: pitfall
title: "MCP 工具无法自动探测当前项目路径，需显式传 repo_path"
tags: ["codebuddy", "pitfall"]
status: deprecated
generated: { by: codewiki/5.2.2, at: 2026-08-12T11:59:00Z }
stale_after: 2026-11-10

metadata:
  date: "2026-08-12"
  origin: "conversation"
  related_components: []
  related_modules: ["mcp", "\"\""]
  source_ref: "raw\\conv-system_reminder-请注意，当你在遇到无法解决的问题时，往往会出现重复行为，导致陷入循环——例如重复输出相同-9.md"
---

## 背景

询问不传 repo_path 时能否自动拿到当前项目路径。

## 结论

不能。resolve_session（workspace_result.py）只认 session_id / repo_path，两者都没有返回 None。MCP server 是独立进程，dispatch 只透传客户端给的 arguments，不做参数注入，工具内部也没有探测 IDE 工作目录的机制。

## 正确做法

调用 query_wiki 等工具时始终显式传 repo_path（绝对路径），不依赖 session 状态。CodeBuddy 集成场景下项目路径由 IDE 侧通过 prompt 模板 _resolve_path 用 os.getcwd() 兜底拼进 repo_path 参数。
