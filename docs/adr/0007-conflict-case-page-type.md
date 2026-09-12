# 0007. 冲突案卷是独立页面类型，不是笔记

日期：2026-09-12

两条 Wiki 笔记矛盾时，本仓此前只有 prompt 约定（矛盾写进 open-questions，`note_consolidation.py`），矛盾存续期间任何 `query_wiki` 都可能盲取单边结论且无警示（2026-08 蒸馏-worker 笔记错误归因案为真实先例：错误归因存续 15 天，靠一次蒸馏 merge 才修正）。决定把「冲突」做成一等对象：顶级 `conflicts/` 页面类型，`flag_conflict`（手动声明）+ `adjudicate_conflict`（裁决，动作集 `keep_a/keep_b/coexist/reject`，内部复用 `reject_note` 原语）两个工具，账本即 git。调研来源：HL-Mem v1.1.7 冲突治理子系统（`docs/HL-Mem-调研与借鉴分析.md`）。

## Considered Options

- `notes/conflicts/` 子目录（复用 note 机制）— 否决：冲突是裁决状态不是知识，进 `notes/` 会把治理元记录混进检索语料。
- 双向 `conflict_with` frontmatter 引用 — 否决：双向引用改一边忘一边，恰是要消灭的「冲突无身份、易漂移」问题。
- 移植 HL-Mem 案卷子系统 — 否决：约 4000 行中一半绑死 SQLite 四表与 CAS；其自动发现依赖 slot 注册表底座（`conflict_key` = 规范化 subject+slot+qualifier 的 SHA-256），本仓自由 Markdown 无此物，且 Mode C 蒸馏实测「弱冲突多为误报」有前科。**自动发现一并排除，只做 Agent 手动声明。**

## Consequences

- 冲突案卷不进知识检索语料；`query_wiki` 命中 claimant 时附加「存在未裁决冲突」标注。
- `open` 冲突超期未裁决由 `lint_wiki` 发 warning。
- 实施挂独立任务「冲突一等对象」，排期与 Phase5 批次二（T5/T6，动同一片 note_lifecycle/note_query 区域）错开。
