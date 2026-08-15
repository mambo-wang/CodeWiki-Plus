---
type: architecture
title: MCP server 薄壳化架构：server.py 职责拆分到 registry/prompts/resources/tools
tags:
- architecture
- tooldef
metadata:
  date: 2026-08-15
  related_modules:
  - server
  - registry
  - prompts
  - resources
  - close_session
  source_ref: raw\conv-user_command-commands-codewiki-增量更新-Wiki-请增量更新代码仓库的-Wiki-文档。.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:14:27+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:05Z'
---

## 背景

team-memory-fusion 功能（新增 capture/distill 工具）落地时，MCP server 层顺带完成了「薄壳化」重构。

## 职责划分（重构后）

- **`server.py`**：薄壳，仅 `list_tools`（→ `registry.get_all_tools()`）、`call_tool`（→ `registry.dispatch()`）、`main`，并调用 `prompts.register()` + `resources.register()`。
- **`registry.py`**：工具注册中心——`ToolDef` + `REGISTRY` dict + `_register()` + `get_all_tools()` + `dispatch(name, arguments, store)`；注册 29 个工具，三种执行模式 `main_thread`/`thread`/`async`。
- **`prompts.py`**：14 个 `_prompt_*` builders + `register()`（内含 `list_prompts`/`get_prompt`）。
- **`resources.py`**：`register()`（3 个静态 resources + 3 个 `codewiki://wiki/{output_dir}/...` templates）。
- **`tools/close_session.py`**：`_write_generation_metadata_from_disk`、`_write_metadata_json`（原在 server.py，已迁出）。
- **`tools/*.py`**：各工具 handler。

## 维护含义

改工具只需动 `tools/<x>.py` + `registry.py` 注册两处；prompts/resources 各自独立 register；`server.py` 不再是逻辑承载地。模块文档若仍描述「server.py 里的 _prompt_*/_write_*metadata」即为过时。
