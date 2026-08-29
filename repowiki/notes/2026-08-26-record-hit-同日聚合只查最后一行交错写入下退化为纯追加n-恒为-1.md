---
type: pitfall
title: record_hit 同日聚合只查最后一行，交错写入下退化为纯追加（n 恒为 1）
tags:
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - mcp/tools/telemetry
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-repowiki-.meta-telemetry-Administrator..md
  scene: telemetry 统计修复
  consolidated_into:
  - wiki/scenarios/代码评审与分析工具方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 21:57:39+00:00
stale_after: '2027-02-22'
origin: conversation
verified:
- by: human:Administrator
  at: '2026-08-26T04:31:04Z'
---

## Background

`record_hit` 声明按 (user, doc, day) 聚合、行数有界，但实际只检查**文件最后一行**：

```152:164:codewiki/mcp/tools/telemetry.py
    if lines:
        try:
            last = json.loads(lines[-1])
```

而 `query_wiki` 一次返回多个文档，`_record_retrieval_stats` 对每个结果**逐个**调用 `record_hit`。上一次记录的最后一行几乎不可能是本次的同一 doc，于是「同 (doc, day) 合并」永远不命中 → 全部追加新行、`n` 恒为 1，与 docstring 声明的聚合设计不符。

## 正确做法

合并逻辑改为全文件**倒序扫描**，命中同 (doc, day) 的 hit 行就原地累加 `n`：

```
for i in range(len(lines) - 1, -1, -1):
    if ev.get("t") == "hit" and ev.get("doc") == doc_path and str(ev.get("at", "")) == today:
        ev["n"] = int(ev.get("n", 0) or 0) + int(count)
        merged = True
        break
```

前提：`_atomic_write_lines` 本来就是整文件重写，扫描全文件不增加 I/O 成本。

## Root cause

「尾部最后一行合并」优化假设「同 doc 的连续写入相邻」，但调用方（`query_wiki` 多结果逐个 `record_hit`）的交错写入打破了这一假设，使优化退化为纯追加。

## 验证

模拟 3 轮交错写入 + 4 次重复命中 → 3 行，`n` 分别为 7/3/3；存量归并 3 个 jsonl（Administrator 48→28、mambo-wang 26→23、local 10→10），hits 总数不变；全量测试 384 passed 无回归。
