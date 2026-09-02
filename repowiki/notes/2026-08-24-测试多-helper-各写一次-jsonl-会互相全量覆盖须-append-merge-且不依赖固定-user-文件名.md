---
type: pitfall
title: 测试多 helper 各写一次 jsonl 会互相全量覆盖，须 append-merge 且不依赖固定 user 文件名
tags:
- pitfall
metadata:
  date: 2026-08-24
  related_modules:
  - tests
  - telemetry
  - teamai-cli-调研与借鉴分析
  severity: medium
  source_ref: conversations/conv-研究一下-https-github.com-Tencent-teamai-cli，看下跟CodeWiki的对比和可借鉴之.md
  consolidated_into:
  - wiki/scenarios/MCP-Server薄壳架构与参数约定.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:16:12+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:10Z'
reject_reason: 聚合进场景：MCP-Server薄壳架构与参数约定
author: mambo-wang
---

## 背景

T2 telemetry 迁移时多个测试 helper 各自写一次 jsonl，结果互相全量覆盖。

## 正确做法

测试种子数据用共享 helper（telemetry_seed.py）以 append-merge 语义写入，避免互相覆盖；测试断言不要依赖固定的 user 文件名（user_id 可用 CODEWIKI_USER 花名覆盖，且 per-user 文件名由身份维度决定）。

## 根因

jsonl 追加式写入：多 helper 同时写同一文件，后写者若用全量覆盖语义会抹掉先写者的数据。测试间共享状态时必须以追加合并为约定。
