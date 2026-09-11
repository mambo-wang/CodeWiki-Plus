---
type: architecture
title: "借鉴调研的排除判据：本仓是本地 markdown + git 版本化 + 同步 MCP 的主动不同取向，服务端/队列/多租户类候选不是缺口"
tags: ["architecture", "openviking"]
metadata:
  date: 2026-09-11
  task_id: 他山之石
  related_modules: ["repowiki", "mcp", "research"]
  severity: medium
  source_ref: "conversations/conv-继续调研.md"
  scene: "他山之石增量调研处置"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:21:54Z }
stale_after: 2027-09-11
origin: conversation

---

## 背景

2026-09-11 完成 11 个借鉴项目的整体增量调研（`docs/借鉴项目整体增量调研报告-2026-09.md`）：44 个候选 → **0 采纳 / 15 deferred / 29 excluded**。这个分布不是调研失败，而是有稳定的排除判据在起作用。

## 三条判据

**1. 本仓已有 → 直接排除（占比最高）。** 最典型：OpenViking 的 auto-recall 超预算丢弃被列为候选时，本仓 `codewiki/mcp/tools/injection_budget.py:1` 的 docstring 第一行就写着「V2, OpenViking auto-recall 借鉴」——早已落地。同类还有 6 个：`deprecated` ≈ 墓碑、SHA-256 内容指纹 ≈ 内容坐标 upsert、多信号确定性排序、git ≈ 修订历史等。**列候选前先 grep 本仓，是收益最高的一个动作。**

**2. 模型不同 → 不是缺口，是取向不同。** 他仓集体往服务端/常驻队列/多租户/计费分区走；本仓是**本地 markdown + git 版本化 + 同步 MCP，没有常驻写入端**。因此队列自愈、计费归因、「任务记录缺失即视为已删除」这类候选一律排除——它们解决的问题在本仓不存在。判断句：先问「本仓有没有这个问题的数据面/进程模型」，没有就排除，而不是记成 deferred 慢慢烂。

**3. 真正在动的主线要挑出来单独看。** 五个项目不约而同地把「成本/预算从软约束变硬约束」（注入预算、扫描预算、分页不丢信息、按优先级分配预算）。本仓 `injection_budget` 已覆盖注入侧，**空档在扫描侧预算**与「deprecated 笔记会不会被新 ingest 复活」。

## deferred 的三种去向（候选必有去向）

- **留档照抄**（9）：真做时直接抄实现，如输入过滤「无配置即恒等 + 编译失败不抛」、增量「基线失效兜底（rev-parse 失败回退工作区 diff）+ 单源失败仍写 state」、去重 Jaccard 预筛（TopK + 小语料直接跳过）、无损分页只在 `end < allowed_count` 才发 cursor。
- **转其他任务**（1）：跨仓 workspace manifest 审批（内容摘要做审批键、变更即失效）→ 转「多仓工作区」裁决，related ≠ same。
- **自查项**（3）：wikilink 重写是否按代码围栏切分、ADR 回写是不是整文件重写、deprecated 笔记是否会被后续 ingest 复活。

## 适用范围

下一轮借鉴调研的候选处置，以及任何「把别家能力当成我们缺口」的判断——先证伪、再分类、排除必填原因。

## 关联

与『借鉴调研先证伪』（讲顺序纪律）、『他山之石增量调研流程』（讲五步操作骨架）、『repowiki 是随代码版本化的资产』（讲单个架构事实）互补：本条讲的是**候选怎么分到 adopted/deferred/excluded 及排除理由怎么写**，是处置层而不是流程层。
