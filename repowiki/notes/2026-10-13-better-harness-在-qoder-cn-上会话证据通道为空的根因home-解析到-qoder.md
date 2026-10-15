---
type: pitfall
title: Better Harness 在 Qoder CN 上会话证据通道为空的根因：home 解析到 ~/.qoder
tags:
- pitfall
aliases:
- session-limited
- qoder-home
- 会话证据为空
- better-harness 证据通道
- Qoder CN 路径
metadata:
  date: 2026-10-13
  confidence_level: strong
  severity: high
  root_cause: better-harness 的会话源发现把宿主 home 解析为 ~/.qoder（国际版布局），而本机 Qoder CN 的会话存储在
    ~/.qoder-cn，5/6 个启用源根不存在 → 会话证据恒空
  reason: 用户要求盘点可优化项时实测发现，报告与已发布文章的「无会话证据」归因需纠正
  verification:
    reviewed_by: human:mambo-wang
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.14.1
  at: 2026-10-13 06:45:58+00:00
stale_after: '2027-04-12'
verified:
- by: human:mambo-wang
  at: '2026-10-14T01:34:44Z'
---

## 现象

对本仓库跑 `/better-harness` 完整审查时，sessionEvidence 通道返回 `eligibleSessions: 0`、Task Episode 0，报告被标为 `session-limited`，经验沉淀维度被压到 38 分（贴近 35 分下限）。当时结论是「30 天内无可录取会话」。

## 真实根因

Better Harness 0.2.20 的会话源发现把宿主 home 解析为 `~/.qoder`（国际版 Qoder 布局）：

- `session-analysis sources` 的 `scope.home` = `C:\Users\Administrator\.qoder`；
- 该目录下 `audit/audit.jsonl`、`logs/sessions/<slug>`、`projects/<slug>` **均不存在**，只有 `logs/runs` 命中；
- 本机实为 Qoder **CN** 版，会话正文在 `C:\Users\Administrator\.qoder-cn\projects\D--repos-CodeWiki-Plus\*.jsonl` 与 `\.qoder-cn\logs\sessions\<slug>\`。

即通道为空是「找错目录」，不是「没有活动」。`~/.qoder` 与 `~/.qoder-cn` 同时存在（前者部分目录被其他工具写入），更容易误判。

## 验证与修法

```bash
node <plugin>/scripts/better-harness.mjs session-analysis sources \
  --workspace . --qoder-home "C:/Users/Administrator/.qoder-cn"
```

实测该覆盖下 6 个源根命中 3 个（run-manifests / log-sessions / projects），`sessions` 返回 84 条。再跑

```bash
harness evidence-bundle --workspace . --language zh-CN --depth quick \
  --since <d1> --until <d2> --qoder-home "C:/Users/Administrator/.qoder-cn" --format json
```

得到 `eligibleSessions: 56`、`taskEpisodes: 248`、`candidateEpisodes: 18`、`emittedCandidates: 3`，populationCoverage 里 withChanges 10、withChecks 1、withExecutionFriction 12 —— 会话证据通道完全打通。

注意：`QODER_HOME` 环境变量这条路的校验器要求 basename 为 `.qoder`/`qoder`，指向 `.qoder-cn` 会被拒；只有 `--qoder-home` 旗标能直接生效。lead 通道文本里的「Source roots: 2 of 6 enabled roots exist」在覆盖后仍是旧串，不能当作会话通道是否生效的判据，要看 sessionEvidence lane 的 `scope.eligibleSessions`。

## 推论

任何在 Qoder CN 上的 Better Harness 审查，若经验沉淀维度分数异常低或报告标 `session-limited`，先核对 `scope.home` 是否为 `.qoder-cn`，再谈「行为未被观察到」。否则会把「证据通道缺失」误读成「工作流薄弱」。
