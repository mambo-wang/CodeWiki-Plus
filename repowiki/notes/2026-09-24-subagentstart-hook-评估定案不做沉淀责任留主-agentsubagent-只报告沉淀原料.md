---
type: decision
title: SubagentStart hook 评估定案：不做，沉淀责任留主 Agent，subagent 只报告沉淀原料
tags:
- decision
- subagentstart
metadata:
  date: 2026-09-24
  confidence_level: weak
  task_id: 他山之石
  source_session: 1b5f06c022ab4dcd9dfabc02661535f2
  related_modules:
  - mcp/prompts
  - cli/utils/ide_config
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-670adf.md
  scene: 通用 subagent（编码/调研/测试/review）要不要注入沉淀提示
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-24 13:00:17+00:00
stale_after: '2027-09-25'
origin: conversation
verified:
- by: human:iamwangbao
  at: '2026-09-25T13:32:41Z'
---

## Background

用户提出：编码/调研/测试/review 等用户自定义任务常以 subagent 方式执行，是否应在 SubagentStart hook 注入提示词让 subagent 沉淀记忆和经验。评估后定案不做（提交 11a57fb 只改 prompt 约定）。

## Decision

**不让 subagent 直接沉淀，让它「报告沉淀原料」，沉淀责任留在主 Agent**：

1. **确认闸门会断裂**：subagent 跑完即销毁——直接 `ingest_note(draft)` 则草稿没人确认悬死草稿区；直接 `add_task_memory` 则直写无需确认，而 subagent 上下文最窄、没有任务级视野做四问过滤（「其他 Agent 能否受益」需要全局视角），并发多个 subagent 还会灌爆 40 条/24KB 压缩阈值、触发近重复拒绝。
2. **沉淀时机不在 subagent 里**：主 Agent 收到 Task 返回值（或 team 的 send_message）那一刻就是天然停顿点，已被现有 active-settle 通道覆盖（UserPromptSubmit 回看提醒 + 收尾轮兜底）。
3. **SubagentStart 事件 CodeBuddy 支持未验证**，为架构上就不对的方向付验证成本不值。

**正确增强点（不需要 hook）**：主 Agent 发 Task 时 prompt 末尾加一句「返回结果时报告三件事：做了什么、关键发现、值得沉淀的经验（若有）」——已写入 `get_prompt("task-workflow")` 的「会话进行中」节。subagent 只携带原料（它本来就要写返回值），过滤、查重、落盘全在主 Agent，符合「工具做簿记，推理决策在调用方」。

## Rationale

例外不冲突：distill-worker 本身就是沉淀 worker，协议在定义文件里，产出草稿仍由主 Agent 确认，闸门未断。未来若 subagent 种类变多且定义文件出现重复 boilerplate，SubagentStart 注入可收敛该重复——触发条件是重复真出现且真机验证过事件支持，现在做属 YAGNI。
