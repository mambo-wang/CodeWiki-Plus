---
type: task
task_id: 统一知识存储层（KnowledgeStore-动词式门面）
title: 统一知识存储层（KnowledgeStore 动词式门面）
status: active
created_at: 2026-08-30T23:51:07.260584+00:00
---

按 docs/plans/knowledge-store-rfc.md 实施：src/frontmatter.py 补解析侧 + 新建 KnowledgeStore 动词式门面 + store_for 桥，逐步迁移 capture/distill → task_manager → knowledge_loop → 其余工具，消灭 13+ 份重复存储管道代码。
