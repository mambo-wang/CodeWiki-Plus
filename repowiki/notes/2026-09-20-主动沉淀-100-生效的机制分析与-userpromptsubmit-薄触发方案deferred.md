---
type: decision
title: "主动沉淀 100% 生效的机制分析与 UserPromptSubmit 薄触发方案（deferred）"
tags: ["decision", "userpromptsubmit"]
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 他山之石
  source_session: "1b5f06c022ab4dcd9dfabc02661535f2"
  related_modules: ["mcp/_ide_hook", "hooks/task_session_start"]
  severity: medium
  source_ref: "conversations/conv-working_memory_content-The-following-is-the-existing-working-848ca6.md"
  scene: "主动沉淀协议生效链路优化"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.10.1, at: 2026-09-20T15:49:58Z }
stale_after: 2027-09-20
origin: conversation

---

## Background

ADR-0015 落地后用户追问：如何让 AGENTS.md 的主动沉淀协议 100% 生效？机制分析：协议生效链路是「AGENTS.md 协议块（会话开头加载一次）→ 模型每轮收尾自查」，断点在第二环——协议确实进了上下文，但会话进行 30 轮后开头的协议在注意力上被稀释，模型「想起来」是概率事件。

## 方案（已设计，用户拍板暂不实施）

**规则与触发分离**：协议全文留在 AGENTS.md / `get_prompt("task-workflow")`（定义规则），UserPromptSubmit hook 每轮注入一行触发器（执行提醒）：

```
[active-settle] 回答前自查：上一轮是否命中停顿点（里程碑/决策落定/话题转向）？
命中且未沉淀 → 先 add_task_memory / ingest_note(draft) 补写，再回答。
```

设计要点：
1. **条件化降成本**：hook 读 `repowiki/.meta/task_bindings/<session_id>.json`，只在有任务绑定的会话注入，未绑定零开销；每轮约 40 token。
2. **复用现有注册**：`_ide_hook --enable` 已挂在 UserPromptSubmit 上（技能草稿提示在用），扩展输出分支即可，不新增注册条目。
3. **通道选型依据**：UserPromptSubmit 注入紧贴新 prompt、注意力最鲜，且停顿点在时间上几乎总对应「上一轮结束、新 user 消息到来」；SessionStart 与 AGENTS.md 同病（开头注入中途稀释）；Stop + block 是唯一强制手段但每轮加延迟、有循环风险、CodeBuddy 语义未真机验证，不推荐。
4. **诚实的天花板**：prompt 注入永远是软约束，「百分百」只有 Stop-block 能做到但代价不成比例；此方案把命中率从「靠模型自觉」推到「每个停顿点都有新鲜提醒」，是成本收益比最优档。

## 状态

用户明确「暂时不做」。方案已备好，实施时改动面：`_ide_hook.py` 加 active-settle 提醒分支 + 测试补断言。若实施，ACTIVE-SETTLE 块可进一步瘦成 3 行指针（触发靠 hook，规则靠 prompt）。

## Rationale

这是对「提示词协议为什么不会 100% 生效」的机制性认知 + 一个完整可拾起的 deferred 方案，下次提升主动沉淀命中率时直接从此实施，不必重新设计。
