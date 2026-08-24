---
title: 对话蒸馏管线与raw暂存区
type: Scenario
description: 蒸馏三模式共同落盘路径、raw 暂存区生命周期、Mode C 多文件蒸馏操作纪律
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:50:29+00:00
stale_after: 2026-11-16
aliases:
- 对话蒸馏管线与raw暂存区
status: stable
metadata:
  source_notes:
  - notes/2026-08-15-no-knowledge-的-raw-由-distill-清理删除keep-raw-是唯一保留途径.md
  - notes/2026-08-15-process-llm-output-是蒸馏三种模式的共同落盘路径改一处全覆盖.md
  - notes/2026-08-15-蒸馏多文件时逐文件处理-每文件后触发上下文压缩避免累积撑满.md
  - notes/2026-08-24-mcp-知识飞轮决策记录l0-对话归档零索引phase-5-资产置信分层与-distill-worker-随包发布.md
  - notes/2026-08-24-raw-索引-indexjson-的-task-id-带字面引号导致按任务过滤漏检.md
  - notes/2026-08-12-tencentdb-agent-memory-四层记忆金字塔逐层蒸馏-触发式调度.md
  - notes/2026-08-24-tam-l0-l3-记忆管线对照codewiki-已有-l0l1空白在-l2-场景聚合与-l3-doctrine.md
  - notes/2026-08-24-openviking-借鉴三原则借分层不借-llm借模式不借-hook借粒度不借无闸门.md
  - 2026-08-24-mcp-知识飞轮决策记录l0-对话归档零索引phase-5-资产置信分层与-distill-worker-随包发布.md
  - 2026-08-24-raw-索引-indexjson-的-task-id-带字面引号导致按任务过滤漏检.md
  - 2026-08-12-tencentdb-agent-memory-四层记忆金字塔逐层蒸馏-触发式调度.md
  - 2026-08-24-tam-l0-l3-记忆管线对照codewiki-已有-l0l1空白在-l2-场景聚合与-l3-doctrine.md
  - 2026-08-24-openviking-借鉴三原则借分层不借-llm借模式不借-hook借粒度不借无闸门.md
  summary: L0 对话归档零索引；raw 索引 task_id 去引号；TAM/OpenViking 借鉴三原则
  heat: 2
---
## 工作场景
distill_conversation 蒸馏管线与 repowiki/raw/ 暂存区生命周期的方法体系。适用于修改蒸馏逻辑、排查 raw 文件去向、宿主 agent 执行 Mode C 批量蒸馏。

## 适用条件
给蒸馏产物（notes/memories）加逻辑、写 raw 相关测试、Mode C 多文件蒸馏的宿主侧操作。

## 核心 SOP
1. 给蒸馏产物加逻辑只改 _process_llm_output 一处：三种模式 A（注入 llm 回调）/ B（后台 env 构建 LLM）/ C（agent 即 LLM 的 prepare/submit）都汇聚到这里（解析 → 去重 → ingest draft → memories 暂存 → mark/delete raw → 重建索引）——改一处全覆盖，避免三处漂移。
2. 处理 raw 文件去向区分两条路径：no_knowledge（notes=[]）按设计直接删除（噪音不留）；keep_raw=true 是唯一保留途径——排查与测试断言都按这个语义。
3. Mode C 多文件蒸馏保持操作纪律：逐文件读 → submit 落盘 → 立即触发上下文压缩（compact）清掉已处理 transcript → 再下一个文件——蒸馏本身逐文件独立，上下文撑满是宿主侧纪律问题，不是工具窗口问题。
4. L0 对话归档走链接优先零索引（raw 不建文本索引）；Phase 5 资产置信分层（raw/notes/wiki 置信度递增）；distill-worker subagent 随包发布，宿主授权后后台批量蒸馏。
5. raw 索引 .index.json 的 task_id 统一去引号：_rebuild_index 与 pending_raws_by_task 复用同一 _unq 处理（历史数据存在字面引号导致按任务过滤漏检），修复后重跑扫描对齐。

## 判断逻辑
- 测试断言口径：no_knowledge 断言「文件不存在」；keep_raw 断言「保留且标 distilled」；旧断言「保留并标记」已过时。
- 不引入「prepare 内联截断 / map-reduce 分治」等复杂方案：问题本质是宿主上下文管理，加机制只增复杂度（历史弯路均已回退）。
- 借鉴外部记忆管线按三原则取舍：借分层不借 LLM（自研无外部模型依赖）、借模式不借 hook（触发形态按需）、借粒度不借无闸门（确认闸门保留）——TAM 对照显示 CodeWiki 已有 L0/L1，空白在 L2 场景聚合与 L3 Doctrine。

## 禁忌与反模式
- 不要把「宿主 agent 上下文撑满」当成「蒸馏 LLM 窗口问题」去解。
- 不要断言 no_knowledge 的 raw 被保留（保留行为由 test_distill_cleanup.py 单独覆盖）。

## 关键事实依据
- _distill_one 每文件一次 LLM 调用，文件间不共享上下文。
- 302 轮大对话一次即可占满宿主上下文，逐文件 compact 是验证过的解法。
- TencentDB 四层记忆金字塔（逐层蒸馏、触发式调度）是 TAM L0-L3 对照的调研基础，分层思路同源。