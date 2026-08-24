---
type: Conversation
title: "conversation 20260824T050116Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:16Z }
captured_at: "2026-08-24T05:01:16Z"
content_hash: "sha256:9c7949d7787a9875b9b9fb6466c7edb634dda66f102b8a7aa7aa75e37fac8b4b"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=1"
keep_raw: false
link_to: "wiki_lint fix=true 修复"
source_session: "qwenwork-mt6owymh1wkon9ze"
turn_count: 2
---

# Conversation Transcript

user: 修复 fix=true 后 broken_links 残留的问题
assistant: 根因：自愈逻辑在所有检查跑完之后才执行——broken_links 早已基于旧 index 计算完；更微妙的是 dedup 本会把这些同行号 broken_links 当 stale_refs 重复吞掉，但 fix 先清空 stale_refs 等于解除 dedup 武装，让旧 index 死链以 error 级暴露。修法：自愈块移到检查执行之前（fix=true 先预扫 stale_refs→符合条件先 rebuild_index→全部检查跑在重建后的索引上），后置 fix 块删除，代码反而更短。教训：修复顺序类 bug 时先看数据流时序（谁先算谁后改），而非只看逻辑正确性；测试断言要先验证'修复前症状可见'再验证'修复后归零'（本例 dedup 掩盖症状导致第一版测试断言不成立）。
