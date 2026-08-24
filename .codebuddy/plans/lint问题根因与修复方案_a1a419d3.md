---
name: lint问题根因与修复方案
overview: 定位并修复 repowiki lint 告警的根因：stale_refs 49 条为「删除 notes 后 index.md 未重建」的机制缺口，提供数据修复（重建索引）+ 代码加固（lint --fix 自动重建 + 删除/归档路径触发 rebuild）+ 存量数据回填（missing_aliases）。
todos:
  - id: rebuild-index
    content: 对 repowiki 调用 rebuild_index 重建 index.md，验证 49 条 stale_refs 清零
    status: completed
  - id: backfill-aliases
    content: 编写 scripts/backfill_aliases.py 回填 30 个缺 aliases 页面，验证 missing_aliases 归零
    status: completed
    dependencies:
      - rebuild-index
  - id: lint-fix-param
    content: 为 handle_lint_wiki 增加 fix 参数实现自动重建索引，并同步 registry.py schema
    status: completed
    dependencies:
      - rebuild-index
  - id: tests-verify
    content: 新增 test_lint_fix.py 用例并跑全量 pytest，最后全量 lint 验证 health_score
    status: completed
    dependencies:
      - lint-fix-param
      - backfill-aliases
  - id: distill-backlog
    content: 委托 [subagent:distill-worker] 后台补蒸馏产品维护任务积压对话
    status: completed
---

## 问题判定：是代码 bug 吗

针对之前会话分析的 repowiki lint 问题清单，逐项判定如下：

| 检查项 | 当前数量 | 判定 | 说明 |
| --- | --- | --- | --- |
| stale_refs | 49 条 (error) | **部分是代码机制缺口** | index.md 仍引用 49 个已删除的 notes（46 个历史 reject 的 deprecated 笔记 + 3 个其他）。根因：`rebuild_index()` 只在 ingest_note / write_doc_file / edit_doc_file / close_session / batch_ingest / analyze_repo 等写入路径触发，删除/清理 notes 的路径无任何索引重建触发点，导致 index.md 残留失效链接，health_score 因此掉到 0。 |
| superseded_pages | 0 条 | 非 bug | `_check_superseded_pages` 判定正确，46 条为历史 reject_note 产生的真实数据，文件已删除、检查已清零。 |
| missing_aliases | 30 条 (info) | 非代码 bug | 存量数据缺口：历史生成的 wiki 页面未带 aliases frontmatter，需数据回填。 |
| no_outlinks | 7 条 (info) | 非 bug | 内容级质量提示，已豁免系统层，剩余页面需内容补链。 |
| note_clusters | 0 条 | 已清零 | 无需处理。 |


## 修复目标

1. **数据修复（立即生效）**：重建 `index.md` 清除 49 条失效链接，恢复 health_score；批量回填 30 个缺 aliases 的 wiki 页面。
2. **代码加固（防复发）**：`lint_wiki` 增加 `fix` 参数，检测到 stale_refs 源自索引失效时自动重建索引（幂等、低风险）。
3. 不处理 no_outlinks 7 条（内容级，另行维护）。

## 技术栈

- Python（复用现有 `codewiki.mcp.tools.wiki_index.rebuild_index` 与 `codewiki.mcp.tools.wiki_lint` 检查函数，不引入新依赖）

## 实现方案

### 1. 数据修复（一次性，立即执行）

- **重建索引**：对 `d:/repos/CodeWiki-CN/repowiki` 调用 `rebuild_index(output_dir)`，重写 `wiki/index.md`，清除 49 条指向已删除 notes 的失效链接。该函数为原子写 + 模块级锁，安全幂等，与现有调用点（doc_writer.py:1264-1268、close_session.py:189-195 等）一致。
- **aliases 回填**：写一次性迁移脚本，扫描 `wiki/**/*.md`，对 frontmatter 缺失 `aliases:` 字段的页面补 `aliases: [<title>]`（无 title 时取文件名 stem），保持 YAML 原子写，不改动正文；回填后 `_check_missing_aliases` 应归零。

### 2. 代码加固（防复发）

- **`handle_lint_wiki` 增加 `fix` 参数**（默认 `false`）：
- `fix=true` 且本轮 stale_refs 全部为「index.md 引用失效 notes」时，自动调用 `rebuild_index(output_dir)` 后重跑 stale_refs 检查，将残留结果返回；修复逻辑包 try/except 保持非致命（沿用现有风格）。
- 只重建索引，不修改正文文档，避免误伤。
- **`registry.py` 的 lint_wiki schema 增加 `fix` 布尔参数**（description 说明用途，required 不含它，向后兼容）。
- 删除/归档 notes 路径（若未来新增 delete/archive 工具）须在末尾触发 `rebuild_index`——本次以 lint 自愈兜底，不新增删除工具。

### 3. 测试与验证

- 在 tests 下新增 lint fix 用例：构造含失效链接的临时 wiki 目录 → `fix=true` 后 stale_refs 归零、index.md 被重建且不改变正文文件。
- 全量回归：`python -m pytest tests/` 确认无破坏；对 repowiki 跑 `lint_wiki(checks=all)` 验证 health_score 恢复。

## 关键设计决策

- 修复入口选 `lint_wiki --fix` 而非自动常开：保持 lint 只读审计语义，fix 由调用方显式触发，避免副作用。
- 索引重建复用 `rebuild_index()`，不重复实现扫描逻辑（DRY），原子写保证并发安全。
- aliases 回填为一次性数据脚本，不进入常驻代码路径（YAGNI），避免给 lint/写入链路增加负担。

## 目录结构

```
codewiki/
├── mcp/
│   ├── registry.py            # [MODIFY] lint_wiki schema 增加 fix 布尔参数
│   └── tools/
│       └── wiki_lint.py       # [MODIFY] handle_lint_wiki 增加 fix 参数 + 自动重建索引逻辑
scripts/
└── backfill_aliases.py        # [NEW] 一次性脚本：为 wiki/ 下缺 aliases 的页面回填 frontmatter
repowiki/
└── wiki/index.md              # [MODIFY] 由 rebuild_index 重建，清除 49 条失效链接
tests/
└── test_lint_fix.py           # [NEW] lint_wiki fix 参数单元测试（临时目录构造失效链接）
```

## Agent Extensions

### SubAgent

- **distill-worker**
- 用途：后台补蒸馏本任务（产品维护）积压的 1 条历史对话，产出草稿笔记与待确认记忆，不阻塞主修复流程
- 预期结果：`distill_conversation(prepare→submit)` 完成，待确认记忆/草稿笔记进入任务上下文供用户确认