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
  confidence_level: weak
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
stale_after: '2027-10-31'
verified:
- by: codewiki/5.15.0
  at: '2026-10-20T10:28:14Z'
- by: codewiki/5.16.6
  at: '2026-10-31T01:16:56Z'
source_conversations:
- conversations/conv-codewiki-setup命令，生成的skill为什么没有根据语言生成不同的内容和名称-@SKILL.md-2-2.md
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

## 技能 frontmatter name 按语言国际化而目录名恒为 codewiki-kebab（ADR-0019 决策 3 修订）

> 合并自蒸馏候选：技能 frontmatter name 按语言国际化而目录名恒为 codewiki-kebab（ADR-0019 决策 3 修订）

## 修订记录（2026-10-30）：决策 3 的 name 前提被实测推翻

用户实测 CodeBuddy 与 Trae 均能识别中文 frontmatter name 并触发，原前提「skill name 必须是 ASCII slug」不成立。修订定案（已实施，65 passed / 1 skipped）：

- frontmatter `name` 按语言国际化：zh 产物 name 为 `codewiki-<中文标题>`（标题取自 `codewiki/mcp/locales/zh.yaml` 的 title，如 `codewiki-蒸馏对话提取记忆和经验`）；en 产物维持 `codewiki-<kebab>` 完全不变。
- **目录名恒为 `codewiki-<kebab>` 不动**：prune 口径（`codewiki/cli/commands/sync_skills.py:32-34`，目标目录 `codewiki-*` 全集 == 本次渲染集合）决定目录名本地化会让 `--lang en` 把 zh 目录当陈旧产物整体删掉。
- 实现收敛在 `sync_skills.py` 新增的 `_localized_skill_name()`；静态资产 `codewiki/assets/skills/codewiki-setup/SKILL.zh.md` name 行同步改中文；`docs/adr/0019` 已加修订记录。行为变更：zh 技能触发词从 `/codewiki-<kebab>` 变为 `/codewiki-<中文标题>`。
- 遗留：qoder 宿主未实测中文 name（只验了 codebuddy/trae），回退点集中在 `_localized_skill_name()` 一处。
