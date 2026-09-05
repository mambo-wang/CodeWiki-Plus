---
type: pitfall
title: analyze_repo 超时根因探测教训：.venv 早已在默认排除且生效，真正拖累是 agent 临时目录（.caveman-tmp 929 文件）——下结论前先实测计数
tags:
- codebuddy
- codewiki
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - analysis
  - patterns
  severity: medium
  source_ref: conversations/conv-我们是如何保证生成的代码WIKI的准确性可信度.md
  scene: 代码分析
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:37:37+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:32Z'
---

## Background

CodeWiki-CN 上 `analyze_repo` 多次超时（>120s），第一直觉归因于「`.venv` 未纳入默认排除」——用户也点名要修。

## 实测更正（2026-09-04）

- `.venv` **早已在** `DEFAULT_IGNORE_PATTERNS`（patterns.py L98）且生效：结构分析 file_tree 中 `.venv` 文件为 0。
- 真正拖累：`.caveman-tmp`（CodeBuddy 临时工作区副本）929 个文件占扫描量 65%（含 495 个第三方 `.go`），且首次 `analyze_repo` 的 `detect_services` 撞上其中的 Go 项目，把 MCP 服务事件循环卡死（PID 满负荷、写锁排队超时、读正常）。
- 修复：默认排除补 `.caveman-tmp` / `.qoder` / `.workbuddy`（patterns.py L102-111）。效果：file_tree 1439→505，完整分析仅 11.1s（1788 组件）。

## 方法论

分析性能问题时先跑探测脚本统计真实分布（哪些路径段占多少文件），再下结论；`.venv` 类「理所当然」的根因假设要用实测计数证伪。agent 临时目录（`.caveman-tmp`/`.qoder`/`.workbuddy`/`.claude` 副本）默认应排除在代码分析之外。
