---
type: decision
title: 任务记忆系统 grill 决策：绑定按 source_session_id 维度，注入走起 session 引导而非 hook 自动注入
tags:
- codewiki
- decision
- sessionstart
- sessionstore
metadata:
  date: 2026-08-15
  related_modules:
  - task_manager
  - _ide_hook
  - capture_conversation
  - session
  source_ref: raw\conv-调研一个需求：参考tencentdb-agent-memory设计咱们Codewiki-Plus的记忆系统，效果比如说用.md
status: stable
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 13:17:26+00:00
stale_after: '2026-11-13'
origin: conversation
verified:
- by: codewiki/5.2.2
  at: '2026-08-15T13:26:10Z'
---

## 背景

设计 CodeWiki 任务记忆系统（参考 TencentDB-Agent-Memory）时，通过 grill-me 逼出方案的 4 个黑洞，逐一拍板决策。

## 4 个黑洞与最终决策

1. **task_id 生命周期**：最初用 slug 当主键但无重名/重命名/删除处理 → 拍板「不允许同名、不允许重命名、提供 delete_task」；删除级联 = 保留经验笔记（知识资产）+ 删 raw 原文 + `get_task_context` 返回「任务不存在」。
2. **「hook 自动注入」是伪通道**：CodeWiki 是 MCP server，**无法修改 IDE 的 system prompt**（参考项目能注入是因为请求层有 `context-injector.ts`，CodeWiki 没有这个层）。`_ide_hook` 只在会话结束时跑，无法把内容塞进下一会话 prompt。→ 砍掉伪通道，注入走「起 session 引导」路线（新增 SessionStart 处理）。
3. **会话绑定锚点**：`SessionStore` 是内存态（TTL 2h），全局单值 `active_task.json` 在多窗口并发下会**静默数据污染**（窗口 B 后写覆盖 A，A 的对话被记到 B 名下）。→ 绑定按 `source_session_id` 维度存 `.meta/task_bindings/<source_session_id>.json`，与 capture 的 supersede 锚点对齐，多会话天然隔离。
4. **起 session 提示的触发者**：参考现有 SessionEnd hook 的 CLI+stdin 接线方式新增 SessionStart；AGENTS.md 直接改写有并发写冲突风险且依赖 LLM 遵守指令（概率性）。

## 根因

方案最初的「hook 自动注入 + 全局 active_task.json」是把参考项目的请求层能力（`context-injector.ts`）和 SessionBinding（有 userId/teamId 维度）错误映射到无状态的 MCP 工具架构上。CodeWiki 工具无状态、参数显式传递，唯一稳定的会话锚点是 IDE 侧 `source_session_id`。
