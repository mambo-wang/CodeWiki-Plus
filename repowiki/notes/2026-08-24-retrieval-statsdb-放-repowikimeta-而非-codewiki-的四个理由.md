---
type: architecture
title: retrieval_stats.db 放 repowiki/.meta 而非 .codewiki 的四个理由
tags:
- architecture
metadata:
  date: 2026-08-24
  related_modules:
  - telemetry
  - repowiki-项目研究与借鉴分析
  severity: medium
  source_ref: conversations/conv-调研-https-github.com-akitaonrails-ai-m-输出报告.md
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:21:44+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:17Z'
reject_reason: 聚合进场景：MCP-Server薄壳架构与参数约定
author: mambo-wang
---

## 背景

调研 ai-m 时被问：为什么 retrieval_stats.db 放 repowiki/.meta/ 而不放 .codewiki/。

## 事实

四个理由：①生命周期不同——热度是跨月累积的行为数据，.codewiki 缓存跟代码分析走、一 reset 就清零；②wiki 工具只认 output_dir 不该知道仓库根——放 .codewiki 每个消费点都要重复 _resolve_db_path 的脆弱启发式；③可移植性——repowiki 整目录可拷贝；④git 策略语义——.meta 默认共享逐个排除，单独 ignore 这一个文件本身就是「行为遥测私有」的设计声明。

## 推论

「行为遥测」与「代码分析缓存」生命周期不同，不能同目录；工具只依赖 output_dir 是架构边界，不该反查仓库根。
