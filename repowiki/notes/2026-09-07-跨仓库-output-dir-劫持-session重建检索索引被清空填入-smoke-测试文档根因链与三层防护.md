---
type: pitfall
title: 跨仓库 output_dir 劫持 session：重建检索索引被清空填入 smoke 测试文档（根因链与三层防护）
tags:
- pitfall
- sessionstore
metadata:
  date: 2026-09-07
  task_id: 他山之石
  related_modules:
  - cache
  - wiki_search
  - session
  - store_bridge
  severity: high
  source_ref: conversations/conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md
  scene: 检索索引维护
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.1
  at: 2026-09-07 01:41:26+00:00
stale_after: 2027-03-06
origin: conversation
reject_reason: 用户评审拒绝收录
---

## Background

新写入 `wiki/queries/` 的文档 `query_wiki` 检索不到，而 `wiki/comparisons/` 的能搜到——这是假象，真实原因是整个 repo 根检索索引被污染后清空重填。

## 根因链（5 环）

1. 某次 smoke/harness 运行以 `repo_path=<真实仓库>` + `output_dir=<Temp>/codewiki_smoke_*` 调 `analyze_repo`，`cache.set_output_dir()` 把这个跨仓库临时目录持久化进 repo 根 DB 的 `repo_meta.output_dir`。
2. `SessionStore.find_or_restore()` 恢复 session 时优先用 `cache.get_output_dir()`（smoke 路径）而非 `<repo>/repowiki` fallback → 后续无显式 output_dir 参数的会话全部被劫持到 smoke 目录。
3. `write_doc_file` 等工具因 session.output_dir 劫持把文档误写入 smoke 目录；`close_session` 重建时经 session 共享 cache（repo 根 DB）执行 `build_search_index(smoke)` → 真实索引（应有 284 文件）被清空，填入 smoke 目录仅 7 个测试文档。
4. comparison 页恰好在 smoke 目录也有误写副本，故验证"通过"是命中副本；query 页只写进真实 repowiki → 搜不到。
5. 铁证：索引 `total_docs=7` vs 磁盘 284 个 md；索引里 5 个 doc 对应文件在真实 repo 中不存在（`test_doc.md`、`smoke-test-decision-*` 等）。

## 修复（三层）

- 数据层：用真实 output_dir 重建索引（7→207 docs）；删除被污染的 `repo_meta.output_dir` 记录。
- 代码层 1：`cache.py` 的 `set_output_dir` 拒绝 repo 外 output_dir（当 repo 自己拥有 `repowiki/` 时）；`get_output_dir` 恢复时同样拦截——外来路径不再被持久化/继承（centralized 合法场景保留）。
- 代码层 2：`wiki_search.py` 新增 `_cache_serves_output_dir` 归属校验 helper，4 处 `session.cache` 使用点（build/update/search/coverage）仅在 cache DB 确实归属该 output_dir 时生效——纵深防御，防 session 缓存再次清空他库索引。
- 运行层：`close_session(force, output_dir=repowiki)` 清理 server 内存中被劫持的 smoke session（TTL 2h，`find_or_restore` 优先返回活跃内存 session）。

## 验证与回归

- 端到端：MCP `query_wiki(repo_path)`（不带 output_dir）命中新写页面（top 18.97）。
- 模拟：smoke 场景被 `set_output_dir` 拒绝、repo 内目录正常、归属校验 smoke=False/repowiki=True。
- 回归：`test_index_freshness` + `test_centralized_layout_fixes` + `test_change_analysis` = 50 passed。

## 启示

- `output_dir` 解析顺序 session.output_dir > 显式参数 > repo_path fallback（`store_bridge.resolve_output_dir`），session 被污染则一切无显式参数调用被劫持。
- 代码防护需 MCP server 重启后加载（旧进程跑旧代码），数据与 session 状态修复即时生效。
- `write_doc_file` 落盘 ≠ 可检索：检索可达性取决于索引是否真覆盖该目录。
