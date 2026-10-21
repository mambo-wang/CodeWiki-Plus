---
type: decision
title: 宿主可见入口全量改为技能薄壳：sync-skills 编译 MCP 提示词为 SKILL.md（ADR-0019）
tags:
- decision
aliases:
- sync-skills
- 技能薄壳
- skill stub
- 宿主技能文件
- ADR-0019
metadata:
  date: 2026-10-20
  confidence_level: strong
  task_id: 日常维护
  related_modules:
  - cli
  - mcp
  source_ref: ADR-0019
  reason: ADR-0019 已在本次会话经用户批准计划并实施完成，按确认闸门先落草稿待 confirm_note
  verification:
    test_ref: tests/test_sync_skills.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-20 10:16:52+00:00
stale_after: '2027-10-20'
verified:
- by: codewiki/5.15.0
  at: '2026-10-20T10:28:14Z'
---

## 决策

初始化阶段的「宿主可见入口」从命令薄壳（`.qoder/commands/codewiki/*.md` 等）全量改为技能薄壳（`<宿主配置目录>/skills/codewiki-<name>/SKILL.md`），CLI 由 `codewiki sync-commands` 替换为 `codewiki sync-skills`（后者保留源码但不再注册）。权威仍在 MCP `get_prompt`，SKILL.md 只是薄壳入口。

## 关键口径

- frontmatter 固定三行：`name: codewiki-<kebab-name>` / `description: "..."`（双引号包裹，en 含 `: ` 必须引号）/ `disable-model-invocation: true`（手动触发，常驻上下文归零，语义等价换格式的 command）。**不渲染 status 字段**。
- 命名恒 `codewiki-` 前缀，不随 locale 变化（推翻 ADR-0017 决策 4 的 locale slug）；`--lang` 决定整文件语言——正文样板与开关映射指引走 `_BODY_I18N` 双态表，en 产物不得残留中文段落。
- codebuddy 不再豁免：IDE 自动映射只有 prompt→command 通道，没有 prompt→skill 通道，故所有宿主（含 codebuddy）统一生成技能薄壳；仓库无任何 IDE 目录时兜底写 `.trae/skills/`。
- 全量覆盖 + prune：删除目标目录下不在渲染集合内的 `codewiki-*/` 目录（只碰前缀）。
- 产物入库：`.qoder/skills/*` 忽略但 `!.qoder/skills/codewiki-*/` 例外（目录被忽略时其内 negation 无效，必须忽略内容不忽略目录）。
- 开关映射指引（2026-09-29 事故语义）保留：enable_task_management/capture/clone 不注入默认 arguments，薄壳指引 Agent 把用户意愿映射进 arguments。

## 被推翻的旧口径

旧 stable 笔记《宿主命令映射口径仅 codebuddy 自动映射 MCP prompt，其余宿主均需 sync-commands 薄壳》（2026-10-09）的「codebuddy 豁免」结论被本决策推翻；ADR-0017 命令薄壳部分被 supersede（工具通道补丁部分仍有效）。

## 验证

- tests/test_sync_skills.py 30 个测试（frontmatter 三行、中英双态无残留、round-trip、prune、宿主判定、开关指引）。
- 实现：codewiki/cli/commands/sync_skills.py；步骤文案：codewiki/mcp/prompts.py `_SYNC_SKILLS_STEP` 单一模块级副本（消除 ADR-0017 时代双副本漂移温床）。
