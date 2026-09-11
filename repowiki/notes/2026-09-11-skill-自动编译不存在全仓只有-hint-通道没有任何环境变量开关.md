---
type: architecture
title: "skill 自动编译不存在：全仓只有 hint 通道，没有任何环境变量开关"
tags: ["architecture", "codewiki", "userpromptsubmit"]
metadata:
  date: 2026-09-11
  task_id: 技能提取
  related_modules: ["skill_match", "skill-creator"]
  severity: medium
  source_ref: "conversations/conv-如何启用skill自动编译功能，是有环境变量控制吗？.md"
  scene: "技能提取"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:28:04Z }
stale_after: 2027-09-11
origin: conversation

---

## 事实

CodeWiki 中不存在 skill 自动编译能力，也没有控制它的环境变量。全仓 skill 相关逻辑只产出提示（hint），没有任何自动执行路径。

## 依据（本次代码核对）

- `codewiki/src/skill_match.py:248` — `build_skill_hint` 的契约写明 "never compile, never install, never write"；产物只是一句「（需你确认后执行；我不会自动编译）」（`skill_match.py:291`）
- `codewiki/mcp/prompts.py:1323` — skill-creator 提示词行为契约：永不自动编译、永不自动 install，触发词出现先向用户确认再执行
- `docs/skill-creator使用指南.md:202` — 三条提醒「只提示，绝不自动编译或安装」

## 现有的三条自动提醒通道（提醒 ≠ 编译）

| 通道 | 位置 | 触发条件 | 是否需要开关 |
|---|---|---|---|
| UserPromptSubmit 匹配未安装草稿 | `codewiki/mcp/_ide_hook.py:389-432` | prompt 与 `status: draft` 技能 containment ≥0.5 且 prompt ≥8 token（`skill_match.py:47,51`） | 需 `install-hooks` 接线，命令已硬编码 `--enable`（`codewiki/cli/utils/ide_config.py:107`），**不用设环境变量** |
| L2 场景块像技能素材 | `codewiki/mcp/tools/note_consolidation.py:706-734` | 命令命中 ≥3（`DEFAULT_CMD_THRESHOLD`）且 ≥2 条笔记背书（`skill_match.py:56,60`） | 无开关，submit 返回里带 `skill_hint` |
| 蒸馏产出撞上草稿 | `codewiki/mcp/tools/distill_conversation.py:1846-1855` | 笔记标题命中草稿 | 无开关 |

## 为什么这样设计

对应团队信条「不自动蒸馏/聚合/刷新 Doctrine：触发永远显式」与「确认闸门对等：凡落盘知识都先 draft、confirm 生效」。

## 操作要点

- 阈值（0.5 / 8 / 3 / 2）是代码常量，**不是**环境变量，要调只能改 `codewiki/src/skill_match.py`
- 编译只能显式走：`skill_creator(mode="prepare", ...)` → 人工撰写 → `submit` → 草稿落 `repowiki/skills/` → `install` 后技能进生效区 `.codebuddy/skills/`，之后才自动生效（`docs/skill-creator使用指南.md:173`）
- 想让 Agent 见到 `skill_hint` 就主动推进，只能在指令/AGENTS.md 里写明「收到 skill_hint 时先问我是否编译」，工具侧不会替用户点头

## 与相邻笔记的关系

`notes/2026-09-07-skill-candidate-hint-设计裁决进展…md` 记的是 hint 机制的设计裁决（何时提醒、去抖、谁接收），本条记的是「自动编译这条路径在代码里根本不存在」这一架构事实与三条通道清单，二者维度不同；且那条已被标为 excluded 的中间状态，故不合并。
