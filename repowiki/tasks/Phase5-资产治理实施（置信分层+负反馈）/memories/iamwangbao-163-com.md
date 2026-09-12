### 2026-09-12 08:26

### 2026-09-12

HL-Mem 调研（docs/HL-Mem-调研与借鉴分析.md）对 Phase5 的三条设计输入（2026-09-12 拷问定稿）：

1. **T7 与 C8 的关系修正**：报告初稿曾把「双时间」整体 excluded，但 T7 本来就计划引入 valid_from/valid_to/last_verified_at——不矛盾，排除的只是完整四字段双时间与 recorded_* 轴；T7 按原计划做。
2. **负反馈延寿公式定稿（T5/T6 落地后的顺手项）**：移植 HL-Mem BayesianUsefulnessPolicy 纯函数（domain/feedback.py:36-37）：bonus = floor(正证据/3) × 14 天，cap 180；延长 stale_after 时被该笔记类型新鲜度上限夹住（对齐 HL-Mem valid_to 夹紧 workers/ttl.py:39-43 + service_health 槽位二次夹紧 :44-46）。默认 observe：先只记录「本应延长多少天」不改实际值。
3. **保留冷启动守卫**：_check_low_adoption 零 adopted 事件静默返回（wiki_lint.py:1271-1277）的纪律不得破坏。

三态词汇统一用 tri-state gate（CONTEXT.md glossary 已落）。排期提醒：「冲突一等对象」任务（ADR-0007）与本任务批次二动同一片 note_lifecycle/note_query 区域，须错开。
