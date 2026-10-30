---
type: lesson
title: "ADR-0020 的 change_plan/job_state 是内部簿记模块而非 MCP 工具：判断「新工具未注册」前先查 TOOL_REGISTRY"
tags: ["lesson"]
metadata:
  date: 2026-10-30
  confidence_level: weak
  task_id: 发版本
  source_session: "5dee23d20a5649afa4429fdc1594bc07"
  related_modules: ["codewiki/mcp"]
  severity: medium
  source_ref: "conversations/conv-@command-windows-python-release-发布版本5.16.3.md"
  scene: "产品维护"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.5, at: 2026-10-30T03:33:16Z }
stale_after: 2027-04-28
origin: conversation

---

## Background

拉取 ADR-0020 代码后，MCP server 工具列表里看不到 `change_plan`/`job_state`，最初误判为「新工具需重启 MCP server 才能注册」；用户重启 MCP 后仍看不到，进一步查证 registry 才更正结论。

## 结论

`change_plan`/`job_state` 是 ADR-0020 设计的**内部确定性簿记模块**，不新增 MCP 工具面，经既有工具暴露：

- `save_module_tree` → 内部调用 change_plan 构建算子计划并在返回值带 `change_plan` 字段（`codewiki/mcp/registry.py:366-368`）
- `analyze_repo` → 内部 `job_state.start_job`/`finish_job`（`codewiki/mcp/tools/analysis.py:84,130`）
- `close_session` → 内部 `finalize_plan` + `finish_job`（`codewiki/mcp/tools/close_session.py:288-316`）
- `write_doc_file` → 每写一页 `mark_page_written` + `mark_op_done`（`codewiki/mcp/tools/doc_writer.py:1087-1098`）

## 教训

判断某模块是否为 MCP 工具，应以 `codewiki/mcp/registry.py` 的 TOOL_REGISTRY 为事实口径（可直接 `.venv/Scripts/python.exe -c "from codewiki.mcp.registry import TOOL_REGISTRY; print(list(TOOL_REGISTRY))"` 验证），不能凭 PR/ADR 描述推断。「重启后仍未注册」可能是符合设计的正常现象，不是故障。

## Rationale

避免下次拉取含内部模块的代码后再次误判「需要重启/工具丢失」，也避免向用户传递错误结论后再更正的往返成本。
