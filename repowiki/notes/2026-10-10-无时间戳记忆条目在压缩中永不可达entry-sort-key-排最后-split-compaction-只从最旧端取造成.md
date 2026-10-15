---
type: pitfall
title: "无时间戳记忆条目在压缩中永不可达：entry_sort_key 排最后 + _split_compaction 只从最旧端取，造成字节阈值卡线与压缩抖动"
tags: ["pitfall"]
aliases: ["压缩抖动", "无日期条目不可压", "memories 字节阈值卡线", "entry_sort_key 死重"]
metadata:
  date: 2026-10-10
  confidence_level: weak
  task_id: 产品维护
  related_modules: ["task_manager", "store"]
  severity: medium
  reason: "停顿点即写即沉淀：本轮实测定位的新 pitfall，需用户确认后才进检索语料"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.14.1, at: 2026-10-10T09:58:37Z }
stale_after: 2027-04-08
---

## 背景
任务记忆热层有两条硬阈值（`codewiki/mcp/tools/limits.py`）：40 条 / 24576 B，且仅当 `total_entries > keep(20)` 时 compaction_needed 才为真；`_split_compaction` 按「superseded 优先 → 其余按时间最旧优先」取走 `len - 20` 条进摘要，keep 窗口始终是「最近 20 条」。

## 现象（2026-10-10 本仓实测）
`repowiki/tasks/产品维护/memories/iamwangbao-163-com.md` 里三块**无时间戳标题**的条目（一块旧摘要正文 `### 本轮追加压缩（截至 2026-10-05…）` + 两份重复的 `### 2026-08-26 会话蒸馏完成…`）：
- 分片已 27391 B，越线 24576 B，每追加一条就立刻重新触发一轮压缩；
- 但每轮只能吞掉 **1 条有日期的真条目**（实测：compressed=1 / kept=20），那三块死重原地不动。

## 根因
两个不变量合起来把无日期条目变成了「永不可达」：
1. `entry_sort_key`（`codewiki/src/store.py:327`）——能匹配时间戳的条目返回 `(0, ts)`，匹不上的返回 `(1, "")`，**无日期条目恒排最后**；
2. `_split_compaction`（`codewiki/mcp/tools/task_manager.py:1216`）——compress 集从**最旧端**取 `len - COMPACTION_KEEP` 条。
于是无日期条目永远落在 keep 窗口内，而它们往往正是历史上格式事故（旧摘要正文被当条目解析、重复追加）的沉积物——越旧越洗不掉。

## 影响
- 分片体积被死重顶在字节线上，压缩频率与条数解耦（append-only 写侧每轮都越阈），而每轮压缩是一次异步子代理调用（实测单轮 25 万 ~ 69 万 subagent token）——性价比极差。
- 表面上「压缩在工作」，实际热层里反复被归档的都是最新的有效条目，旧事故块反而永驻。

## 正确做法（待实施，本笔记只记录已核实现状）
- 一次性：把无日期死重先归档到 `memories-archive/`、再从热层摘除（走 `locked_rmw`，不手写文件）；
- 根治：`_split_compaction` 的候选队列改为 superseded → **无日期条目** → 有日期最旧，使历史格式事故可被后续压缩自然洗掉；配套加「单次最少压缩 N 条」下限避免字节阈值边界抖动；两者需同步修订 ADR-0009 D8 口径与 `tests/test_task_memory_search.py` / `tests/test_task_manager.py` 的驱动测试。

## 相关
上游成因见「user_id 解析链整条依赖进程环境…」（同一人切成两分片、退化通道写错路径）与压缩摘要标题重复那类格式纪律问题。
