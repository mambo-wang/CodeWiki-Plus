---
type: pitfall
title: CODEWIKI_TEAM_MEMORY_HOOK 与 CODEWIKI_RAW_TOOL_DETAIL 不是 skill 自动编译开关，别改错方向
tags:
- pitfall
metadata:
  date: 2026-09-11
  task_id: 技能提取
  related_modules:
  - _ide_hook
  - tool_digest
  severity: medium
  source_ref: conversations/conv-如何启用skill自动编译功能，是有环境变量控制吗？.md
  scene: 技能提取
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-11 01:28:50+00:00
stale_after: '2027-03-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-11T03:55:11Z'
---

## 背景

当被问到「有没有环境变量控制 skill 自动编译」时，最容易把两个名字相近、且都与 skill 链路沾边的环境变量当成答案，进而改错开关、把采集通道关掉。

## 两个变量的真实语义

- `CODEWIKI_TEAM_MEMORY_HOOK=1`（`codewiki/mcp/_ide_hook.py:71,470-479`）：开的是**对话采集**总闸，不是编译。只有手工 `python -m codewiki.mcp._ide_hook` 时才需要它；走 `codewiki install-hooks` 接线的 wrapper 已自带 `--enable`，不用设
- `CODEWIKI_RAW_TOOL_DETAIL`（`codewiki/src/tool_digest.py:145`）：采集**成功工具调用细节**的 kill switch（设 `0`/`off` 关闭）。它影响的是技能**素材质量**，与自动编译无关——想让以后编译出的技能有完整步骤序列，反而要保证它默认开启

## 正确做法

先分清两类开关：「采集 / 素材质量」与「编译 / install」是不同层，前者有环境变量，后者没有、只能显式调用 `skill_creator`。遇到「有没有开关控制 X」这类提问，先确认 X 在实现里是否真的存在自动执行路径，再谈开关。

## 根因

技能链路（采集 raw → 蒸馏 → 笔记 → 场景 → 编译技能）环节多、命名相近，环境变量命名里又都带 CODEWIKI_ 前缀，容易被按名字联想而不是按代码归属归类。
