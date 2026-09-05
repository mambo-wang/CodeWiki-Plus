---
type: architecture
title: frontmatter sources 有三个生产者，字段形态各不相同
tags:
- architecture
- codewiki
- l55
metadata:
  date: 2026-09-05
  task_id: 产品维护
  related_modules:
  - evidence
  - doc-writer
  severity: medium
  source_ref: conversations/conv-@MCP_Tools_DocWriter.md-23-29-这段内容是如何生成和使用的.md
  scene: 代码证据（OKF sources）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:12:06+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:34Z'
---

## 结论

CodeWiki 页面 frontmatter 的 `sources` 字段由三条互不相同的链路写入，可以据字段形态反推来源：

| 生产者 | 字段形态 | 场景 |
|---|---|---|
| `_inject_evidence`（`codewiki/mcp/tools/doc_writer.py:965-1041`） | `id` / `resource` / `content_hash` | `write_doc_file` 写模块文档时自动锚定本地代码 |
| `_okf_sources_block`（`doc_writer.py:390-421`） | 额外带 `title` / `last_modified` | 引自 `source_registry.json` 的外部资料页 |
| MCP 工具 `stamp_evidence`（`codewiki/mcp/tools/evidence.py:229`） | 额外写 `repo` | Agent 手工补证据 / 复核后重盖 |

因此：只含 `id/resource/content_hash` 的条目是 auto-stamp 产物（还会带 `generated.by: codewiki/<版本>`），带 `repo` 的说明经过手工盖章。

## 手工重盖是幂等的

`stamp_evidence` 按 `id` 合并：`evidence.py:180-189` 中 `by_id.get(eid)` 命中则就地更新 `content_hash`，未命中才 append。复核后重盖不会产生重复条目。

## 落盘顺序契约

证据注入必须在 `_record_page_manifest` 之前完成，否则页面基线里的 `source_fingerprint` 记不到最终的 `sources`（`doc_writer.py:1504-1531`）。

## 自动盖章永不覆盖人工证据

`append_evidence_block` 里 `_SOURCES_KEY_RE.search(fm)` 命中已存在的 `sources` 时直接 `return content` 原样返回；写入走 `locked` + `atomic_write`。

## 自指证据

`repo://codewiki/templates/schema.yaml#L55-L65` 这类指向 `auto_evidence` 开关自身的条目是合法的——该开关正是证据机制本身的开关。
