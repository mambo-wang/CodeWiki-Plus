---
type: Conversation
title: "conversation 20260819T014113Z"
status: distilled
stale_after: 2026-11-17
generated: { by: codewiki/5.3.0, at: 2026-08-19T01:41:13Z }
captured_at: "2026-08-19T01:41:13Z"
content_hash: "sha256:68c5e854d34d67a0dd33fdd4d86728dd645e9e30d1dbecf35823d585f0450f57"
keep_raw: false
link_to: "团队记忆融合-L2场景聚合与L3-Doctrine设计方案"
source_session: ""
turn_count: 2
---

# Conversation Transcript

user: 蒸馏后的 raw 对话被删除，笔记 source_ref 全部失效，L0 留档有什么用？保存到哪？会不会拖慢检索？不建索引、靠链接按需查找可行吗？
assistant: 验证发现 48/48 条笔记的 source_ref 指向已删除的 raw，溯源链整体断裂。建议留档到独立的 repowiki/conversations/ 目录：蒸馏成功即搬家，笔记 source_ref 改指归档路径；不建 BM25 索引（链接优先、零索引），检索结果露出 source_ref 供 agent 按需 view_repo_file 下钻；drop_raw 作为隐私显式删除通道。基准测试证明：查询耗时不受影响，重建成本可用增量索引规避，归档放独立目录还保护了采集路径的扫描性能。
