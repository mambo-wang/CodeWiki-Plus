---
type: decision
title: skill-creator Phase 2 未启动：数据侧地基已落地、编排侧零启动；先攒真实试用反馈再谈编排
tags:
- '29'
- codewiki
- decision
metadata:
  date: 2026-09-07
  related_modules:
  - skill-creator
  severity: medium
  source_ref: conversations/conv-SKILL-CREATOR需求的PHASE-2是不是还没启动.md
  scene: skill-creator Phase 2 评估
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:01:18+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:18Z'
---

## 背景

2026-09-06 核实：skill-creator 的 Phase 2（真实任务回流编排、技能采纳信号、hooks.yaml 家族分发技能资产）**未启动**——工单（repowiki/.meta/issues.json 18 条 open）无相关项、docs/plans/ 六个计划文件无相关内容、codewiki/mcp/tools/skill_creator.py 无 TODO/占位。但数据侧地基已铺好：§9 素材保真度（codewiki/src/tool_digest.py）已落地，文档自述其定位是「回流迭代（Phase 2）的素材质量地基」。注意：docs/CodeWiki-CN-优化Roadmap.md 的「Phase 2：生成引擎增强」是仓库整体路线分期，与 skill-creator 的 Phase 2 不是同一件事。

## 分三块判断（2026-09-06 数据）

- **P2a 技能采纳信号——现在做是空转**：方案 §4.4 已定「负面=flag_issue，正面=沉默即默认」，唯一数据源是 flag；IDE 不回报技能触发次数，正面反馈通道缺失是有意取舍。
- **P2b 真实任务回流编排——值得做但缺的是数据不是编排**：prepare 已聚合 open issues，flag → prepare → submit → install 全链 #29 已实测通过。现在上编排 = 让 LLM 给自己生成的技能打分（竞品 wikiskill 六次 live 运行零接受、$0.09/迭代的失败教训）。
- **P2c hooks.yaml 家族分发——需求尚未成立**：当前只有一个宿主（CodeBuddy）。

## 结论

值得做但当时启动会建成空中楼阁；真正的下一步是把 `maintain-fork-pr-merge` 拿去真跑几次 fork PR 合入，攒够 3-5 条真实试用反馈（当时仅 1 份技能、0-1 条反馈）。
