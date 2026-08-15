---
type: decision
title: output_dir 解析收敛方案：resolve_workspace 单点 + 优先级统一
tags:
- '1'
- decision
- valueerror
- workspacecontext
metadata:
  date: 2026-08-15
  related_modules:
  - workspace_result
  - capture_conversation
  - distill_conversation
  - knowledge_loop
  source_ref: raw\conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:13:50+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:08Z'
---

## 背景

针对架构摩擦点 #1（output_dir 解析复制粘贴）的收敛方案，经 grilling 问询定案。

## 方案（5 项）

1. **新模块**：新建独立 `workspace_context.py`，`resolve_workspace(arguments, store) -> WorkspaceContext(dataclass: output_dir/session/repo_path)`；`workspace_result.resolve_session` 改为薄封装（避免 import 环）。
2. **优先级统一**：`显式 output_dir > 显式 repo_path 派生(rp/repowiki) > session.output_dir`——修复 stale path bug（「显式 > 可推导 > 缓存」语义最可预测）。
3. **错误契约**：抛 `ValueError`，依赖 `dispatch()` 统一兜底转 error dict（handler 内零 try/except）。
4. **纯解析不 mkdir**：只读场景不产生空目录垃圾，写场景调用方一行 `mkdir` 即可。
5. **范围**：11 处全收（capture/distill/source_ingest/knowledge_loop 6 处/doc_writer/module_tree/close_session）；`analysis.py` 除外（`repo_path` 强制参数语义不同）；`_ide_hook` 无自有解析不用动。

## 状态

方案已 grill 定案，落地实施待后续会话。
