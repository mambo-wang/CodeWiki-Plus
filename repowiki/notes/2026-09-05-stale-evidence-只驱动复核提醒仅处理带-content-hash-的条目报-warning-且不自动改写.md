---
type: architecture
title: stale_evidence 只驱动复核提醒：仅处理带 content_hash 的条目，报 warning 且不自动改写
tags:
- architecture
metadata:
  date: 2026-09-05
  task_id: 产品维护
  related_modules:
  - wiki-lint
  - evidence
  severity: medium
  source_ref: conversations/conv-@MCP_Tools_DocWriter.md-23-29-这段内容是如何生成和使用的.md
  scene: 代码证据（OKF sources）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:14:01+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:41Z'
---

## 结论

`wiki_lint._check_stale_evidence`（`codewiki/mcp/tools/wiki_lint.py:1004-1069`）是 frontmatter `sources` 的**唯一消费者**，只驱动复核提醒，绝不自动改写文档。

## 判定逻辑

- 遍历 `sources`，仅 `isinstance(entry, dict)` 且含 `content_hash` 的条目进入校验——纯外部源条目（无哈希）**不受这条检查约束**；
- `verify_entry` 重算哈希后给出四态：`ok` / `stale`（代码已变）/ `missing`（文件已删）/ `unresolvable`（路径已废），lint 按 `stale > missing > unresolvable` 取最优处置；
- 非 `ok` 才报 issue，级别是 **warning**（health_score 扣 3 分，不是 10），建议措辞为「重新核实结论后 re-stamp 或 edit_doc_file」。

## 边界

1. **行区间是上次分析的近似值**：代码增删导致行号漂移即变 `stale`；无行号条目退化为整文件哈希（`compute_file_hash`，`splitlines()` 后按行 join）。
2. **与 `stale_after` 互不替代**：`stale_after`（如 `2027-02-22`）是另一套时间新鲜度机制，与证据漂移各自独立，不能互相代替。
3. **多仓解析**：`evidence_roots()`（`wiki_lint.py:1012-1060`）按条目的 `repo` 字段 + 已注册业务仓 + `output_dir.parent` 逐个试根；`repo` 字段只在集中式工作区下出现。
4. **对外文章用中文同义词**：面向业务读者的文章（如 `docs/articles/CodeWiki-Plus系列11：机器写的Wiki凭什么可信——证据、保鲜与冲突消解.md`）把这条检查写作「证据漂移」，全文不出现 `stale_evidence` 字面量——按代码术语去搜文章会误判为「没写」。

## 使用建议

核对「文档是否描述了某机制」时，先用中文同义词（`证据漂移` / `代码证据` / `指纹`）检索，再用代码术语。

## 与相邻笔记的分工

本条讲证据的**消费侧**（谁读 `sources`、怎么判定、告警级别）；`frontmatter sources 有三个生产者，字段形态各不相同` 讲**生产侧**。两者互补。
