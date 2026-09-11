---
type: architecture
title: CodeBuddy Skills 三级渐进披露：常驻只占 ~100 词元数据，disable-model-invocation 与 user-invocable
  语义相反
tags:
- architecture
- codebuddy
metadata:
  date: 2026-09-11
  related_modules:
  - skills
  - mcp
  severity: medium
  source_ref: conversations/conv-@command-codewiki-蒸馏对话提取记忆和经验.md
  scene: 技能上下文开销与安装策略
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-11 01:05:06+00:00
stale_after: '2027-09-11'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-11T03:55:10Z'
---

## 事实（CodeBuddy 官方 Skills 文档，2026-09 查证）

技能采用**渐进式三级加载**，未触发的技能不会把正文塞进上下文：

| 层级 | 何时进上下文 | 开销 |
|---|---|---|
| 元数据 `name` + `description` | **始终**（只要处于启用态） | 约 100 词/个 |
| 正文 SKILL.md body | 仅被触发时 | < 5k 词 |
| 打包资源 references/ 等 | AI 按需读取 | 无限制 |

## 四种「禁用/隐藏」的语义差异（极易搞反）

| 方式 | 对模型是否可见 | 上下文占用 |
|---|---|---|
| `skillOverrides: "off"` | 隐藏，按名调用也拦截 | 零 |
| `skillOverrides: "name-only"` | 仅名称 | 最小 |
| frontmatter `disable: true` | 禁用 | 零 |
| **`disable-model-invocation: true`** | **不可见，只能手动 `/名称` 触发** | **归零** |
| **`user-invocable: false`** | **仍会被 AI 自动调用** | **照常占 ~100 词** |

坑点：`user-invocable: false` 常被误当成「禁用」，官方原文是「这类 Skill **会被加载到 AI 的上下文中**，但用户无法通过 `/` 菜单直接调用」——它只是从菜单隐藏、改由 AI 自动决策，**不省上下文**。真要省预算用 `off` / `disable` / `disable-model-invocation`。

## 权衡（决策要点）

常驻的那 ~100 词**就是触发机制本身**（模型靠 description 匹配任务），因此「AI 自动识别调用」与「零常驻占用」不可兼得：加了 `disable-model-invocation` 就等于放弃自动触发。低频但高价值的护栏型技能（会在你漏步骤时提醒）留着 100 词通常比禁用划算；真正该 `off` 的是长期不触发的。

## CodeWiki 两区制与上下文的关系

- 草稿区 `repowiki/skills/<name>/SKILL.md`（未 install）：不在 IDE 发现路径，**零上下文**，可以放心攒；
- 生效区 `.codebuddy/skills/`（install 后）：常驻约 100 词元数据。install 时会剥离管理类 frontmatter，只保留 `name`/`description` + 正文，因此改 flag 应改草稿区再重装，否则两份副本产生 hash 漂移。

## 验证方式

跑 `/skills` 面板查看每个技能的预估 token 数，先量化再决定裁哪个；覆盖优先级 `settings.local.json > settings.json > ~/.codebuddy/settings.json`。

依据：CodeBuddy IDE Skills 文档（https://www.codebuddy.ai/docs/zh/ide/Features/Skills）、CLI Skills 文档（https://www.codebuddy.cn/docs/cli/skills）。

## 关联

与『CodeBuddy Hooks matcher 语义』同属 CodeBuddy 平台机制事实类，但主题不同（技能加载 vs hook 匹配），不合并。
