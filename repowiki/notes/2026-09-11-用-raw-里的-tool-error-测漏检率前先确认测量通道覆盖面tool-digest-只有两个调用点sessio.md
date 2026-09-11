---
type: lesson
title: "用 raw 里的 [tool-error] 测漏检率前，先确认测量通道覆盖面：tool_digest 只有两个调用点，session-end 补采集不经过它"
tags: ["lesson"]
metadata:
  date: 2026-09-11
  task_id: 他山之石
  related_modules: ["capture", "tool_digest", "hooks"]
  severity: medium
  source_ref: "conversations/conv-继续调研.md"
  scene: "采集覆盖率探测 / 借鉴调研证伪"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:21:09Z }
stale_after: 2027-03-10
origin: conversation

---

## 背景

上一轮用「8 条 raw 中仅 1 条含 `[tool-error: …]`、漏检率 0%」来论证采集层没有漏掉工具失败信号。复核发现这个结论的口径是错的。

## 事实（2026-09-11 代码核对）

`[tool-error: …]` 这类行**只由 `codewiki/src/tool_digest.py` 的 `digest_blocks` 产生**，而它全仓只有两个调用点：

- `codewiki/mcp/_ide_hook.py:268`（导入）/ `:273`（调用）—— IDE hook 采集通道；
- `codewiki/mcp/tools/capture_conversation.py:210`（导入）/ `:222`（调用）—— MCP 主动采集通道。

**session-end 的 transcript 补采集不经过 `tool_digest`**。所以「raw 里有多少条含 tool-error」测的是**这两条通道覆盖了多少会话**，不是「失败信号有没有被漏检」。加大样本只是在放大同一个偏差。

## 正确做法

任何「从产物反推覆盖率/漏检率」的探测，先按这个次序：

1. **先回答「这个信号在几条通道上被采集、各覆盖多少会话」**（覆盖面）；
2. 再谈样本量与漏检率；
3. 结论里必须标注样本量与翻转条件（例如「n=1，只能写未观测到缺口，不能写已证否」）。

## 关联

与 lesson『探测脚本用小样本算出 0% 漏检，不能当成缺口已证否』是同一问题的两层：那条讲样本量不足（统计层），本条讲更靠前的一层——测量通道本身没覆盖到（覆盖面层）。两层放一起读才不会被误用；若决定合并，本条内容可作为「附：通道覆盖面」章节并入那条，不丢信息。

## 适用范围

采集/日志类功能的覆盖率评估、以及任何「用已有数据反推缺失」的调研结论。
