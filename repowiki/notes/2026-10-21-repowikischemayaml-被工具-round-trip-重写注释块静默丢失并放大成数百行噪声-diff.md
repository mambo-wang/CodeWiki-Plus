---
type: pitfall
title: repowiki/schema.yaml 被工具 round-trip 重写：注释块静默丢失并放大成数百行噪声 diff
tags:
- pitfall
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: Trae适配
  source_session: b483ced5633c4d888013bfa4df3cafa5
  related_modules:
  - repowiki
  - schema
  - export
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-变更评估与代码评审-请对最近代码变更做影响范围评估（修改后-96933d.md
  scene: Trae适配 三提交评审
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 02:03:08+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-21T03:48:47Z'
---

## 背景

评审提交 `1620d10`（`schema.yaml` 扩展：笔记类型晋升 `promote_to`、合并字段 `merge_fields`、`project` 块、HTML 导出配置）时，`repowiki/schema.yaml` 的 diff 达到 575 行，与提交意图的量级明显不符。

## 现象：round-trip 序列化的稳定指纹

行 diff 呈现整文件重写而非局部增删：

- 旧版头部注释块整体消失（schema 说明、字段用途的注释全丢）；
- 文件头新增 `---` 文档标记；
- 长字符串被重新折行；
- 行数级 diff 巨大，容易被误判为破坏性语义变更。

## 判定方法：先语义对比，再决定是否报 blocker

1. 用 `git show <old-rev>:repowiki/schema.yaml` 取旧版，新旧两版各自 `yaml.safe_load` 后对结构化结果做 JSON 级 diff，不依赖行 diff；
2. 语义对比结论：变更**全部为纯增量**（新增 `note_types` / `promote_to` / `merge_fields`、`project` 块、`export.html`、`generated_at`、`version`），无任何值删除；
3. 由此得出：行数噪声不等于语义破坏，本次提交可接受、不必回滚；真实损伤只是注释丢失。

## 根因与正确做法

根因是某处代码以 `yaml.load` → `yaml.dump` 重写该文件（round-trip），PyYAML 的 dump 不保留注释与原始排版（嫌疑在 export / schema 相关代码）。

- 排查并修复重写源头：改用保留注释的写法（如 `ruamel.yaml`）或做文本追加，而不是整体重写；
- 被删除的头部注释可从 git 历史恢复；
- 修复源头后 diff 会自然回到最小增量，无需为噪声回滚已提交内容。

## Rationale

「整文件重写 + 注释消失 + 新增 `---` 标记 + 字符串重折行」是 YAML round-trip 的通用指纹。评审时若不先做语义级对比，就会把纯增量误报为破坏性变更，或反过来放过注释静默丢失这类真实损伤。该方法可复用于任何被工具重写的配置文件（YAML/JSON/TOML）。
