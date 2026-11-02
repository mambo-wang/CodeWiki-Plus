---
type: pitfall
title: 技能 SKILL.md 正文引用外部本机脚本导致不可移植（linseer 案例）
tags:
- pitfall
metadata:
  date: 2026-10-31
  confidence_level: weak
  task_id: 产品维护
  source_session: 183913c20fab44a9996c660b1278cb6b
  related_modules:
  - skill-creator
  severity: medium
  source_ref: conversations/conv-我在内网电脑使用codewiki的时候，发现一个小问题，就是编译的技能里只有SKILL.md没有相关脚本，看可以优化吗？.md
  scene: 技能编译
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.6
  at: 2026-10-31 01:42:43+00:00
stale_after: '2027-04-29'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-31T07:01:31Z'
---

## Background

编译 `linseer-preset-multimal-asset` 技能时，SKILL.md 正文直接照搬笔记里的工具名 `hf_download.py` / `zip_assets.py`，但这两个脚本是用户本机（`G:\models`）的本地工具，不在技能包、也不在工作区。技能安装到内网/新机器后触发时找不到脚本，技能不可移植。

## Root cause

`skill_creator` 编译产物只有 SKILL.md 单文件，无资产通道；写作规范只禁绝对路径和密钥，没有「脚本引用必须自包含」规则，裸文件名引用完全漏网。

## 正确做法

- 编译技能前先排查正文里出现的脚本名/文件路径，确认其归属；
- 需要复用的脚本 → 标准化后放进技能包 `scripts/` 目录，正文用相对路径 `scripts/xxx.py` 引用；
- 简单的下载/打包操作 → 直接内联标准做法（huggingface_hub 的 `snapshot_download` / 标准 zipfile 非流式写入），不依赖外部脚本。

## Rationale

值得持久化：这是用户亲历复盘并主动上报的产品缺陷，直接催生了 skill_creator 资产通道设计（见决策笔记「skill_creator 增加技能包 scripts/ 资产通道」）；即便工具层未改造前，手工编写/编译技能时该规则也立即适用。

## Recovery

工具层修复（scripts/ 资产通道 + submit error/lint warning 校验）落地后此坑由工具兜底；落地前靠本规则人工把关。
