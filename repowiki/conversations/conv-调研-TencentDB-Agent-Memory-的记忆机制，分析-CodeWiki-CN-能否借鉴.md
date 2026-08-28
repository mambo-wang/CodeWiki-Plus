---
type: Conversation
title: "conversation 20260824T050115Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:15Z }
captured_at: "2026-08-24T05:01:15Z"
content_hash: "sha256:d17185cc2c7412ad13c6c6ddbaae75c843ca9c2d3c85ee06469acd221dcf74ea"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: "团队记忆融合-L2场景聚合与L3-Doctrine设计方案"
source_session: "qwenwork-msvrbmt5zvkq5t6g"
turn_count: 4
---

# Conversation Transcript

user: 调研 TencentDB-Agent-Memory 的记忆机制，分析 CodeWiki-CN 能否借鉴
assistant: 完成 TAM（D:\repos，feat/server_team 分支）L0-L3 记忆管线深度分析：L0 录制器+hooks 采集、L1 原子记忆提取（调度器批处理）、L2 场景聚合（SceneExtractor）、L3 人格生成（PersonaTrigger）。评估结论：CodeWiki 已借鉴一半——_should_capture_l0/_should_extract_l1 门控已对齐 TAM，L0（capture_conversation→raw/）L1（distill_conversation→notes/）已有，空白在 L2 只有 lint 信号无聚合实体、L3 完全缺失。
user: 写设计文档到 docs/
assistant: docs/团队记忆融合-L2场景聚合与L3-Doctrine设计方案.md：新增 consolidate_notes（confirmed 笔记聚合为 ≤15 个 wiki/scenarios/ 场景块，UPDATE>MERGE>CREATE 容量分级）与 refresh_doctrine（压缩 ≤1200 字 doctrine.md 项目操作原则）两个 Mode C 工具。关键适配决策：触发用计数器信号替代 TAM 定时器级联（wiki_stats/get_task_context 露出）；去重召回用现有 BM25 替代向量、判定交宿主 agent（两段式 submit+四操作）；产物沿用 OKF 三态评审闸门。三阶段路线图 P1 蒸馏增强/P2 场景聚合/P3 Doctrine。与 team-memory-fusion-feasibility.md 形成链路。
