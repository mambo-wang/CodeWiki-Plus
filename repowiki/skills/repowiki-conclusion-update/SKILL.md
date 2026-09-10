---
name: repowiki-conclusion-update
description: 已落库 repowiki 结论发生变化时，按「结论方向 vs 表述」分流：方向变则新写 decision 笔记+reject_note 旧+confirm 并回源 ADR，仅表述/证据变则 edit_doc_file 原地改
type: Skill
status: stable
generated:
  by: codewiki/5.9.0
  at: "2026-09-10T09:06:45Z"
stale_after: 2026-12-09
metadata:
  summary: 已落库结论变更的更新流程：wiki 页 edit_doc_file 原地改 / 笔记 reject+confirm 新写 / ADR 回源同步
  source_refs: ["notes/2026-09-10-已落库结论变更的更新流程wiki-页-edit-doc-file-原地改笔记新写reject-note-旧的confir.md"]
  revisions: ["at: \"2026-09-10T09:06:45Z\""]
  reason: created from candidate materials
  source: skill_creator
  installed_at: "2026-09-10T09:37:32Z"
  installed_to: .codebuddy/skills/repowiki-conclusion-update/
  installed_hash: "sha256:4c47466a3c507d68c911cf1bc514c299dbe4d9cb7989c31ffe4a303cf23bf10a"
---


## 工作场景
已落库的 repowiki 结论（wiki 页面或 notes/ 笔记）需要变化时使用：知识库维护、方案演进、设计裁决变更、结论到期复核。

## 适用条件
- 结论已 stable 或 draft 存在于 repowiki（wiki/queries/、wiki/comparisons/、notes/）。
- 须先区分「改同一结论的表述/证据」与「改结论方向」两类（见判断逻辑）。
- 不用于未落库的新结论（直接 ingest_note）；不用于物理删除（用 reject_note 标记而非删文件）。

## 核心 SOP
依据: notes/2026-09-10-已落库结论变更的更新流程wiki-页-edit-doc-file-原地改笔记新写reject-note-旧的confir.md 的「分两条路径」与「标准三步」。

1. **wiki 页面**（wiki/queries/、wiki/comparisons/）→ `edit_doc_file` 就地编辑：
   - `str_replace` 改结论段落（按 body 去重，不受 frontmatter 回声干扰）；
   - `insert` 补「决策变更记录」小节；
   - `undo` 回滚（历史在 `.meta/edit_history.json`，加锁防并发）。
   - 编辑后自动刷新 page manifest、BM25 索引、`wiki/log.md`。
   - ⚠️ 页面带 `sources`(content_hash) 时，改完 `lint_wiki` 的 `stale_evidence` 只报复核提醒、不自动改写。
2. **笔记结论**（notes/）→ 新写 + 显式退役旧的：
   - `ingest_note(note_type="decision", ...)` 写新结论，正文点明「修正/取代哪条、为什么」；
   - `reject_note(note_file="notes/旧结论.md", reason="被 <新> 取代：…")` → 置 `deprecated` 并从检索剔除（note_lifecycle.py:93-116）；superseded 归一成 deprecated；
   - `confirm_note(note_file=新)` → 转 stable、续期 stale_after。
   - 同主题多条合成一条用 `note_merge`（标题 replace/正文 append/tags union，产物仍 draft）。
3. **仅到期复核（未变）→ 续期或退役**：decision/architecture 365 天、pitfall/lesson 180、workaround 45 窗口；仍成立 `confirm_note` 续期，不成立 `reject_note`。
4. **回源**：结论变化源头通常在 `docs/`，先改 `docs/adr/NNNN-*.md`（冲突写 `Contradicts ADR-000X`），再更新 repowiki，避免二次漂移。

## 判断逻辑
- 改「同一结论的表述/证据」→ `edit_doc_file` 原地改（路径 1）。
- 改「结论方向」→ 新写 decision 笔记 + `reject_note` 旧 + `confirm` 新 + 同步 ADR（路径 2）。
- 仅过期未变 → 路径 3 续期/退役。

## 禁忌与反模式
- 勿用 `ingest_note` 想「覆盖」同名旧结论：同 slug 同正文返回 `already_exists`，不同正文只追加新文件，旧结论仍 stable 占坑 → 必须显式 `reject_note` 旧的。
- 勿直接物理删除 notes 文件：用 `reject_note` 标记 deprecated，保持溯源链与检索剔除可审计。
- 勿只改 repowiki 不回源 `docs/adr`：会造成二次漂移（docs 与 wiki 结论打架）。
- 页面带 `sources` 时改完别指望 lint 自动改写证据，只报提醒。

