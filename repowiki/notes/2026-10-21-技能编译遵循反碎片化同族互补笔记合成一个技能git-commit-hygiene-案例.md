---
type: decision
title: "技能编译遵循反碎片化：同族互补笔记合成一个技能（git-commit-hygiene 案例）"
tags: ["decision"]
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 日常维护
  source_session: "d1684b0203bc487398ca761a4bfce9fd"
  related_modules: ["skill-creator"]
  severity: medium
  source_ref: "conversations/conv-现在蒸馏对话的时候，是否会按采集时间从早到晚的顺序来蒸馏？.md"
  scene: "技能编译"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.15.0, at: 2026-10-21T11:58:51Z }
stale_after: 2027-10-21
origin: conversation

---

## Background

2026-10-21 评估把「共享工作区多会话并行时提交必须用显式 pathspec」笔记（命令密度 11，超阈值 3）编译成技能时，发现同族还有一条 2026-09-20 的「提交前清理暂存区测试残留并排除 .scratch 与 .codebuddy/teams 临时目录」笔记。

## Decision

两条同属 git 提交卫生但场景互补（一条讲多会话 index 污染隔离、一条讲单会话残留清理），按反碎片化纪律**合成一个技能**（`git-commit-hygiene`）而非各编一个。用户确认执行，技能草稿落在 `repowiki/skills/git-commit-hygiene/SKILL.md`（吸收材料双向溯源已记录）。

## Rationale

skill_creator 的容量与冲突预检按技能数计，碎片化技能会占容量且触发条件互相重叠；同族知识合成单技能是 skill-creator 流程的标准取舍判据，后续编译技能时应先检索同族笔记再决定合成范围。

## 依据

本次会话中用户明确指示「评估编译技能」并采纳了合成方案（2026-10-21）。
