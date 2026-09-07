---
type: decision
title: output_dir 是 repo_path 的纯函数：写路径一律布局推导、砍跨进程持久化、只读检索保留跨仓寻址出口
tags:
- decision
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - workspace_layout
  - cache
  - session
  - registry
  - note_query
  severity: high
  source_ref: conversations/conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md
  scene: MCP 工具参数面设计
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.1
  at: 2026-09-07 01:41:34+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: codewiki/5.6.1
  at: '2026-09-07T01:47:00Z'
---

## Background

用户质疑：REPO_PATH 与 OUTPUT_DIR 什么情况下需要自定义，能否删掉 output_dir 或只保留 repo_path，输出目录写死 repowiki？此前发生过跨仓库 output_dir 劫持清空真实索引的事故，深层原因是 output_dir 被跨进程持久化。

## 决策

字面"写死 `<repo>/repowiki`"不可行——会废掉 centralized 布局（业务仓没有自己的 repowiki）与 workspace 第二跳跨仓寻址。正确收敛（用户选定 B 激进方案）：

1. 写路径收敛：analyze/write/ingest/close 等工具的 `output_dir` 移出必选参数面，一律 `default_output_dir(repo_path)` 布局推导；显式 output_dir 降级为 legacy 覆盖并拒绝指向 repo 外。
2. 砍掉跨进程持久化：删除 `cache.repo_meta.output_dir`，`find_or_restore` 恢复 session 时用布局推导；`set_output_dir` 不再存在，smoke 污染在机制上不可能。
3. 只读检索保留唯一独立寻址出口：`query_wiki`/`note_query` 允许 output_dir 指向任意 wiki（含别的仓）——workspace 两跳路由刚需，且只读不产生污染。

## Rationale

- 代码中已有唯一布局感知推导函数 `default_output_dir(repo_path)`（`workspace_layout.py`）；所有工具解析链第三级已是"repo_path 能唯一确定目录"，只是布局感知而非字面写死。
- 两跳都可只传 repo_path：`query_wiki` 原生支持 repo_path 寻址（`note_query.py`），无显式 output_dir 时经 `default_output_dir` 布局推导；`find_or_restore` 在业务仓无缓存时返回 None 恰好落到 repo_path 推导分支。
- 唯一保留显式 output_dir 的例外：目标知识库不属于任何仓库布局（无宿主仓的孤立 wiki 目录）。
- session.output_dir 应恒为推导值；写 handler 统一 `output_dir = resolve_output_dir(session, arguments)`（allow_explicit=False 时忽略显式 output_dir，仅告警不一致）。

## 待确认范围

影响面：53 个工具文件引用 output_dir，绝大多数是透传 store_bridge；真正改 schema 描述、handler 解析、session 恢复、`cache.py` 三处点 + 测试断言。centralized/colocated 回归测试（`test_centralized_layout_fixes` 等）可兜底。
