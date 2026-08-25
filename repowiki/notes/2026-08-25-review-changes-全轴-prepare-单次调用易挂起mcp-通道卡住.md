---
type: pitfall
title: review_changes 全轴 prepare 单次调用易挂起（MCP 通道卡住）
tags:
- lastwritetime
- pitfall
aliases:
- review_changes 卡住
- 全轴 prepare 超时
- MCP 长调用挂起
- 四轴评审 prepare
metadata:
  date: 2026-08-25
  related_modules:
  - mcp
  related_components:
  - codewiki/mcp/tools/review_changes.py
  severity: high
  root_cause: review_changes prepare 全轴模式内部串行执行约 12 次 BM25 全库检索，累计分钟级耗时，MCP 通道对长调用无进度反馈导致挂起
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 15:55:07+00:00
stale_after: '2027-02-21'
verified:
- by: human:mambo-wang
  at: '2026-08-25T15:55:19Z'
---

## 背景

调用 review_changes 做四轴评审（focus=all）时，MCP 调用界面表现为「卡住」，等待数十秒无返回。

## 现象与排查

- MCP 服务器并未死：后续轻量 query_wiki 调用秒回（宽泛词命中正常）。
- 磁盘上 .codewiki/workspace/review_context.json 的 LastWriteTime 停留在调用前，说明该次全轴 prepare **从未成功写盘**——长调用在 MCP 通道上挂起，未等到返回。
- 改用轻量、分步收集四轴证据后一切正常。

## 根因

prepare 的 focus=all 内部**串行**执行约 12 次 _query_wiki（convention 轴 6 次：5 查询 + overview；module_knowledge 轴最多 5 次），每次都是 BM25 全库检索，累计耗时达分钟级。MCP stdio 通道对长耗时、大返回的调用无进度反馈，容易挂起。

## 正确做法

1. 不依赖单次大调用：改用轻量分步收集证据（单次 query_wiki 秒回）。
2. 诊断技巧：用文件 LastWriteTime 判断工具是否真的执行完成；用宽泛词 query_wiki 验证服务器存活。
3. 工具侧改进方向：将多轴查询并行化（ThreadPoolExecutor）或拆分 focus 多次调用，降低单次调用时长。
