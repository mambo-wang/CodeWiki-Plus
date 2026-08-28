---
type: architecture
title: 多 IDE hook 支持按家族归并：31 个智能体收敛为 3 家族 schema
tags:
- architecture
- codebuddy
metadata:
  date: 2026-08-24
  related_modules:
  - hooks
  - registry
  - teamai-cli-调研与借鉴分析
  severity: medium
  source_ref: conversations/conv-研究一下-https-github.com-Tencent-teamai-cli，看下跟CodeWiki的对比和可借鉴之.md
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:16:10+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:09Z'
reject_reason: 聚合进场景：IDE-Hook采集链路方法
---

## 背景

调研 teamai-cli 的 KNOWN_AGENTS 注册表（31 个智能体）后，评估自己创建 hook 时如何支持更多智能体。

## 决策

按家族归并而非逐智能体适配：hooks.yaml 三家族 10 智能体 schema。核心洞察：skills 目录布局已行业事实标准化，只适配目录约定不适配协议（每条目仅 id/displayName/category/skillsPath 四字段）。hooks 层分三家族（claude settings.json / cursor hooks.json / codex hooks.json）+ 事件名映射表 + 安装探测。CodeBuddy/Qoder/Claude Code 都读 Claude 格式，一个家族复用即可。覆盖上限是支持生命周期 hooks 的工具（6-8 家族），不是 31。

## 根因

逐智能体适配是线性复杂度且不可维护；家族归并把 31 个收敛到 3 族，新增工具=加一行。注：具体安装接线见「多 IDE hook 自动检测接线」笔记。
