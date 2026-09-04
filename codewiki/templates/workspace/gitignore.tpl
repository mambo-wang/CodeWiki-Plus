# ── 业务子仓库（独立 clone，本仓 git 一律不追踪）──────────────────────
# 新增业务仓时必须在此登记，否则 `git add .` 会将其作为 embedded
# repository（裸 gitlink）误提交，破坏"提交不打架"的结构性保证。
{{REPO_IGNORE_LINES}}

# ── 通用忽略 ────────────────────────────────────────────────────────
__pycache__/
*.pyc
.DS_Store
Thumbs.db
# 本机分析缓存（centralized 布局下落在工作区根，可重建，不入库）
.codewiki/
repowiki/.meta/search_index.json
repowiki/.meta/retrieval_stats.db
repowiki/.meta/telemetry-local/
# Team-layout Phase 1（D1）：可重建派生物不入库——索引/元数据/运行态本地重建，
# 入库只会制造整文件重写冲突（详见 docs/团队化文件冲突治理与同步策略设计方案.md）
repowiki/wiki/index.md
repowiki/.meta/edit_history.json
repowiki/.meta/metadata.json
repowiki/.meta/module_tree.json
repowiki/.meta/symbol_map.json
repowiki/.meta/project.json
repowiki/.meta/overview_refs.json
repowiki/.meta/aggregate_state.json
repowiki/.meta/source_registry.json
repowiki/.meta/task_bindings/
repowiki/.meta/locks/
repowiki/tasks/.index.json
repowiki/distill-jobs.json
# KnowledgeStore 锁文件（集中存放于 .meta/locks/；*.lck 兜底兼容旧版散落 sidecar）
*.lck
