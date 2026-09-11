---
type: architecture
title: "repowiki/.meta/telemetry/*.jsonl 只记 wiki 检索命中，不含 MCP 工具调用数据"
tags: ["architecture"]
metadata:
  date: 2026-09-11
  task_id: Cli能力
  related_modules: ["telemetry", "mcp", "lint"]
  severity: high
  source_ref: "raw\\conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md"
  scene: "工具调用量统计与遥测"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:12:18Z }
stale_after: 2027-09-11
---

## 事实

`repowiki/.meta/telemetry/<user>.jsonl`（如 `wangbao.jsonl`、`local.jsonl`）是**检索侧**遥测，每条记录的字段是 `{"t": <类型>, "doc": <文档路径>, "at": <日期>, "n": <次数>}`。

类型只有三种：

- `hit` —— wiki 检索命中（占绝大多数，如 429 条）；
- `by_file` —— 按文件查知识时间线（如 24 条）；
- `adopted` —— 检索结果被采纳（如 8 条）。

**里面没有 MCP 工具调用记录**：没有工具名、没有调用次数、没有会话维度。2026-09-11 复核仍只有这三种 `t` 值。

## 影响

- 任何「按实测调用频次决定保留/裁剪哪些 MCP 工具」「按调用量给工具排名」的需求，**目前无数据支撑**，只能人工判定，或先新增埋点。
- 想做工具调用量统计，得在 MCP 层（入口/分发处）新增写入，而不是读这个 jsonl——它记录的是「知识被查到没有」，不是「工具被调了几次」。

## 适用范围

评估工具裁剪、设计遥测埋点、以及任何引用 telemetry 做决策的场合：先确认记录类型，别把检索命中当成工具调用频次。

## 关联

与『record_hit 同日聚合只查最后一行，交错写入下退化为纯追加』互补：那条讲 hit 记录怎么写（写入机制 bug），本条讲这个文件里**有什么、没有什么**（没有工具调用维度）。
