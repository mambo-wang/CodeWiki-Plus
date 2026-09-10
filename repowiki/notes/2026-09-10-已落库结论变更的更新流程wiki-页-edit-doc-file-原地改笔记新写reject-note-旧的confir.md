---
type: procedure
title: 已落库结论变更的更新流程：wiki 页 edit_doc_file 原地改；笔记新写+reject_note 旧的+confirm；ADR 须回源同步
tags:
- procedure
metadata:
  date: 2026-09-10
  related_modules:
  - note
  - doc
  - repowiki
  severity: medium
  source_ref: conversations/conv-我做方案设计的时候，是否应该把设计方案放到repowiki中呢.md
  scene: 知识库维护 / 结论更新
  compiled_into:
  - skills/repowiki-conclusion-update/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:48:19+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:15Z'
---

## Background
已落库的 repowiki 结论发生变化时如何更新。分两条路径。

## 1. wiki 页面（`wiki/queries/`、`wiki/comparisons/`）→ 就地编辑
用 `edit_doc_file`（`codewiki/mcp/tools/doc_writer.py:1667,1747,1797`）：`str_replace` 改结论段落（按 body 去重，不受 frontmatter 回声干扰）；`insert` 补「决策变更记录」小节；`undo` 回滚（历史在 `.meta/edit_history.json`，加锁防并发）。编辑后自动刷新 page manifest、BM25 索引、`wiki/log.md`。⚠️ 页面带 `sources`（content_hash）时，改完 `lint_wiki` 的 `stale_evidence` 只报复核提醒、不自动改写。

## 2. 笔记结论（`notes/`）→ 新写 + 显式退役旧的
`ingest_note` 不覆盖同名结论：同 slug 同正文返回 `already_exists`；同 slug 不同正文则追加 6 位 hash 生成**新文件**。标准三步：
1. `ingest_note(note_type="decision", ...)` 写新结论，正文点明「修正/取代哪条、为什么」；
2. `reject_note(note_file="notes/旧结论.md", reason="被 <新> 取代：…")` → 置 `deprecated` 并从检索剔除（`note_lifecycle.py:93-116`）；`superseded` 归一成 `deprecated`；
3. `confirm_note(note_file=新)` → 转 `stable`、续期 `stale_after`。
同主题多条合成一条用 `note_merge`（标题 replace/正文 append/tags union，产物仍 draft）。

## 3. 只是到期复核 → 续期或退役
类型窗口：decision/architecture 365 天、pitfall/lesson 180、workaround 45。仍成立→`confirm_note` 续期；不成立→`reject_note`。

## 4. 回源
结论变化源头通常在 `docs/`：先改 `docs/adr/NNNN-*.md`（与既有 ADR 冲突要显式写 `Contradicts ADR-000X`），再更新 repowiki，否则会二次漂移。

## 一句话判据
改「同一结论的表述/证据」→ `edit_doc_file`；改「结论方向」→ 新写 decision 笔记 + `reject_note` 旧的 + 同步 ADR。
