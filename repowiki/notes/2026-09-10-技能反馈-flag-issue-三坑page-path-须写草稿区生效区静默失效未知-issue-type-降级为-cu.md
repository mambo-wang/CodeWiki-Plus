---
type: pitfall
title: 技能反馈 flag_issue 三坑：page_path 须写草稿区（生效区静默失效）、未知 issue_type 降级为 custom、无关闭 issue
  工具
tags:
- pitfall
metadata:
  date: 2026-09-10
  task_id: 产品维护
  related_modules:
  - skill
  - issue
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-docs-articles-CodeWiki-Plus系列13：把知识编译成行.md
  scene: 产品维护 / 技能反馈
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:46:53+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:13Z'
---

## Background
用户问「文章说可以给技能反馈问题，怎么反馈」。`flag_issue` 链路通，但有三个真实坑。

## 坑 1：page_path 必须写草稿区，生效区路径静默失效
分组逻辑要求路径至少 3 段且首段等于 `skills`（`skill_creator.py:340-342`）。技能装上后物理位置在 `.codebuddy/skills/<name>/SKILL.md`，但反馈**仍要写** `skills/<name>/SKILL.md`——写生效区路径不报错，只是永远进不了 prepare，反馈石沉大海。

## 坑 2：issue_type 未知值被降级为 custom
枚举只有 9 个值（`registry.py:1985-1995`），handler 对未知类型打 warning 后强制改写为 `custom`（`issue_tracker.py:110-112`）。`skill-ineffective` 不在枚举里会被降级，语义丢失。要真正支持需改**两处**：`registry.py` 的 schema enum 和 `issue_tracker.py:99-109` 的 `valid_types`，只改一处会前后不一致。

## 坑 3：没有关闭 issue 的工具
注册表只有 `flag_issue`，没有 `resolve_issue`。修订完、skill 更新后，那条 issue 仍 `open`，继续出现在每次 prepare 当素材。唯一关闭手段是手动把 `.meta/issues.json` 该条 `status` 改成非 open（`skill_creator.py:338` 只认 `open`）。

## 正确做法
- 反馈时 `page_path` 一律用 `skills/<name>/SKILL.md`（草稿区），勿用生效区绝对路径。
- 类型用 `custom` 即可；若需语义类型，先确认枚举已含该值（且 registry 与 issue_tracker 两处同步）。
- 闭环：`flag_issue` → 下次 `skill_creator(mode=prepare)` 的 `open_issues_by_skill` 聚合 → 折进正文 → `submit(action=updated)` → 确认 → reinstall。

## 关联
与 architecture 笔记『UserPromptSubmit 技能提示 hook 已实现并接线…』互补：hook 只提示 draft 技能，而 draft 技能的反馈又靠 flag_issue 这条坑满满的链路回流。
