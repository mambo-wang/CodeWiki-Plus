---
type: Conversation
title: "conversation 20260824T050116Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:16Z }
captured_at: "2026-08-24T05:01:16Z"
content_hash: "sha256:7df0534c2cea5cbf47aa39e527eb45c2ad603b86bc130557c38f8f66ef43e155"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=1"
keep_raw: false
link_to: "repowiki-项目研究与借鉴分析"
source_session: "qwenwork-msyqo42hbupfpxef"
turn_count: 2
---

# Conversation Transcript

user: 调研 https://github.com/akitaonrails/ai-m 输出报告
assistant: 完成 ai-m 调研报告。期间回答了一个关键架构问题：为什么 retrieval_stats.db 放 repowiki/.meta/ 而不放 .codewiki/——①生命周期不同（热度是跨月累积的行为数据，.codewiki 缓存跟代码分析走、一 reset 就清零）②wiki 工具只认 output_dir 不该知道仓库根（放 .codewiki 每个消费点都要重复 _resolve_db_path 的脆弱启发式）③可移植性（repowiki 整目录可拷贝）④git 策略语义（.meta 默认共享逐个排除，单独 ignore 这一个文件本身就是'行为遥测私有'的设计声明）。
