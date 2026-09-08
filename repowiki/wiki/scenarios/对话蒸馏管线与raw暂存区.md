---
type: Scenario
title: 对话蒸馏管线与raw暂存区
description: 蒸馏三模式汇聚点、distilled_file 侧通道、L0 链接优先零索引、subagent 回报须复核、Mode C 冲突裁决与重提纪律
tags:
- CodeWiki-CN
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:54:25+00:00
stale_after: 2026-12-07
aliases:
- 对话蒸馏管线与raw暂存区
status: stable
metadata:
  generated_from: f08feab
  resource: repo://CodeWiki-CN
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
  source_notes:
  - notes/2026-09-05-蒸馏-subagent-自报的笔记状态不可信需用-get-task-context-的-related-notes-状态.md
  - notes/2026-09-07-mode-c-补蒸馏实操教训submit-空转先重试弱冲突多为误报按-store-裁决重提必须带完整正文.md
  summary: 补入 subagent 落盘状态必须独立复核、Mode C 空转重试与冲突裁决重提须带完整正文
  heat: 4
---
## 工作场景
`distill_conversation` 蒸馏管线与 `repowiki/raw/` 暂存区生命周期，含委托 subagent 补蒸馏的结果验收。适用于改蒸馏逻辑、排查 raw 去向、宿主 agent 执行 Mode C 批量蒸馏、对话归档与溯源设计。

## 适用条件
给蒸馏产物加逻辑、写 raw 相关测试、Mode C 多文件蒸馏、验收 subagent 蒸馏结果。

## 核心 SOP
1. 给蒸馏产物加逻辑只改 `_process_llm_output` 一处：A/B/C 三模式都汇聚到这里。
2. raw 去向两条路径：`no_knowledge`（notes=[]）按设计直接删除；`keep_raw=true` 是唯一保留途径。
3. Mode C 多文件蒸馏纪律：逐文件读 → submit 落盘 → 立即触发上下文压缩 → 下一个文件。
4. **MCP 参数长度受限走 `distilled_file` 侧通道**：先把蒸馏 JSON 写入 `repowiki/raw/.distill-*.json`，submit 只传小路径；不写临时 Python 脚本直连 handler。
5. 无知识密度的对话也提交空结果（`{"notes": [], "memories": []}`）让工具走归档清理，否则 raw 一直滞留。
6. **L0 归档链接优先、零索引**：蒸馏成功搬家到 `repowiki/conversations/`，归档层不建 BM25 索引；`query_wiki` 命中时经 `metadata.source_ref` 按需回读，蒸馏后把笔记 source_ref 从 `raw/` 改写为 `conversations/`。
7. raw 索引 `.index.json` 的 `task_id` 统一去引号（`_rebuild_index` 与 `pending_raws_by_task` 复用同一 `_unq`）。
8. **subagent 回报的落盘状态一律当线索**：用 `get_task_context` 的 `related_notes[].status` 或直接读 notes frontmatter 复核；`draft` 未 confirm 前只能只读参考，直接采信即构成一次静默确认。
9. **Mode C 三条实操**：submit 返回 `missing_result` 且 `notes_created=0` 先原样重试一次（与「超时不幂等」不同，本现象是实际未执行）；`conflicts_pending` 多为 BM25 词面误报，逐条核对后 `dedup_action=store`，**重提必须带完整笔记正文**（否则草稿正文被裁决说明覆盖）；prepare 清单文件名与磁盘不符时列 raw 目录或重新 prepare。
10. Phase 5 方向：资产置信分层（strong/weak/shadow）+ 负反馈闭环（`flag_misrecall` 达阈值自动降权）。

## 判断逻辑
- 借鉴外部记忆管线：借分层不借 LLM、借模式不借 hook、借粒度不借无闸门。
- 归档不进索引 → 无全量重建成本与检索噪音；对话是低信噪比文档，混入默认检索会挤掉高价值结果。
- `dedup_action` 只解决与候选笔记的重复冲突，与 draft→confirm 确认闸门无关。

## 禁忌与反模式
- 不要把「宿主 agent 上下文撑满」当成「蒸馏 LLM 窗口问题」去解。
- 不要断言 `no_knowledge` 的 raw 被保留。
- submit **超时**后不盲目重试（不幂等，会重复写入与字节交错）；返回 `missing_result` 才是「未执行」可重试。
- 不要把 subagent 自报的「已入库/已生效」直接转述给用户。

## 关键事实依据
- `_distill_one` 每文件一次 LLM 调用，文件间不共享上下文。
- 基准：1000 条对话倒排查询 82ms，但全量重建成本线性增长。
- 实测：worker 报 3 条 `ingested`，实际 frontmatter 全为 `draft`。