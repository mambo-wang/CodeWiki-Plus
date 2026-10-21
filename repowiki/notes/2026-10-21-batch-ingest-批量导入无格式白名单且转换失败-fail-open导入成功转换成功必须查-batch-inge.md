---
type: pitfall
title: batch_ingest 批量导入无格式白名单且转换失败 fail-open：导入成功≠转换成功，必须查 batch_ingest_report.json
tags:
- pitfall
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: 00d2597c-3348-8a86-9334-b42b389d1518
  related_modules:
  - mcp-tools
  severity: medium
  source_ref: conversations/conv-批量文档导入支持哪些文件格式-18a7d1.md
  scene: source_ingest/batch_ingest 批量文档导入
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 02:55:29+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:01Z'
---

## Background

用户询问 `batch_ingest` 批量文档导入支持的文件格式。代码核对结论：批量导入不设格式白名单，`kind='source'` 项逐条委托给单文档导入 `handle_ingest_source`（`codewiki/mcp/tools/batch_ingest.py:82`），批量和单条格式规则完全一致。

## 格式分档（codewiki/mcp/tools/source_ingest.py:283、:291）

- **文本类**（`.md` `.markdown` `.html` `.htm` `.txt` `.rst`）：原文进 `raw/sources/`，正文参与版本指纹比对（`version_sibling` / `supersedes` 两道版本闸门会触发），HTML 先剥标签再取纯文本（:316）。
- **二进制类**（`.pdf` `.docx` `.xlsx`）：经 markitdown 转出 `.converted.md` 侧车文件，指纹比对、`[^src:...]` 行号引用、知识抽取都以侧车为准（ADR-0018，:286–:292）。需装可选依赖 `pip install codewiki-plus[convert]`。
- **其他任意文件**：不报错不拒绝，原样拷进 `raw/sources/` 并登记索引（:747），但 `derived_text=null`，只能当附件追踪，不能进入抽取流程。

## Pitfall：转换失败是 fail-open 设计

未装 `[convert]` 依赖或转换异常时（:337–:343），**导入仍会成功**，只是 `derived_text=null`、`convert_error` 给出 `dependency_missing` / `empty_output` / `converter_exception` 三种信号之一。批量导入结束后必须查看 `.meta/batch_ingest_report.json`（`batch_ingest.py:166`）里逐条的 `derived_text`，不能把转换失败当成导入成功。

与既有笔记 `notes/2026-09-29-optional-extra-的延迟导入-fail-open-降级模式.md` 互补：该笔记讲实现侧的 fail-open 模式（延迟导入、结构化 convert_error），本笔记讲调用侧的坑（批量导入后必须核对报告，别把 fail-open 的静默降级误读为成功）。

## Rationale

格式分档本身读代码可知，但「导入成功 ≠ 转换成功」的 fail-open 语义与检查点（batch_ingest_report.json）是易误用的坑，未来 agent 做批量导入时直接受益。

## 附带发现（代码核对）

- 工具描述承诺「PDF, MD, DOCX, HTML」，代码实际还收 `.markdown/.txt/.rst/.xlsx`；`.pptx` 虽然 markitdown 能转但没进 `_CONVERTIBLE_SUFFIXES`——这是 :289 注释刻意要求的「与对外描述保持一致」，属有意收窄而非漏配。
- 死代码：`_convert_to_markdown` 在 :321 有一个只有 docstring 的空壳定义，随即被 :333 的完整定义覆盖，功能无影响但可清理。
