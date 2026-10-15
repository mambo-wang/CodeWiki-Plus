---
type: procedure
title: optional extra 的延迟导入 + fail-open 降级模式
tags:
- importerror
- markitdown
- procedure
metadata:
  date: 2026-09-29
  confidence_level: strong
  task_id: 产品维护
  source_session: 21f92d273a7c47e597c547a2cd0beb1f
  related_modules:
  - source_ingest
  - pyproject
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-8bc161.md
  scene: ingest_source 二进制源转换
  verification:
    test_ref: tests/test_source_convert.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.14.1
  at: 2026-09-29 01:56:16+00:00
stale_after: '2027-04-08'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-10T09:48:44Z'
---

## Background

`ingest_source` 的 `[convert]` extra（markitdown）采用 optional extra + fail-open 降级模式，使未安装 extra 的用户完全不受影响。

## Procedure

标准实现模式（以 `source_ingest.py` 的 markitdown 集成为例）：

1. **延迟导入**：`from markitdown import MarkItDown` 写在 `_convert_to_markdown()` 函数体内，而非模块顶部。模块加载时零开销，文本格式导入根本不碰 markitdown。
2. **ImportError 捕获 + fail-open 降级**：`except ImportError` 捕获后，导入照常成功（存储+注册），不抛异常、不阻断主流程。
3. **结构化错误字段**：registry 条目记 `convert_error` 字段，区分三种失败原因：
   - `dependency_missing` — 未装 extra，日志提示 `pip install codewiki-plus[convert]`
   - `empty_output` — 转换成功但产出空串（如扫描版 PDF 无 OCR）
   - `converter_exception` — 转换器抛异常
4. **下游感知**：抽取流程读到 `convert_error` 时给出明确指引（「扫描版 PDF 需先 OCR」），而非让 Agent 对着 null 猜。
5. **pyproject 声明**：`[project.optional-dependencies] convert = ["markitdown[all]>=0.1.0"]`，用户按需 `pip install codewiki-plus[convert]`。

## Rationale

本仓已有成熟先例（CBM delegation 的 fail-open 模式）。optional extra 的核心约束：未装时行为与改造前完全一致，不引入硬依赖、不静默失败。延迟导入确保模块加载零开销，结构化错误确保下游可做明确决策而非猜测。
