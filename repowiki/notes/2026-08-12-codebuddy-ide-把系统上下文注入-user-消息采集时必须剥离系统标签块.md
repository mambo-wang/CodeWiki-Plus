---
type: lesson
title: "CodeBuddy IDE 把系统上下文注入 user 消息，采集时必须剥离系统标签块"
date: 2026-08-12
related_modules: ["mcp", "capture", "\"\""]
related_components: []
tags: ["codebuddy", "lesson"]
source_ref: "raw\conv-user_query-@d-repos-CodeWiki-CN-repowiki-raw-conv-user_info.md"
status: deprecated
generated: { by: codewiki/5.2.2, at: 2026-08-12T11:59:15Z }
stale_after: 2026-11-10
origin: conversation

---

## 背景

用户发现 repowiki/raw/ 生成的对话文件包含大量与对话无关的系统内容。

## 根因

CodeBuddy IDE 会把整个系统上下文（<user_info>、<rules>、<git_status>、<project_context>、<additional_data> 等）作为首个 user 消息的 content 原样传给捕获 hook。capture_conversation 只按 role 过滤（保留 user/assistant），无法区分真实对话和系统注入噪声，导致所有 raw 文件被污染。

## 正确做法

在 capture_conversation.py 新增 _strip_system_injection()：剥离已知系统注入标签块；<user_query> 是真实用户输入，去壳保留内部文本；清理残留的 user: 空角色行。在 _extract_transcript 写 user turn 前调用。distill_conversation.py 的 _extract_turns 加同逻辑兜底防旧文件漏网。配套测试 tests/test_strip_system_injection.py（6 个用例）。
