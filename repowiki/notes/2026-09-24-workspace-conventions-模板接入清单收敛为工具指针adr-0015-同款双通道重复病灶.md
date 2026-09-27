---
type: decision
title: Workspace Conventions 模板接入清单收敛为工具指针（ADR-0015 同款双通道重复病灶）
tags:
- codewiki
- decision
metadata:
  date: 2026-09-24
  confidence_level: weak
  task_id: 他山之石
  source_session: 1b5f06c022ab4dcd9dfabc02661535f2
  related_modules:
  - templates/workspace
  - mcp/prompts
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-670adf.md
  scene: 集中式工作区 AGENTS.md 约定块精简
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-24 12:57:19+00:00
stale_after: '2027-09-25'
origin: conversation
verified:
- by: human:iamwangbao
  at: '2026-09-25T13:32:43Z'
---

## Background

用户要求评估 CodeWiki Workspace Conventions 块（集中式布局版，48 行）的精简空间。该块是产品模板渲染物（`templates/workspace/agents-md-workspace-centralized.md.tpl`，经 `write_workspace_conventions` 标记整块替换），改模板即改所有集中式工作区。提交 1787de0。

## Decision

逐节过筛后只动两处：

1. **新业务仓接入清单 8→2 行**：清单里的「手工接入须同步三处」（bootstrap 登记表、`.gitignore`、repo-map）与 `add_workspace_repo` 工具的事务式同步是双通道重复——工具 prompt 已写明同步四处。这是 ADR-0015 同款病灶（文件全文 + prompt 按需版并存）。收敛为块内 2 行（工具名 + `get_prompt("add-workspace-repo")` 指针），手工三步作为「MCP 工具不可用时的兜底」移入该 prompt 的注意事项。
2. **分支策略 3→1 行**：规则是「不要在本仓记录业务仓分支」，前后解释删掉。

**保留不动**：头部布局说明、检索路由（一跳）、提交纪律红线（`.gitignore` 失效即停）、知识写入路由表——都是唯一载体的行为规则，符合「只删重复、留唯一」边界。

**连带**：colocated 模板（`agents-md-workspace.md.tpl`）同步改保持两模板结构对齐；`test_hook_registry.py:358` 只断言标记存在，内容改动安全。

## Rationale

写错位置是集中式布局最高频错误，路由表是唯一载体必须留；接入清单是唯一有重复载体的一节，删的恰好是它。存量工作区经标记整块替换自动升级，零迁移成本。
