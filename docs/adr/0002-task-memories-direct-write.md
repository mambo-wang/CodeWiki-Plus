# 0002. 任务记忆直写落盘，不设确认闸门

日期：2026-08-24
状态：已接受

## 背景

任务记忆蒸馏链路原本与笔记共用确认闸门：`distill_conversation` 产出的 memories 先暂存
`pending-memories.json`，经用户 `confirm_task_memories` / `reject_task_memories` 才落盘
`memories.md`（stage/confirm/reject/list_pending 四工具支撑）。使用者反馈"经验需要确认，
记忆可以不用确认"，重新评审该设计。

## 决策

任务记忆（task memories）蒸馏后**直写落盘** `memories.md`（带时间戳头的原子追加写），
不设确认闸门；笔记（notes）的 confirm_note/reject_note 闸门保持不变。
stage/confirm/reject/list_pending 四工具与 pending-memories.json 暂存机制彻底退役。

## 理由

1. **风险等级不同**。确认闸门防的是"噪声进全局知识库"：笔记进 query_wiki 检索、进
   health score、跨任务跨会话可见，一条错误笔记有长尾误导成本。任务记忆不进检索、
   作用域锁死在单个任务、随 delete_task 级联清除——噪声成本天然有界、随任务生命周期
   衰减。闸门成本（打断用户评审进度性内容）与其防的风险不成比例。
2. **与 ADR-0001 的压缩决策同构**。P1 已拍板 compact_task_memories 直写不走闸门，理由
   即"可逆、低风险、进度性内容不配人工评审成本"。任务记忆整体属于该风险类别。
3. **消除真实摩擦**。每个有补蒸馏的会话都需在自然停顿点打断用户展示待确认记忆；
   distill-worker subagent 的职责有一半是搬运这套确认仪式。直写后工作流少一环。
4. **业界参照一致**。TAM、OpenViking 的记忆提取均为无闸门直写；teamai 为直推 +
   事后治理。事前评审是 CodeWiki 对知识库可信度的选择，不是记忆系统的通行做法。

## 已知限制

- 直写后无删除工具：蒸馏产出错误或无价值的条目时，纠错手段暂时只有删除整个任务。
  若实际出现该需求，补 `remove_task_memory` 做事后治理（teamai prune 思路）。
- 存量 `pending-memories.json` 中未确认的条目随本决策废弃，不做迁移（已确认的条目
  已在 memories.md 中；未确认的条目本来就是被评审否决风险的候选）。

## 后果

- `distill_conversation` 响应字段由 `memories_staged`/`memories_pending` 改为
  `memories_written`；`get_task`/`get_task_context` 响应移除 `pending_memories` 字段。
- 调用方（IDE Agent、distill-worker subagent、sessionStart hook 注入文案）同步更新：
  待确认清单只剩草稿笔记。
