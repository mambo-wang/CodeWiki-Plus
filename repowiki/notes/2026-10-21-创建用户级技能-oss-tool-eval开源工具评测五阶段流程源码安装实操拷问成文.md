---
type: decision
title: 创建用户级技能 oss-tool-eval：开源工具评测五阶段流程（源码→安装→实操→拷问→成文）
tags:
- decision
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: 164a77b4-96c0-4d21-aab3-fe43fc1f2401
  severity: medium
  source_ref: conversations/conv-system-reminder-The-user-selected-the-following-plugins-that.md
  scene: 开源项目评测
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 12:15:29+00:00
stale_after: '2027-10-22'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-22T01:58:05Z'
---

## Background

用户要求把 Better Harness 分析试用的方式沉淀为可复用技能，用于后续评测更多开源项目（下载源码、安装工具、分析原理、实操验证、产出评测文章）。

## Decision

创建用户级技能 `oss-tool-eval`（`C:\Users\<user>\.qoder-cn\skills\oss-tool-eval\`，跨项目可用），五阶段主流程：

- A 定源与事实底座：clone 源码，产出带 file:line 的事实清单，「文档声明/代码事实/我的推断」分栏；
- B 安装与宿主适配：逐宿主安装、只读体检、记录本机路径差异；
- C 真实仓库实操：**跑前预登记预测**、原始输出落盘、换参数同窗口复跑；
- D 用代码事实拷问工具结论：真/假阳性/归因错/前提被证伪四分类，改完换一台仪器复审；
- E 成文与配图：11 段文章骨架 + 配图规范 + 发布前 5 道闸门。

配套 `scripts/svg2png.cjs`（自动回退 npm root -g 解析 playwright）与 `scripts/phone-check.cjs`（--audit/--shot），均已实测。

## Rationale

评测类工作的可复用资产是「取证纪律 + 文章骨架 + 出图管线」三件套，固化成技能比每次重推导可靠；预登记预测是抓归因错误的关键手段。

## 依据

2026-10-14 会话创建并实测通过（SKILL.md 91 行，校验清单全过，本会话技能目录可见）。
