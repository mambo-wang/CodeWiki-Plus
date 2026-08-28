---
type: architecture
title: TencentDB-Agent-Memory 四层记忆金字塔：逐层蒸馏 + 触发式调度
tags:
- architecture
- codewiki
- memorycore
- personatrigger
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-12 11:58:57+00:00
stale_after: 2026-11-10
metadata:
  date: '2026-08-12'
  origin: conversation
  related_components: []
  related_modules:
  - '""'
  source_ref: raw\conv-system_reminder-请注意，当你在遇到无法解决的问题时，往往会出现重复行为，导致陷入循环——例如重复输出相同-8.md
  consolidated_into:
  - wiki/scenarios/对话蒸馏管线与raw暂存区.md
reject_reason: 聚合进场景：对话蒸馏管线与raw暂存区
---

## 背景

源码级调研 d:\repos\TencentDB-Agent-Memory\MemoryCore\src，理解四层记忆提取机制，为 CodeWiki 知识飞轮借鉴。

## 架构事实

| 层级 | 模块 | 产出物 | 触发 | LLM |
|---|---|---|---|---|
| L0 原始对话 | conversation/l0-recorder.ts + hooks/auto-capture.ts | JSONL + 向量索引 | agent_end 同步 | 无 |
| L1 原子记忆 | record/l1-extractor.ts | memory_*.json | 调度器批处理 | 单次调用 |
| L2 场景 | scene/scene-extractor.ts | scene 文件 + 索引 | 向下计时器 | 有 |
| L3 人格 | persona/persona-generator.ts | profile（版本化） | PersonaTrigger | 有 |

关键机制：
1. L0 零 LLM：performAutoCapture 原子 checkpoint 采集（文件锁防并发 agent_end），双路径向量索引（sqlite 异步 embed vs VDB 同步），notifyConversation 传空数组让 runner 自读 DB。
2. 宽松/严格双门控：shouldCaptureL0（只滤结构噪声）vs shouldExtractL1（L0 超集 + 长度/符号/注入过滤），门控都在 LLM 调用之前。
3. 三路径触发 + warmup：阈值计数（新会话 1→2→4→8 指数递增）/ idle 超时 / shutdown flush。
4. Over-fetch 积压自排空：L1 取 2N 行只处理 N 行，hasMore 挂 idle 定时器，hasFullBacklog 立即再入队。
5. L1 单次 LLM 两件事：切场景 + 提三类记忆（persona 80-100/50-70、episodic 80-100/60-70、instruction -1/90-100/70-80），原则宁缺毋滥、独立完整、归纳合并。
6. 批次去重：embedding 召回 topK 冲突候选 → LLM 判定 store/update/merge/skip，失败兜底全量写入。
7. L2 向下计时器：只提前不推迟，受 min/max interval 约束。
8. L3 版本化触发：contentMd5 变更检测 + triggerEveryN，内容没变不重新生成。

## 对 CodeWiki 的借鉴

1. L0/L1 分离 + 宽松/严格双门控，避免噪声灌进蒸馏；
2. 游标 + 原子 checkpoint 续跑，增强 repowiki/raw/ 可靠性；
3. contentMd5 变更检测做增量蒸馏判断；
4. 单次 LLM 调用多任务，减少往返。

## 相关文档

- [对话蒸馏管线与 raw 暂存区](../wiki/scenarios/对话蒸馏管线与raw暂存区.md)
