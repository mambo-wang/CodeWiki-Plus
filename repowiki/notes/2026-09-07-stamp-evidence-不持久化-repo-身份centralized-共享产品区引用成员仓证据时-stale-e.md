---
type: pitfall
title: stamp_evidence 不持久化 repo 身份：centralized 共享产品区引用成员仓证据时 stale_evidence 误报 file
  disappeared
tags:
- pitfall
metadata:
  date: 2026-09-07
  related_modules:
  - evidence
  - workspace
  - lint
  severity: medium
  source_ref: conversations/conv-本周改动有点大，请把CODEWIKI-MCP整体测试一遍，重点测试最近一周的改动.md
  scene: MCP 整体测试
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:04:02+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:18Z'
---

## 背景

2026-09-02 E2E 验证「P0 证据锚定 × 多仓 centralized 布局」时发现：`stamp_evidence` 接受 `repo_path` 但证据记录不持久化 repo 身份；`lint_wiki` 的 `_check_stale_evidence` 只能从 `output_dir.parent` 猜 repo 根。

## 症状

- 主流程正常：colocated 布局与 centralized 成员仓各自的 repowiki（`<ws>/<name>/repowiki`）下，`output_dir.parent` 恰为 repo 根，lint 无误报。
- 误报场景：centralized 的**共享产品区**（`<ws>/repowiki`）页面引用成员仓证据时，被误报 `evidence file disappeared`（此时 output_dir.parent 是 workspace 根，不是任何成员仓根）。
- `workspace.json` 结构只有 `wiki_layout`，无成员仓映射可查。

## 修复方向（当时建议，未实施）

让 stamp_evidence 持久化 repo 身份（写入证据记录），或让 lint 读 workspace.json 的成员仓映射。`test_evidence.py` 当时无 centralized/repo 映射覆盖，是测试缺口。
