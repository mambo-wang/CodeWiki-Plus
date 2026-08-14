---
type: architecture
title: "query_wiki 的 output_dir 非必填，解析顺序为 output_dir → session → repo_path"
tags: ["architecture"]
status: deprecated
generated: { by: codewiki/5.2.2, at: 2026-08-12T11:58:59Z }
stale_after: 2026-11-10

metadata:
  date: "2026-08-12"
  origin: "conversation"
  related_components: []
  related_modules: ["mcp", "\"\""]
  source_ref: "raw\\conv-system_reminder-请注意，当你在遇到无法解决的问题时，往往会出现重复行为，导致陷入循环——例如重复输出相同-9.md"
---

## 背景

确认 query_wiki 入参 output_dir 是否必填。

## 结论

output_dir 不是必填。handle_query_wiki（codewiki/mcp/tools/knowledge_loop.py）按优先级解析：
1. 显式传 output_dir → 直接使用；
2. 有 session（session_id 或 repo_path 解析得到）→ 用 session.output_dir；
3. 只传 repo_path 无 session → 推导为 <repo_path>/repowiki；
4. 以上都没有 → 才报错 output_dir is required。

IDE 正常会话中只传 repo_path 即可，报错信息里的 required 只是兜底提示。

## Rationale

多级兜底让调用方不必关心 session 状态；schema 层所有属性均无 required 数组。
