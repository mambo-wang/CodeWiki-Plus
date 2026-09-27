---
type: decision
title: 主动沉淀 100% 生效的机制分析与 UserPromptSubmit 薄触发方案（deferred）
tags:
- decision
- userpromptsubmit
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 他山之石
  source_session: 1b5f06c022ab4dcd9dfabc02661535f2
  related_modules:
  - mcp/_ide_hook
  - hooks/task_session_start
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-848ca6.md
  scene: 主动沉淀协议生效链路优化
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-24 13:00:14+00:00
stale_after: '2027-09-25'
origin: conversation
source_conversations:
- conversations/conv-working_memory_content-The-following-is-the-existing-working-2-670adf.md
verified:
- by: human:iamwangbao
  at: '2026-09-25T13:32:40Z'
---

## Background

本笔记取代原 deferred 方案笔记（2026-09-20，用户当时拍板「暂不做」）：该方案已于本次会话完整实施并真机验证（提交 2f316ad），deferred 状态解除。原方案的设计骨架保留——规则与触发分离、复用 `_ide_hook --enable` 的 UserPromptSubmit 注册、诚实天花板（prompt 注入是软约束，推高命中率后接受残差，残差由收尾轮兜底）。

## Decision（已实施）

`_ide_hook.py` 新增 `ACTIVE_SETTLE_REMINDER` 常量 + `_repo_has_active_tasks()`（读 `repowiki/tasks/.index.json`，fail-open：索引损坏/不可读则不注入、exit 0，hook 绝不因自身簿记破坏用户 prompt）；`_handle_user_prompt` 输出改为技能提示与提醒拼接（技能在前更具体，提醒在后通用兜底）。补 5 条测试断言（注入/无任务静默/非 active 静默/拼接顺序/索引损坏 fail-open）。

**与原方案的两处偏差**：
1. 触发条件用「仓库有 active 任务」代理信号起步，原方案的「读 task_bindings/<session_id>.json 绑定落盘」方案 deferred——session 生命周期短，落盘文件堆积需清理逻辑，违反「显式优于缓存」。
2. 措辞从纯回看式改为混合式。

**明确不做**（grill 定案）：PreCompact——UserPromptSubmit 是其超集（压缩后下一条指令即重新注入）；Stop+block——Stop 无 transcript 无法验证该不该 block，盲 block 每轮加延迟、mtime 启发式必误伤、有死循环风险，且停顿点判据是语义判断只有模型能做，与 Stop 的语法位置对不上。

## 措辞：混合式一行两职

用户质疑「为什么提示上一轮而不是提醒本轮记得」后修正为混合措辞：`[active-settle] 若上一轮命中停顿点（里程碑/决策落定/话题转向）且尚未沉淀，先 add_task_memory / ingest_note(draft) 补写再回答；本轮收尾按主动沉淀协议自查。`

回看补写是 hook 的独有价值（UserPromptSubmit 触发时上一轮已完结、内容全在上下文，判断窗口与行动窗口重合）；纯前瞻提醒等于把 AGENTS.md 协议换个位置再说一遍，注意力稀释问题原样复现；纯回看式有滞后一轮的盲区（会话末轮无下一条指令），前瞻尾巴衔接协议块弥补。

## Rationale

协议全文留 AGENTS.md 定义规则，hook 每轮注入一行触发器执行提醒——规则与触发分离。真机验证：提交后本会话下一条用户消息即触发 `[active-settle]` 注入。
