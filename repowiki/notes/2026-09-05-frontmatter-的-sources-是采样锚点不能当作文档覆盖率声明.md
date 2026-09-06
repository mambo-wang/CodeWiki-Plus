---
type: pitfall
title: frontmatter 的 sources 是采样锚点，不能当作文档覆盖率声明
tags:
- codewiki
- pitfall
metadata:
  date: 2026-09-05
  task_id: 产品维护
  related_modules:
  - evidence
  - doc-writer
  - wiki-lint
  severity: medium
  source_ref: conversations/conv-@MCP_Tools_DocWriter.md-23-29-这段内容是如何生成和使用的.md
  scene: 代码证据（OKF sources）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:13:51+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:34Z'
---

## 背景

读 CodeWiki 页面（如 `repowiki/wiki/modules/MCP_Tools_DocWriter.md`）的 frontmatter 时，容易把 `sources:` 里的 2 条证据理解为「这份文档完整体现了这些文件」。实际上该页 `component_count: 43`，却只落了 2 条证据。

## 正确做法

`sources` 是**采样锚点**，不是覆盖率声明。要判断文档是否覆盖某个文件，应看 `module_tree` / `component_count`，而不是数 `sources` 的条数。

## 生成链路与两道截断

`write_doc_file` 落盘 → 交叉链接注入后调 `_inject_evidence`（`codewiki/mcp/tools/doc_writer.py:1504-1510`）→ `append_evidence_block` 在 frontmatter 闭合 `---` 前外科插入（`codewiki/mcp/tools/evidence.py:200-226`）。损耗来自两步：

1. `sorted(module_components)[:_MAX_AUTO_EVIDENCE]`，`_MAX_AUTO_EVIDENCE = 8`——按组件 ID 字典序截断前 8 个，**不是按重要性**；
2. 逐个从 `session.components` 取 `relative_path / start_line / end_line`，节点缺失或文件不存在就 `continue`。

两道损耗叠加，43 个组件最终只剩 2 条能解析出存在的文件。

## 影响

`stale_evidence` lint 只能校验已落地的少量锚点，未被采样的文件发生代码漂移不会被发现；因此「lint 无告警」不等于「该文档证据充分」。
