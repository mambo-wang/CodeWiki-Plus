# 00 — START HERE: 对话→Wiki 提取链 开工顺序

本目录是 `team-memory-fusion` 计划的规范化工单（本地 markdown 追踪器，因环境无 `gh` CLI）。
按 **tracer-bullet** 顺序执行：先打通 T1→T2→T5 的端到端最小链路（含一条确认落地），
再加 T3 去重、T6 自动采集，最后补 T4 全链路测试。

## 开工顺序

| 阶段 | Ticket | 做什么 | 完成标志 |
|------|--------|--------|----------|
| 0 | [01](01-trigger-decision.md) | （已 resolved）确认 both 触发形态 | 无需动作，约束已写入 spec/T6 |
| 1 | [02](02-capture-conversation.md) | 实现 `capture_conversation`：落 raw + 幂等 + `keep_raw` 透传 | raw 文件可写、可幂等、不进检索 |
| 2 | [03](03-distill-conversation.md) | 实现 `distill_conversation`（无状态、LLM 由调用方注入、草稿 draft、蒸馏后清 raw） | 给 raw 能产出 draft note，确认后进 notes/ |
| 3 | [05](05-retrieval-distinction.md) | `query_wiki` 暴露 `origin` 并可按来源过滤 | 确认的对话笔记可检索且带 origin |
| —— 此时已打通「采集→蒸馏→确认→检索」最小闭环 —— |
| 4 | [04](04-dedup.md) | 在蒸馏前对 notes/ 检索去重 | 重复蒸馏不再污染知识库 |
| 5 | [06](06-ide-hook.md) | 可选 IDE hook：监听事件自动调 capture_conversation（只落 raw） | 开启后对话结束自动落 raw，可开关、异步 |
| 6 | [07](07-tests.md) | 端到端集成测试 + golden-set 提取质量 | 全链路可独立跑、不依赖实时 LLM |

## 依赖图（blockers 在前）

```
01 (resolved)
02 ──┬──> 03 ──┬──> 04 (dedup)
     │         └──> 05 (retrieval)
     └──> 06 (ide hook)
02,03,04,05 ──> 07 (tests, 最后)
```

## 关键约束（实现前必读）

- `distill_conversation` 是**无状态**工具，不持有 LLM；LLM 由调用方注入（subagent 优先，或 BackgroundWorker 配 `MAIN_MODEL`/`LLM_BASE_URL`）。
- 蒸馏是 LLM 重活，**必须后台异步**，主线程不等待。
- 自动采集（T6）**只落 raw，不蒸馏**。
- `repowiki/raw/` 是暂存区、**不进 `query_wiki` 检索**；蒸馏完成后清理（除非 `keep_raw`），默认保留 7 天。
- 触发形态（T0）：**both**（手动命令主 + IDE hook 可选）。

## 关联文件

- Spec: `../SPEC-conversation-to-wiki.md`
- 决策地图: `../README.md`
- 可行性报告: `../../docs/team-memory-fusion-feasibility.md`
