---
type: decision
title: skill_candidate hint 设计裁决进展：蒸馏+session-start 双提醒、按主题去抖、容量硬顶静音、后台静音
tags:
- decision
metadata:
  date: 2026-09-07
  related_modules:
  - skill-creator
  - distill
  severity: medium
  source_ref: conversations/conv-SKILL-CREATOR需求的PHASE-2是不是还没启动.md
  scene: skill_candidate hint 设计
  disposition:
    verdict: excluded
    at: '2026-09-08'
    reason: 设计未定稿的中间进展记录，裁决仍在推进，属临时状态而非可复用方法
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:01:26+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:17Z'
---

## 背景

用户想降低「攒了可编译经验却忘了编技能」的摩擦，讨论在蒸馏/L2 时识别可创建技能的情况并 hint 提醒。经两轮 grill 评审（Q1-Q22），用户已裁决的部分如下（2026-09-06，未全部完成裁决，设计仍在推进中）。

## 已锁定（用户裁决）

- 目标形态：**蒸馏时提醒 + session-start 提醒都做**（Q13=ii）；运行时**不扫 conversations/ 归档**（Q16）。
- 已先做了 Q18 只读验证（扫 raw），结果：文件名判据 0 有效信号（见同批 lesson 笔记）。
- 按主题去抖（同一主题喊过一次就安静，直到有新素材）；容量耦合：技能硬顶 12 / 橙线 9，硬顶时完全静音、橙线时改口吻为「先合并再考虑新建」。
- 素材边界：任务记忆（memories）不作技能素材，蒸馏双轨产出的 memories 侧排除在判据之外。
- 消费者约束：只放工具返回值（零落盘），后台 distill-worker / Mode B 下静音（无人接收 = 纯噪音）；hint 内容带 `skill_creator(mode="prepare", topic=...)` 可复制命令 + 容量/冲突预警。
- 不限每批 hint 条数（Q12 用户取消硬顶）。
- 判据分层：A 层（用户指令文本相似）先上，B 层（工具序列相似）落数据但攒够样本再启用；工具权重推荐动作型 1.0 / 只读 0.3（待裁决）。

## 依据

- Doctrine「触发永远显式」：全自动发现→生成→install 不该做；hint 级半自动（提醒先问用户）明文允许；install 是用户动作。
- 可复用先例：`aggregation_hint` 机制（aggregation_state.py，计数器越线挂 additive key + 去抖）、distill 侧 `friction_hint`（distill_conversation.py）。

## 待裁决（截至该会话结束）

Q14 挂载点（推荐：蒸馏时抽指纹+比对+喊，L2 只喊不抽）、Q15 只读工具权重、Q19 清洗规则确认、Q20 session-start 历史来源（推荐：蒸馏时把指纹落轻量索引）、Q21 基线语料、Q22 B 层启用时机。
