---
type: pitfall
title: "溯源审计脚本三个口径坑：reject_reason 在顶层且中英并存、空串链接、严格与宽松解析"
tags: ["pitfall"]
metadata:
  date: 2026-11-14
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["MCP_Tools_Knowledge"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的.md"
  scene: "笔记退役与溯源审计脚本"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-14T01:36:14Z }
stale_after: 2027-05-13
origin: conversation

---

## 背景

为量化「更正传播」缺口写一次性溯源扫描脚本（/tmp/scan_provenance.py）时，初版结果严重误判，修正后才得到可用数据。三个口径坑可复用于任何笔记状态/溯源审计。

## 坑 1：退役原因在顶层 reject_reason，且中英两种写法并存

- `reject_note` 把原因写进 frontmatter **顶层** `reject_reason`（`codewiki/mcp/tools/note_writer.py:197-199`；`wiki_lint.py:125` 容忍为 legacy 键），**不在** `metadata.disposition.reason`。
- 语料里两种写法并存：协议词表是英文 `consolidated into <scene title>`（`note_consolidation.py:104-105,454-455`），实际大量笔记写的是中文 `聚合进场景：<标题>`。
- 只查 metadata 或只匹配英文 → 把正常吸收退役误判为「失效」。会话初版扫描把 118 条场景块源引用判为 invalidated 且多数显示「无原因记录」；改用顶层 reject_reason + 中文关键词后，带下游链接的笔记状态分布为 absorbed_retired 113 / ok 18。
- 吸收判别关键词须含中文：聚合/吸收/并入/成块/归入/合并进 + consolidated；**无 reason 的 deprecated 单列为「可疑」**，不能默认无害。

## 坑 2：空串链接必须过滤

`consolidated_into` / `compiled_into` 存在空串值（会话实测 148 条 consolidated_into 中 26 条空串、22 条 compiled_into 中 6 条空串，非空断链 0）。取列表时若把空串当条目（得到 `['']`），审计会把它们全判成 dangling 假断链。

## 坑 3：严格 YAML 与宽松子串解析口径不同，报数必须声明口径

同一批 11 个场景块：严格 YAML 解析 → 9 块成功、102 refs、0 断链，2 块整体解析失败（frontmatter 结构性损坏）；宽松子串解析器 → 124 refs、3 条截断断链。两个口径都成立但结论不同：严格口径说「两块不可审计」，宽松口径说「3 条断链」。审计报数必须写明用的是哪种解析。

## Rationale

口径错会把「正常吸收退役」报成「更正传播缺口」，直接导致错误立项；这三个坑都不在代码注释里，只能从数据实测撞出来。
