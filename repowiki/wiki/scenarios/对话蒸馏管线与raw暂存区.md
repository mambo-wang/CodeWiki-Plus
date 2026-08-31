---
title: 对话蒸馏管线与raw暂存区
type: Scenario
description: 蒸馏三模式共同落盘、distilled_file 侧通道、L0 归档零索引、空结果提交纪律、超时不幂等陷阱
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:50:29+00:00
stale_after: 2026-11-16
aliases:
- 对话蒸馏管线与raw暂存区
status: stable
metadata:
  summary: distilled_file 文件侧通道；L0 归档链接优先零索引；无知识对话也提交空结果；submit 超时不幂等陷阱
  heat: 3
  source_notes:
  - notes/2026-08-25-mcp-参数长度受限时蒸馏-submit-走文件侧通道python-脚本直接调-handle-distill-conve.md
  - notes/2026-08-25-蒸馏时无知识密度的对话也提交空结果否则-raw-无法归档清理.md
  - notes/2026-08-26-distill-conversation-submit-mcp-超时后仍会执行且不幂等超时重试导致任务记忆重复写入与字节.md
  - notes/2026-08-19-l0-对话归档采用链接优先零索引设计.md
  - notes/2026-08-21-下一期方向资产置信分层与负反馈闭环roadmap-phase-5.md
  - notes/2026-08-26-github-竞品分层调研tencentdb-agent-memory-为直接竞品llm-wiki-家族为理念源头.md
---
## 工作场景
distill_conversation 蒸馏管线与 repowiki/raw/ 暂存区生命周期的方法体系。适用于修改蒸馏逻辑、排查 raw 文件去向、宿主 agent 执行 Mode C 批量蒸馏、设计对话归档策略。

## 适用条件
给蒸馏产物加逻辑、写 raw 相关测试、Mode C 多文件蒸馏的宿主侧操作、对话归档与溯源链路设计。

## 核心 SOP
1. 给蒸馏产物加逻辑只改 _process_llm_output 一处：三种模式 A/B/C 都汇聚到这里——改一处全覆盖，避免三处漂移。
2. 处理 raw 文件去向区分两条路径：no_knowledge（notes=[]）按设计直接删除；keep_raw=true 是唯一保留途径。
3. Mode C 多文件蒸馏保持操作纪律：逐文件读 → submit 落盘 → 立即触发上下文压缩 → 再下一个文件。
4. **MCP 参数长度受限时走 distilled_file 文件侧通道**：先用 write_to_file 把蒸馏 JSON 写入 `repowiki/raw/.distill-*.json`，submit 只传小路径（工具读取后自动删除暂存文件）。小载荷仍可内联 distilled。**不要写临时 Python 脚本调用 handler 绕过。**
5. **无知识密度的对话也提交空结果**（{"notes": [], "memories": []}），让工具走归档清理路径——否则 raw 文件一直留在暂存区无法清空。prepare 返回 captures 时，无价值对话直接返回空结果并 submit。
6. **L0 对话归档采用链接优先、零索引设计**：蒸馏成功的对话搬家到 repowiki/conversations/（raw/ 保持暂存队列语义）；归档层不建 BM25 索引（检索入口永远是知识层）；发现路径是链接式——query_wiki 命中笔记时露出 metadata.source_ref，agent 按需读取原始对话。蒸馏完成后把笔记 source_ref 从 raw/ 改写为 conversations/。drop_raw 是隐私显式删除通道。
7. raw 索引 .index.json 的 task_id 统一去引号：_rebuild_index 与 pending_raws_by_task 复用同一 _unq 处理。
8. Phase 5 方向：资产置信分层（strong/weak/shadow）+ 负反馈闭环（flag_misrecall 标记误召回达阈值自动降权）。

## 判断逻辑
- 借鉴外部记忆管线按三原则取舍：借分层不借 LLM、借模式不借 hook、借粒度不借无闸门。
- 归档不进索引则全量重建成本和检索噪音都不存在；对话是低信噪比文档，混入默认检索会挤掉高价值结果。
- 不引入 prepare 内联截断/map-reduce 分治等复杂方案：问题本质是宿主上下文管理。

## 禁忌与反模式
- 不要把「宿主 agent 上下文撑满」当成「蒸馏 LLM 窗口问题」去解。
- 不要断言 no_knowledge 的 raw 被保留。
- 不要在 MCP submit 超时后盲目重试（distill submit 不幂等，会导致任务记忆重复写入与字节交错损坏）——超时后先核实落盘状态再决定是否重试。
- 不要写临时 Python 脚本直连 handler 绕过 MCP 参数限制（已有正式 distilled_file 通道）。

## 关键事实依据
- _distill_one 每文件一次 LLM 调用，文件间不共享上下文。
- 基准测试：倒排索引查询耗时与文件数基本解耦（1000 条对话 82ms），但全量重建成本线性增长。
- distill_conversation submit 超时 ≠ 未执行：MCP 响应通道断开但 server 端实际继续执行。
