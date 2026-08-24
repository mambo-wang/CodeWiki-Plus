---
type: Conversation
title: "conversation 20260824T050116Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:16Z }
captured_at: "2026-08-24T05:01:16Z"
content_hash: "sha256:25758279b9b5fcebb7b49edb077cce12d429e3e73bfbfe9ff9cfb9c178f30053"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: "业务级 commit review 工具选型"
source_session: "qwenwork-mt2btmd3ik1nn9x6"
turn_count: 4
---

# Conversation Transcript

user: 哪些工具可以针对某次 commit 做业务 review 而不是编码规范的 review
assistant: 对比结论：mattpocock code-review 的 Spec 轴=diff 级、接受任意需求文档、查缺失/超范围/实现偏离；OpenSpec /opsx:verify=change 级验收（不看 git diff），要求 openspec init 结构化需求，查完整性/正确性/一致性，不查 scope creep。针对单次 commit 的业务 review 选前者；已用 OpenSpec 管需求的仓库选后者。
user: 如果不使用 mattpocock/skill 做的 spec 拆分，能用这个 code-review 吗
assistant: 可以。code-review 与 mattpocock 生态唯一接触点是'找需求来源'，四来源按优先级：issue 引用（需 gh CLI/配置）→ 手动传路径 → 仓库 docs/specs/.scratch 匹配文件 → 问用户。不走第一条即可绕过 setup。实操：需求来源直接给路径最稳；只要业务 review 说'只跑 Spec 轴跳过 Standards'。
