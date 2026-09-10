---
type: procedure
title: 删除导入文档的三种路径：源文档 retract_source(先 dry_run)、笔记 reject_note、wiki 页面无工具级删除
tags:
- procedure
metadata:
  date: 2026-09-10
  related_modules:
  - source
  - note
  - doc
  - repowiki
  severity: medium
  source_ref: conversations/conv-我做方案设计的时候，是否应该把设计方案放到repowiki中呢.md
  scene: 知识库维护 / 删除资产
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:48:23+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:18Z'
---

## Background
用户问「想删除某个导入的文档，用哪个工具方法」。三种资产三种路径，都倾向「标记/移入 .trash」而非物理删除。

## 1. `ingest_source` 导入的外部文档 → `retract_source`
唯一有正式删除路径的资产（`registry.py:1460-1492`）。两种模式（`source_ingest.py:747-752`）：
- `flag_stale`（默认）：registry 标 `status: retracted`+`retracted_at`，**文件保留**；引用它的页报 `stale_sources` 提醒。
- `remove_refs`：文件移到 `repowiki/.trash/`（重名加时间戳，非物理删除、可恢复），清理所有 wiki 页 frontmatter 的 `source_refs`。
两种模式都：更新 registry → 追加 `wiki/log.md` → 重建 BM25 索引。要点：**先 `dry_run: true`** 看要移动哪个文件、清多少引用；`name` 查 `repowiki/.meta/source_registry.json`。注意 `remove_refs` 只做「移文件+清 source_refs」，该源派生的 `wiki/sources/*.md` 页面不在范围内，需另行 `edit_doc_file` 或手动删。

## 2. `ingest_note` 写入的笔记 → 无删除工具，用 `reject_note`
`reject_note(note_file=..., reason=...)` 置 `deprecated` 并剔除检索（`note_lifecycle.py:93-116`）。物理删文件只能手动 `rm`+重建索引，不推荐（会留悬空引用）。

## 3. `write_doc_file` 生成的 wiki 页面 → 无删除工具
`edit_doc_file` 只有 `str_replace`/`insert`/`undo`，无 delete（`doc_writer.py:1667`）。删页面只能手动删文件再重建索引。

## 一句话
源文档 `retract_source(mode='remove_refs')` 先 dry_run；笔记 `reject_note`；wiki 页面无工具级删除。别绕过工具直接 `rm`。
