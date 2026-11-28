---
type: pitfall
title: "task_session_start.py 两个已评审确认的 Low 级遗留问题：raw 索引回退过时归属、异步弹框后任意文本被当答案"
tags: ["pitfall"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  task_id: 他山之石
  source_session: "374cbbe2c2ab47a2a7f4b140b49205d7"
  related_modules: ["task_session_start", "hooks"]
  severity: medium
  source_ref: "conversations/conv-@command-open-code-review-delegate-拉取最新代码并review最近一次提交.md"
  scene: "code review 遗留问题跟进"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:30:17Z }
stale_after: 2027-05-27
origin: conversation

---

## Background

对 commit `0ac6081`（fix: 续接会话时避免重复选择任务）的 code review 给出 Approve，但发现两个不阻塞合入的 Low 级遗留问题，尚未修复。

## 已知问题（截至 2026-11-26 review）

1. **raw 索引回退可能返回过时归属**（`codewiki/hooks/task_session_start.py:835-842`）：回退逻辑用 `reversed(files)` 找「最新一条带 task_id 的条目」，但若同一 session 有更新的采集条目且其 `task_id` 为空（会话末尾已解绑），旧条目的 task_id 仍会被返回——归属过时。建议改为先取最新匹配条目、再判断它是否有 task_id。该回退只服务旧版本数据，影响面小。
2. **异步弹框后的任意用户文本都被当作答案**（`task_session_start.py:773-783`）：`pending_choice_async` 置位后，下一条用户纯文本无条件进入 `_classify_choice`；无关消息（如「先帮我修个 bug」）会被分类为 `new`（未命中任何任务）→ `saw_create=True`，之后 agent 直接绑定已有任务会被 766 行拒绝、退回弹框。行为保守可接受，但应在 docstring 注明该启发式假设。

## Rationale

这两个是已定位、有行号、有建议修法的已知问题；后续任何人改 task_session_start.py 或排查「续接会话仍弹框/任务归属不对」时应先对照本清单，避免重复定位。

## 正确做法

跟进修复时：问题 1 改回退取条目顺序；问题 2 至少补 docstring 说明启发式假设。修复后应补充对应测试（现有 41 项测试未覆盖这两个边界）。
