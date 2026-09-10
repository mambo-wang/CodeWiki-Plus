---
type: pitfall
title: retract_source(remove_refs) 不清理 metadata 嵌套的 source_refs，lint stale_refs 也漏，且源
  name 可复用碰撞致派生页残留
tags:
- pitfall
- weknora
metadata:
  date: 2026-09-10
  related_modules:
  - source
  - lint
  - repowiki
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-撤回已导入的外部文档-撤回外部文档工作流。当-`inges.md
  scene: 知识库维护 / 撤回源文档
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:49:19+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:19Z'
---

## Background
执行 `retract_source(name="README_CN", mode="remove_refs")` 撤回 TencentDB Agent Memory README，dry_run 报清理 12 处 `source_refs`，lint `stale_sources`/`stale_refs` 均 0 issues。但复核发现 `wiki/sources/README_CN.md` 派生页（旧 WeKnora 内容）仍挂着 `source_refs: [README_CN]`，指向已退役源——lint 没报，retract 也没清。

## 事实（工具/检查盲区）
- `remove_refs` 只清 frontmatter **顶层** `source_refs`；嵌套在 `metadata:` 下的引用不在处理范围（`source_ingest.py:797-815` 行为），12 处清理未覆盖到派生页。
- `lint_wiki` 的 `stale_refs` 同样只扫顶层 `source_refs`，漏掉 `metadata` 嵌套 → 已退役源仍被引用却显示 0 issues。
- 根因叠加**源 name 复用/碰撞**：同一 `README_CN` 标识符先后被 WeKnora README（2026-08-03 导入）与 TencentDB README（2026-09-04 注册）占用；旧派生页的 `source_refs` 现在指向已退役源。

## 正确做法
- 撤回后必须精确复核残留：`src:README_CN:[0-9]`（排除 `README_CN_2.0:`）区分碰撞 name；手动读派生页确认其 `metadata.source_refs`。对 lint `stale_refs` 的 0 结果**不可全信**。
- 派生页无工具级删除：手动移 `repowiki/.trash/` + `close_session(force=true)` 重建索引；删前用 `[[README_CN` 查入链确认无断链。
- 派生页本身（`wiki/sources/<name>.md`）不在 `remove_refs` 范围内，需另行 `edit_doc_file` 或手动处理。

## 关联
与 procedure 笔记『删除导入文档的三种路径：源文档 retract_source(先 dry_run)、笔记 reject_note、wiki 页面无工具级删除』互补：那条讲路径，本条讲 retract/lint 的 `metadata` 嵌套盲区与 name 碰撞实测。
