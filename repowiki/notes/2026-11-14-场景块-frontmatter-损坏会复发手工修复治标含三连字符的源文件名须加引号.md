---
type: pitfall
title: "场景块 frontmatter 损坏会复发：手工修复治标，含三连字符的源文件名须加引号"
tags: ["pitfall"]
metadata:
  date: 2026-11-14
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["MCP_Tools_Knowledge", "MCP_Tools_DocWriter"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的.md"
  scene: "场景块 frontmatter 数据修复"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-14T01:36:11Z }
stale_after: 2027-05-13
origin: conversation

---

## 现象（2026-11-13 实测，本人 Read 复核）

`repowiki/wiki/scenarios/IDE-Hook采集链路方法.md` 与 `发布与依赖治理方法.md` 的 frontmatter 结构性损坏：

- `IDE-Hook采集链路方法.md:27` 是截断的源引用 `- notes/2026-09-07-userpromptsubmit-的-ide-hook`，文件名后半截粘在闭合栅栏上成为 :33 的 `---enable-是-draft-技能提示通道advisory只.md`（真实文件 `2026-09-07-userpromptsubmit-的-ide-hook---enable-是-draft-技能提示通道advisory只.md` 存在）。
- 同一 frontmatter 里有**两套重复的 summary/heat/confidence_level 块**（:30-32 与 :34-36，heat 分别为 6 与 4），是两次聚合更新撞车的痕迹。
- `发布与依赖治理方法.md:36,43` 同款截断（会话共实测 3 条截断断链，真实文件均存在，前缀匹配证实）。

后果：严格 YAML 解析下**整块 frontmatter 解析失败**，该场景块的全部 `source_notes` 不可审计——不是「3 条断链」这么轻。会话实测 11 个场景块中 9 块严格解析成功（102 refs、0 断链）、2 块整体失败。

## 与既有 stable 笔记的关系（修正）

- `notes/2026-09-20-聚合写场景块时超长笔记文件名含-----折行落行首会被当作-frontmatter-闭合栅栏.md` 记录的正是这同两个文件，其 Recovery 写「手工修复后重提聚合报告即通过、lint 0 error」。本次实测损坏仍在 → **手工修复只治标**：写路径既不校验源目标存在（`note_consolidation.py:562-578`、`skill_creator.py:498-523`），也不给含 `---` 的文件名加引号，损坏会再积累。该 stable 笔记宜补「根因在写路径 + 修复须加引号 + 需防复发」口径。
- `notes/2026-10-21-confirm-note-静默失败根因textfind---3-探测-frontmatter-栅栏被值内-----误截断.md` 记载解析侧收敛函数已落地 `codewiki/src/frontmatter.py`、剩余调用点迁移未完成；本条说明即使解析侧收敛，**写入侧不校验/不加引号仍会造出新的结构性损坏**，两者不可互代。

## 正确做法（修复方案在会话中为推荐、待用户裁决）

- 要做的是**重建 frontmatter**，不是替换 3 个字符串：恢复完整文件名并 **YAML 加引号**（防 `---` 落行首复发）、合并重复 summary/heat 块（推荐 summary 取后块、heat 取 max）、修正闭合栅栏。
- sanctioned 修复路径：`edit_doc_file` 的 `str_replace` **可以改 frontmatter**——body 内 0 命中时回退全文替换（`codewiki/mcp/tools/doc_writer.py:1782-1789`，注释明示 "Fall back to a whole-document search (e.g. editing frontmatter)"）；`insert` 被禁止落入 frontmatter 区（:1832-1845）。
- 验收：严格 YAML 解析通过 + 重扫断链归零，不能只看 lenient 解析「能读出字段」。

## Rationale

lenient 解析会把结构性损坏降级为「字段偏移」，让人误判成普通字符串笔误；同一处损坏复发说明必须堵写路径，否则修完再脏。
