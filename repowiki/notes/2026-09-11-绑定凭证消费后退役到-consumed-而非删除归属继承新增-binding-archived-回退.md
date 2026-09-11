---
type: decision
title: 绑定凭证消费后退役到 consumed/ 而非删除，归属继承新增 binding-archived 回退
tags:
- decision
aliases:
- binding archived
- binding-archived
- 归属丢失
- task_bindings consumed
metadata:
  date: 2026-09-11
  related_modules:
  - store
  - task-bindings
  - capture-conversation
  - distill-conversation
  source_ref: docs/adr/0006-session-binding-attribution-tombstone.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-11 02:48:35+00:00
stale_after: '2027-09-11'
verified:
- by: human:wangbao
  at: '2026-09-11T02:49:24Z'
---

## Background

2026-08-24 的结论是「绑定文件改为一次性消费凭证，成功落盘后**删除**，supersede 继承旧 task_id，归属不丢」。

2026-09-11 实测发现这个保证有缺口，且缺口无法靠原机制修补：supersede 继承的继承源是 `raw/.index.json` 里 `status=pending` 的条目，而**蒸馏会删除 raw 文件并摘掉索引条目**。一旦会话的首条 raw 已被蒸馏，继承源消失，绑定凭证又早已被消费销毁——两头皆空，后续捕获的 `task_id` 变成空字符串。本仓 `repowiki/raw/conv-manually_attached_skills-*.md` 就是这样丢归属的（frontmatter 无 task_id，绑定文件已被删除）。

## Decision

1. **消费动作从「删除」改为「退役」**：`capture_raw` 成功落盘后，绑定文件从 `task_bindings/<sid>.json` 移入 `task_bindings/consumed/<sid>.json`（`KnowledgeStore.archive_binding`）。凭证语义不变——`read_binding` 对已退役凭证仍返回空，一次性语义完整保留。
2. **新增兜底回退**：`capture_raw` 在 supersede 未继承到 task_id 时，回退读退役凭证，`task_source=binding-archived`。
3. **GC 一并清扫**：`gc_bindings` 同时扫 `consumed/`，按 `bound_at` 30 天清理，墓碑不会无限堆积。
4. 目录常量 `CONSUMED_BINDINGS_DIR`（`codewiki/src/config.py`）；gitignore 已按目录覆盖 `.meta/task_bindings/`，无需改动。

## Why

- **不动一次性凭证语义**：删除改为退役，是为了让「凭证失效」与「归属保留」解耦。凭证失效由 `read_binding` 返回空保证，归属保留由墓碑保证，两者不再互相牺牲。
- **不新增状态目录**：墓碑放在 `task_bindings/` 子目录，复用既有 gitignore 与 gc 通道，避免第二套生命周期管理（Doctrine：单点收敛）。
- **不依赖下游幂等**：兜底回退是显式的第三级（binding → binding-inherited → binding-archived），不是靠重试碰运气。

## Evidence

受控实验（`KnowledgeStore` + 临时 root）：

- 修复前：`CAP1 task_id='task-A' source='binding'` → 蒸馏移除首条 raw → `CAP2 task_id='' source=''`（丢失）
- 修复后：`CAP2 kind=captured task_id='task-A' source='binding-archived'`
- 回归测试 `tests/test_knowledge_store.py::test_attribution_survives_distilled_raw_via_archived_binding`
- 全量 `pytest` 933 passed, 2 skipped

前置证伪：先跑过 4 场景实验（绑定在/不在 × 首次/重捕），`binding → task_id` 主链路全部正确，因此排除「落盘时漏写 task_id」的假设，避免改错地方。

## Scope / 适用

任何「会话级一次性凭证 + 事后继承」的设计：凭证销毁与归属保留必须分开，否则「凭证已消费」与「继承源已消失」同时发生时必然丢归属。

## 取代关系

取代 `notes/2026-08-24-task-bindings-绑定文件改为一次性消费凭证成功落盘后删除-supersede-继承旧-task-id.md`。该笔记的凭证机制保留，但「归属不丢」这一保证被修正为「仅在继承源存在时成立」。
