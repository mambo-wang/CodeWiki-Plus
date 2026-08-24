---
type: Conversation
title: "conversation 20260824T050116Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:16Z }
captured_at: "2026-08-24T05:01:16Z"
content_hash: "sha256:8ac202853931e9ae2c4b6f34e9a0ca757954037efe891babdc7209c114913a4c"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: "architecture-review"
source_session: "qwenwork-mt2bpcc8atdjwnha"
turn_count: 4
---

# Conversation Transcript

user: 对 CodeWiki-CN 跑 improve-codebase-architecture skill
assistant: 报告 6 候选（%TEMP%/architecture-review-*.html）：①frontmatter+layout deep module（Strong，top rec——3 个 writer 8 个 reader 散落，_unquote_fm 类补丁是症状）②WikiStore 写入 seam（12 处索引刷新仪式）③拆 registry.py（2403 行三模块+enum drift——type_filter 漏 scenario 的 live bug 是症状）④SearchIndex seam（wiki_search 三重级联+第二份 BM25，cache.py 34 公开方法）⑤WorkspaceResolver（13 份 output_dir 拷贝）⑥handler 返回结构化结果。
user: Explore candidate 1
assistant: grilling 定稿四个决策：Q1 布局路由（PAGE_TYPE_DIRS）收进 module（查表成本零，算路径与拼 frontmatter 从来连着发生）；Q2 原地扩展 frontmatter.py 而非新建 wiki_layout.py（避免第二真源）；Q3 序列化保持字节级兼容（reader 接受所有旧 parser 的并集，round-trip 不变量 parse(render(x))==x 写成测试锁死）；Q4 先 reader 后 writer 两步各自成提交（reader 纯收敛零行为风险，先消灭引号补丁）。
