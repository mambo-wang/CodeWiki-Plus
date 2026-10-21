---
type: pitfall
title: 聚合写场景块时超长笔记文件名含三连字符折行落行首会被当作 frontmatter 闭合栅栏
tags:
- pitfall
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 他山之石
  source_session: aaf162a0ce2446bc857294d07c2c72b7
  related_modules:
  - MCP_Tools_Knowledge
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-e77a69.md
  scene: 知识聚合（consolidate_notes）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 03:08:29+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:05:39Z'
---

## 背景

consolidate_notes 聚合 submit 时校验失败：两个场景块（`repowiki/wiki/scenarios/发布与依赖治理方法.md`、`IDE-Hook采集链路方法.md`）frontmatter 缺 `type: Scenario`，被 submit 校验拦截（同批还有一处 disposition 文件名笔误）。

## 现象与根因

历史聚合把 source_notes 写进场景块 frontmatter 时，超长笔记文件名（如 `2026-09-10-uv-工具链两坑---no-group-devpython-version-补丁固定与-uv.md`）发生折行，`---no-group-dev...` 片段落在行首，被 YAML 解析器当作 frontmatter 闭合栅栏，其后所有键（`type: Scenario`、`status` 等）解析丢失。场景块本身内容完好，只是 frontmatter 结构被写坏。

## 正确做法

- 聚合 submit 校验拦截此类坏 frontmatter 后，直接手工修复场景块 frontmatter 再重提聚合报告，不要绕过校验；修复后 submit 通过、lint 0 error。
- 写 frontmatter 时若值内含长文件名或自由文本，须确保不会出现行首 `---`（给值加引号、或避免折行）。

## 关联与区别

- 与 `notes/2026-09-12-重写-frontmatter-文件时闭合栅栏后必须保留换行lenient-正则会静默吞掉正文且测试可能侥幸通过.md` 根因不同：那条是**写入侧**闭合栅栏后缺 `\n` 导致正文被吞；本条是**值内容**里的 `---` 折行落行首被误认为闭合栅栏导致后续键丢失。两者都是 lenient 解析把结构性错误降级为静默偏移的实例。
- 产品维护任务记忆已记录同族解析 bug：`_read_frontmatter`（note_consolidation.py）曾用 `text.find("---", 3)` 找结束标记，frontmatter 值内含 `---` 即截断，已修为按行匹配 `^---\s*$`；全仓约 30 处同款模式待收敛成共享 helper。

## Recovery

手工修复两个场景块的 frontmatter（确保 `type: Scenario` 等键可解析）后重提聚合报告即通过。
