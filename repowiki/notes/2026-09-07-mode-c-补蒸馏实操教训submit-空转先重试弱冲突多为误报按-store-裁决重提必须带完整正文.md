---
type: lesson
title: Mode C 补蒸馏实操教训：submit 空转先重试、弱冲突多为误报按 store 裁决、重提必须带完整正文
tags:
- lesson
metadata:
  date: 2026-09-07
  related_modules:
  - distill
  severity: medium
  source_ref: conversations/conv-teammate-message-from-team-lead-from-summary-Initial-task-as-2.md
  scene: Mode C 补蒸馏实战
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:05:02+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:15Z'
---

## 背景

2026-09-05 一次 distill-worker 补蒸馏实战（22 条无归属 raw，Mode C 纯 MCP JSON）中沉淀的三个操作性教训。

## 教训

1. **内联 submit 偶发空转**：submit 返回 `missing_result` 且 `notes_created=0`，但重试相同载荷即成功——首次遇到先核对 raw 是否仍 pending、有无草稿被创建，重试一次确认可复现再深查，避免误判参数形态错误而改道。（与既有「submit MCP 超时不幂等」笔记是不同现象：那条是超时后仍执行致重复写入，本条是返回 missing_result 实际未执行。）
2. **弱冲突多为 BM25 误报**：提交新笔记常触发 conflicts_pending，候选笔记仅因个别词面重叠（L0/L1 编号撞词、sources 术语撞词等）；逐一 read_file 核对候选后，主题不同的一律 `dedup_action=store` 强制入库。裁决重提时**必须携带完整笔记正文**（重提的 content 会覆盖首轮草稿内容，只写裁决说明会把草稿正文覆盖成说明文字）。
3. **prepare 清单文件名可能与磁盘不符**：按 full_path 读文件报不存在时，列 raw 目录核对实际文件名，或重新 prepare 拿最新准确清单（已处理的会从清单消失）。

## 适用范围

codewiki distill_conversation Mode C 补蒸馏（主 Agent 委托 subagent 的场景）。
