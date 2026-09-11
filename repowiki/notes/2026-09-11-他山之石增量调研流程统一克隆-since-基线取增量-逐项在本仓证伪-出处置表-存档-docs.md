---
type: procedure
title: 他山之石增量调研流程：统一克隆 → since 基线取增量 → 逐项在本仓证伪 → 出处置表 → 存档 docs/
tags:
- '374'
- '375'
- procedure
metadata:
  date: 2026-09-11
  task_id: 他山之石
  related_modules:
  - docs
  severity: medium
  source_ref: conversations/conv-看一下docs里我们借鉴过的项目，自上次借鉴过后有什么新的合入值得借鉴.md
  scene: 他山之石/增量调研
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 23:00:39+00:00
stale_after: '2027-03-10'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-11T00:55:44Z'
---

## 适用场景

对已调研过的外部项目做周期性增量调研（「自上次借鉴后有什么新合入」）。

## 步骤

1. **统一克隆**：把借鉴过的项目克隆到同一父目录（本次为 `D:\repos`），后续增量 `git pull` 即可，不用每次重新定位。批量克隆命令容易被用户取消，实际只落了一部分，需检查目录清单补漏。
2. **取增量**：`git log --oneline <上次基线>..HEAD` + `git log --since=<基线> --diff-filter=A --name-only -- docs/designs`——除了 commit，新增的设计文档往往比代码更能说明机制取舍（本次 3 篇新设计文档承载了 #374/#375 的核心论证）。再对照 `CHANGELOG.md` 定位版本跨度。
3. **逐项在本仓证伪**：对每个候选机制，先 grep 本仓同语义实现（注意命名差异：lock/flock、friction/摩擦），确认本仓空白才允许写「值得借鉴」。
4. **出处置表**：每个候选一律落 absorbed / deferred / excluded 三选一，excluded 必填原因；「待探测」项要写明可证伪的阈值判据（例：「有 tool-error 行但 friction_score=0 的会话占比 ≥ 20% → 做」）。
5. **存档位置**：成果是「正在想的事」（调研事实 + 建议 + 待定项），写 `docs/<项目>-增量调研与借鉴分析-<日期>.md`；只有想明白的通用结论才进 `repowiki/notes/`。
6. **初稿错了就地加修正块**：本次初稿把本仓已有能力误判为缺口，修订时是在 §1/§2/§3 原地补「错在哪 + 实际代码在哪」，而不是重写历史。

## 检查点

- 处置前先确认「模型是否相反」（缓存 vs 资产、分发 vs 归属），相反直接 excluded。
- 探测结论必须带样本量与翻转条件。
- 用户认可后可顺带把可复用机制提为 draft note，须 `confirm_note` 才正式落盘。
