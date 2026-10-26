---
type: pitfall
title: "Better Harness 报告三件套：canvas.json 存数据、report.canvas.tsx 是固定模板，正文可能与结构化字段脱节"
tags: ["pitfall"]
aliases: ["better-harness 报告结构", "report.canvas.tsx 固定模板", "evidenceBoundary 与 overview 不一致"]
metadata:
  date: 2026-10-26
  confidence_level: weak
  severity: medium
  root_cause: "report.canvas.tsx 是 Qoder Canvas 的固定查看器（import canvasData from \"./canvas.json\"），结论数据在 canvas.json 与 findings.json；overview 由判读环节撰写，evidenceBoundary 由采集环节写入，两者可分别更新"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.2, at: 2026-10-26T02:17:22Z }
stale_after: 2027-04-24
---

## 现象

同一仓库跑两轮 `/better-harness`，`.qoder/better-harness-runs/<run>/` 下都是三个文件：`canvas.json`、`findings.json`、`report.canvas.tsx`。两轮 findings 差别很大（5 条 / 8 条，12,114 B vs 26,501 B），两份 `report.canvas.tsx` 却逐字节相同（md5 均为 `24bc7eaa608c3c5dceb8b0e581a7e847`，均 80,906 B）。

## 根因

TSX 里是 `import canvasData from "./canvas.json"; const report = canvasData;`——它是 Qoder Canvas 的固定查看器，数据来自同目录的 `canvas.json`。README 只提 findings 与 TSX 两件产物，不含 `canvas.json`，但校验器读的偏偏是它（markdown 模式与 `--validate` 互斥也源于此）。

## 陷阱

第二轮报告的 `summary.overview` 写着「录取 56 个会话、248 个 Task Episode」，同一份 `canvas.json` 的 `summary.evidenceBoundary.manifest.selection.eligibleCount` / `analyzedCount` 与 `episodeCoverage.episodeCount` 仍是 0，`evidenceMode` 仍是 `session-limited`。正文判断和采集边界可以各写各的。

## 正确做法

1. 验收报告看三处：`summary.overview`（判读结论）、`summary.evidenceBoundary`（真实采集边界）、`summary.dimensions`（分数）。
2. 不要拿 `report.canvas.tsx` 的内容或大小判断结论是否更新——它恒为同一份模板。
3. 改结论要同步 `findings.json` 与 `canvas.json`（两者都含 summary + findings）。

