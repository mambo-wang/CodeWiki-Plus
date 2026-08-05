status: resolved
type: spec
title: 借鉴 TAM 对话→Wiki 提取（MVP）
labels: ready-for-agent
body: |
  # Spec: 借鉴 TencentDB Agent Memory 的对话→Wiki 提取能力（MVP）

  > 源自 wayfinder 评估（`.scratch/team-memory-fusion/`）结论：可行，推荐借鉴式，3–6 人周。
  > 本研究只落地 MVP：对话经验沉淀为可检索 Wiki 笔记，复用现有知识飞轮。

  ## Problem Statement

  用户在使用 Agent 时反复重复已走过的弯路：纠正、调试结论、方案取舍等"对话中产生的经验"散落在聊天记录里，换一次 Session 就丢失，下一个 Agent 无从继承。CodeWiki-CN 已有把"代码/文档"变成 Wiki 的能力（`codewiki/` → `repowiki/`），也有人工确认的笔记沉淀（`ingest_note` + 确认飞轮），但**缺少从"对话流"自动提炼经验资产**的能力——即 TAM 的 L0（原始对话）→ L1（语义原子）分层抽取。用户希望借鉴 TAM 这一高价值切片，在 CodeWiki-CN 自身 Python 体系内实现，不引入 Node 依赖或外部服务。

  ## Solution

  在 CodeWiki-CN 现有知识飞轮（`ingest_note` / `confirm_note` / `reject_note` / `query_wiki`）之上，新增两级能力：
  1. **对话采集入口**：把一次 Agent 对话的原始 turns 落盘到 `repowiki/raw/`（该目录已存在）。
  2. **L0→L1 蒸馏**：LLM 把原始对话蒸馏为语义原子（事实 / 偏好 / 约束 / 事件），生成草稿 note，经现有 `confirm_note` 人工确认门后才正式并入 `repowiki/notes/`，最终可被 `query_wiki` 检索。

  不新建存储、不新建确认门、不引入 TAM 代码；仅复用"对话经验"专属知识流，不替代架构级 Wiki 生成。

  ## User Stories

  1. As an Agent operator, I want to capture the raw transcript of a session, so that conversation-derived experience isn't lost when the session ends.
  2. As an Agent, I want the system to distill concrete facts/preferences/constraints/events from a raw conversation, so that I don't have to re-read the whole transcript next time.
  3. As a human reviewer, I want distilled experience to land as a draft that I must confirm before it enters the knowledge base, so that low-quality or hallucinated extractions never pollute `repowiki/notes/`.
  4. As an Agent, I want confirmed conversation-notes retrievable via `query_wiki`, so that past session lessons inform the current task.
  5. As a team lead, I want conversation-derived notes visually distinct from architecture Wiki pages, so that I can tell "this came from a chat" vs "this is code structure".
  6. As an Agent, I want to trigger distillation on-demand (e.g. at session end or on user command), so that extraction doesn't run wastefully mid-task.
  7. As a reviewer, I want a one-click reject path for a bad draft note, so that noise is removed cheaply.
  8. As an Agent, I want the distiller to cite the source conversation turn, so that a recalled fact can be traced back to its origin.
  9. As a power user, I want to attach a conversation file (export) for distillation, so that past sessions I didn't capture live can still be ingested.
  10. As a maintainer, I want the distiller to respect the existing `note_type` taxonomy (decision/lesson/pitfall/architecture/workaround), so that conversation notes blend with the current note model.
  11. As an Agent, I want duplicate detection against existing `notes/` before a draft is proposed, so that we don't re-file the same lesson twice.
  12. As a reviewer, I want to see a confidence/coverage indicator on a draft (how much of the conversation was distilled), so that I can judge draft completeness at a glance.
  13. As a developer, I want the distillation to run through the same `ingest_note` path as manual notes, so that there's one indexing/persistence code path, not two.
  14. As an Agent, I want distillation to skip trivial chit-chat and only surface decision-worthy content, so that the knowledge base stays signal-dense.
  15. As a team lead, I want conversation notes scoped to the workspace (not global), so that experience stays relevant to the repo it was captured in.

  ## Implementation Decisions

  - **Seam**: reuse the existing knowledge loop. New capability adds exactly one new stage (distill) that feeds the existing `ingest_note` handler; collection adds a raw-transcript writer to `repowiki/raw/`. No new storage, no new confirmation gate.
  - **Collection entry**: a new MCP tool (e.g. `capture_conversation`) writes raw turns (with session id, timestamps, actor labels) to `repowiki/raw/<session>.md`. Reuses the workspace session concept already used by `ingest_note`/`query_wiki`.
  - **Distill stage**: a new MCP tool (e.g. `distill_conversation`) reads a raw transcript, calls the LLM to produce L1 semantic atoms typed into the existing `note_type` taxonomy, and creates draft notes via the existing `ingest_note` with `status='draft'` (unconfirmed). Output goes through the existing `confirm_note`/`reject_note` gate.
  - **Indexing/persistence**: zero new — drafts and confirmed notes flow through the existing BM25 index used by `query_wiki`. `repowiki/notes/` is the sole note store.
  - **Traceability**: each distilled note records a `source_conversation` frontmatter field pointing at the `repowiki/raw/<session>.md` turn range, satisfying the citation user story.
  - **Raw lifecycle (new)**: `repowiki/raw/` is a *transient staging area*, not a knowledge store. It is **excluded from `query_wiki` retrieval** by design (BM25 only indexes `wiki/` and `notes/`; the legacy keyword search explicitly skips `raw/`), so volume there does **not** slow down queries — it only costs disk. To prevent unbounded growth: (a) raw files are **deleted once their distillation completes and all drafts are confirmed or rejected** (best-effort cleanup in `distill_conversation`); (b) a `capture_conversation` flag `--keep-raw` lets a reviewer retain a specific transcript for auditing; (c) a configurable retention cap (default e.g. 7 days) auto-prunes untouched raw files. Raw is never the source of truth — confirmed notes in `notes/` are.
  - **De-dup**: before proposing a draft, the distiller queries `query_wiki` over `notes/` for near-duplicates and suppresses/merges them (reuses existing retrieval).
  - **Distinction**: conversation notes carry `origin: conversation` in frontmatter so they're visually/semantically separable from architecture Wiki pages in `wiki/`.
  - **Scope**: notes are workspace-scoped, consistent with how `ingest_note` already operates per workspace session.
  - **No TAM code**: the design only borrows TAM's L0→L1 layering *idea*; all implementation is native Python in `codewiki/`, no dependency on Team-Agent-Memory.
  - **MCP-exposed**: both new tools registered in the existing MCP server (`codewiki/mcp/registry.py`) so agents call them like any other tool.
  - **LLM injection (stateless tool)**: `distill_conversation` is a *stateless* MCP tool — it does **not** hold or configure an LLM itself. The LLM capability is **injected by the caller**: preferred path is an IDE subagent invoking the tool (uses CodeBuddy's built-in model — no LLM config needed, isolated context, async/non-blocking); alternatively the `BackgroundWorker` thread may call it (then `MAIN_MODEL`/`LLM_BASE_URL` must be configured, per `codewiki/src/fe/background_worker.py`). The distillation is LLM-heavy and must run off the main thread.
  - **Trigger shapes (T0 decision: both)**: (a) manual command — user/agent explicitly calls `distill_conversation` (primary); (b) optional IDE hook — auto-calls `capture_conversation` on conversation events, off by default, async, only stages raw (no distillation). Distillation always runs via the subagent/worker path, never inline in the hook.

  ## Testing Decisions

  - **Test external behavior, not internals**: tests assert (a) a raw transcript produces draft notes of correct `note_type`, (b) drafts enter `notes/` only after `confirm_note`, (c) `query_wiki` retrieves confirmed conversation notes, (d) re-running distillation on the same transcript does not duplicate existing notes.
  - **Modules under test**: the new distill/collection tools (behavior via the MCP handler surface), and the existing `ingest_note`/`confirm_note` integration (unchanged path).
  - **Prior art**: follow the existing MCP tool tests pattern in `codewiki/mcp/tools/` (the `handle_ingest_note` / `handle_confirm_note` suites); add fixtures with sample raw transcripts under `tests/`.
  - **Quality guard**: add a small golden-set of transcripts with expected note extractions to catch extraction regressions (the "hallucination" risk).
  - **Integration seam**: one test that exercises `capture_conversation` → `distill_conversation` → `confirm_note` → `query_wiki` end-to-end through the MCP handlers, mirroring how the codebase tests other multi-tool flows.

  ## Out of Scope

  - L2 scenario clustering and L3 user/team persona modeling (deferred beyond MVP).
  - Skill assets as a first-class registry (TAM's Skill system) — only loosely inspired, not built.
  - MemoryProxy-style transparent injection of memory into LLM calls.
  - Multi-agent / team collaboration primitives and ACL / user isolation.
  - Introducing or bridging Team-Agent-Memory code, Node services, or its storage backends.
  - Replacing or duplicating the existing architecture Wiki generation (`codewiki/` → `repowiki/wiki/`).

  ## Further Notes

  - MVP effort ≈ 3 人周; full conversation-to-wiki-with-Skill ≈ 3–6 人周.
  - Top risk: dialogue collection link is absent in CodeWiki-CN today — the `capture_conversation` entry point is the primary net-new engineering, and its trigger (IDE hook vs manual command) should be chosen early.
  - De-dup against `wiki/` vs `notes/` boundary must be explicit to avoid two overlapping knowledge bases (architecture Wiki vs conversation notes).
  - Full feasibility rationale: `docs/team-memory-fusion-feasibility.md`.
