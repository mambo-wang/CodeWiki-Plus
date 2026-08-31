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
