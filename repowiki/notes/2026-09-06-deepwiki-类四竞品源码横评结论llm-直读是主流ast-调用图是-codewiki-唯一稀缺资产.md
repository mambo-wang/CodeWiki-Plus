---
type: architecture
title: DeepWiki 类四竞品源码横评结论：LLM 直读是主流，AST 调用图是 CodeWiki 唯一稀缺资产
tags:
- architecture
- codewiki
- deepwiki
- opendeepwiki
metadata:
  date: 2026-09-06
  related_modules:
  - dependency_analyzer
  severity: medium
  source_ref: conversations/conv-调研-openwiki、deepwiki-open、OpenDeepWiki、deepwiki-rs-四个-DeepWi.md
  scene: 竞品调研
status: stable
author: local
generated:
  by: codewiki/5.5.0
  at: 2026-09-06 08:23:37+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:13Z'
---

## 背景

2026-09-06 对 openwiki（16.2k★）、deepwiki-open（17.9k★）、OpenDeepWiki（3.6k★）、deepwiki-rs/Litho（1.7k★，已转向后继项目 Terrain 维护态）四个 DeepWiki 类项目做源码级横评（clone 后子代理通读，全部带文件:行号依据），报告在 docs/DeepWiki类开源项目对比调研报告-2026-09.md。

## 结论

1. 四个竞品全部走 LLM 直读代码路线，无一家做 AST/tree-sitter 静态分析——CodeWiki 的依赖分析管线在同类项目中没有直接竞争者。
2. 知识治理（证据哈希/确认闸门/采纳反馈）仅 CodeWiki 与 openwiki 认真做；deepwiki-open 缓存键无 commit hash（无增量）、deepwiki-rs 每次删目录全量重写。
3. deepwiki-open 用最弱工程拿最高 star，验证网页 Demo 传播效应：若需传播性，复用现有 Vue 前端做只读可视化比补技术短板划算。
4. README 与代码多处不符（deepwiki-rs 宣称支持 Go 实际无 Go 处理器、宣称并行实际串行、死旗标、缓存不校验 model_name）——竞品调研必读源码再次验证。

## 适用范围

后续定位讨论、竞品对标、借鉴选型时引用；详细六维度对比表与 B1-B10 借鉴清单见报告原文。
