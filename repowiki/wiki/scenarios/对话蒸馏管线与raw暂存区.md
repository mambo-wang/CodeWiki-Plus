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
  summary: 蒸馏三模式共同落盘路径改一处全覆盖；raw 生命周期（no_knowledge 删、keep_raw 留）；Mode C 多文件逐文件处理+compact
    操作纪律
  heat: 1
---
## 工作场景
distill_conversation 蒸馏管线与 repowiki/raw/ 暂存区生命周期的方法体系。适用于修改蒸馏逻辑、排查 raw 文件去向、宿主 agent 执行 Mode C 批量蒸馏。

## 适用条件
给蒸馏产物（notes/memories）加逻辑、写 raw 相关测试、Mode C 多文件蒸馏的宿主侧操作。

## 核心 SOP
1. 给蒸馏产物加逻辑只改 _process_llm_output 一处：三种模式 A（注入 llm 回调）/ B（后台 env 构建 LLM）/ C（agent 即 LLM 的 prepare/submit）都汇聚到这里（解析 → 去重 → ingest draft → memories 暂存 → mark/delete raw → 重建索引）——改一处全覆盖，避免三处漂移。
2. 处理 raw 文件去向区分两条路径：no_knowledge（notes=[]）按设计直接删除（噪音不留）；keep_raw=true 是唯一保留途径——排查与测试断言都按这个语义。
3. Mode C 多文件蒸馏保持操作纪律：逐文件读 → submit 落盘 → 立即触发上下文压缩（compact）清掉已处理 transcript → 再下一个文件——蒸馏本身逐文件独立，上下文撑满是宿主侧纪律问题，不是工具窗口问题。

## 判断逻辑
- 测试断言口径：no_knowledge 断言「文件不存在」；keep_raw 断言「保留且标 distilled」；旧断言「保留并标记」已过时。
- 不引入「prepare 内联截断 / map-reduce 分治」等复杂方案：问题本质是宿主上下文管理，加机制只增复杂度（历史弯路均已回退）。

## 禁忌与反模式
- 不要把「宿主 agent 上下文撑满」当成「蒸馏 LLM 窗口问题」去解。
- 不要断言 no_knowledge 的 raw 被保留（保留行为由 test_distill_cleanup.py 单独覆盖）。

## 关键事实依据
- _distill_one 每文件一次 LLM 调用，文件间不共享上下文。
- 302 轮大对话一次即可占满宿主上下文，逐文件 compact 是验证过的解法。