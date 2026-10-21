---
type: pitfall
title: "confirm_note 静默失败根因：text.find(\"
status: stable
---\",3) 探测 frontmatter 栅栏被值内 --- 误截断；收敛函数 find_frontmatter_end() 已落地"
tags: ["pitfall"]
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 日常维护
  source_session: "dc4c7f117deb422892911aea88082116"
  related_modules: ["note_writer", "frontmatter", "mcp-tools"]
  severity: medium
  source_ref: "conversations/conv-@command-codewiki-distill-conversations.md"
  scene: "日常维护：批量确认草稿笔记时实证的产品 bug 与修复"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.15.0, at: 2026-10-21T09:04:44Z }
stale_after: 2027-04-19
origin: conversation

---

## 现象

confirm_note 返回 stable，但笔记文件 frontmatter 实际仍是 draft——确认静默失败；且再次 confirm 会把手工修复过的文件覆盖回损坏态（返回成功却写回旧内容）。

## 根因

`codewiki/mcp/tools/note_writer.py`（`_note_source_ref`、`_apply_status_to_file` 两处）用 `text.find("---", 3)` 探测 frontmatter 闭合栅栏。当 title 值内含字面 `---`（如超长文件名折行落进行内）时误截断 YAML 块 → YAML 解析失败 → 走 regex 回退，把伪 `status: stable` 行当真并原样写回。讽刺的是，那条「折行 `---` 被当作栅栏」的踩坑笔记（2026-09-20）自己的 frontmatter 就被这个 bug 写坏了。

## 修复（2026-10-21 已落地）

1. `codewiki/src/frontmatter.py` 新增收敛函数 `find_frontmatter_end()`：逐行扫描，闭合栅栏必须是整行 `---`，值内的 `---` 不再误命中；
2. `note_writer.py` 两处改调收敛函数；
3. `tests/test_frontmatter_roundtrip.py` 新增 2 项回归测试（单元 + 端到端复现原 bug 场景），10/10 通过；`test_backfill_note_authors` 5/5 无回归；ruff 全过。

## 排查方法（可复用）

核对笔记状态必须解析 frontmatter，不能全文 grep `status:`——正文里引用 `status: draft` 字样会误判。本次用 PowerShell `Select-String` 限定 frontmatter 行范围逐文件提取真实 status，才发现 28 条「已确认」中最后 1 条实际未生效。

## 遗留

全仓 `find("---", 3)` 同构写法共 31 处（evidence、doctrine、wiki_lint、close_session、source_ingest、page_manifest、note_query、note_lifecycle、note_consolidation），本次只修了实证 bug 所在的 note_writer，其余调用点语义相同，待统一迁移到 `find_frontmatter_end()`。

## 关联

本条更新 `notes/2026-09-20-聚合写场景块时超长笔记文件名含-----折行落行首会被当作-frontmatter-闭合栅栏.md` 中「全仓约 30 处同款模式待收敛成共享 helper」的进度：收敛函数已落地于 `codewiki/src/frontmatter.py`，剩余调用点迁移未完成。与 `notes/2026-09-12-重写-frontmatter-文件时闭合栅栏后必须保留换行lenient-正则会静默吞掉正文且测试可能侥幸通过.md` 根因不同（那条是写入侧栅栏后缺换行），三者同属 lenient 解析把结构性错误降级为静默偏移的实例。
