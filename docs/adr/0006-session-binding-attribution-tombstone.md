# 0006. 会话绑定凭证退役而非销毁，归属继承三级回退

日期：2026-09-11
状态：已接受

## 背景

会话绑定（`repowiki/.meta/task_bindings/<source_session_id>.json`）是一次性凭证：
`set_session_task` 写入，`capture_conversation` 首次成功落盘后消费，用于把原始对话盖章到任务上，供 `distill_conversation` 路由记忆。

2026-08-24 的约定是「落盘后**删除**凭证，supersede 时从旧 raw 继承 `task_id`，归属不丢」。实测发现这个保证有缺口：`capture_raw` 的继承源是 `raw/.index.json` 里 `status=pending` 的条目，而**蒸馏会删除 raw 文件并摘掉索引条目**。一旦会话首条 raw 已被蒸馏，继承源消失，凭证又早已销毁，后续捕获的 `task_id` 变成空字符串——对话蒸馏后不会归到任务，只产出无归属笔记。

本仓 `repowiki/raw/conv-manually_attached_skills-*.md` 即为此症状：frontmatter 无 `task_id`，对应绑定文件已不存在，与「会话开始提示有积压、按 task 查为 0」的现象一致。

前置证伪：受控实验（绑定在/不在 × 首次/重捕 4 场景）确认 `binding → task_id` 主链路**全部正确**，排除「落盘时漏写字段」的假设。真凶是继承源消失。

## 决策

1. **消费动作由「删除」改为「退役」**：`capture_raw` 成功落盘后，凭证从 `task_bindings/<sid>.json` 移入 `task_bindings/consumed/<sid>.json`（`KnowledgeStore.archive_binding`）。`read_binding` 对已退役凭证仍返回空——**一次性语义完整保留**。
2. **归属继承三级回退**：
   - `binding`（读活跃凭证，读后退役）
   - `binding-inherited`（supersede 时从 pending 旧条目继承，原机制不变）
   - `binding-archived`（前两级皆空时读退役凭证，本次新增）
3. **GC 一并清扫**：`gc_bindings` 同时扫 `consumed/`，按 `bound_at` 30 天清理。
4. 目录常量 `CONSUMED_BINDINGS_DIR` 落在 `codewiki/src/config.py`；gitignore 已按目录覆盖 `.meta/task_bindings/`，无需改动。

## 理由

1. **凭证失效与归属保留必须解耦**：原设计让同一个文件同时承担「凭证」和「归属记录」两个职责，于是「销毁凭证」必然连带销毁归属。拆成活跃目录与 `consumed/` 后，两者不再互相牺牲。
2. **不新增第二套生命周期**：墓碑放在 `task_bindings/` 子目录，复用既有 gitignore 与 gc 通道（Doctrine：单点收敛，新逻辑先找收敛点）。
3. **不依赖下游幂等当安全网**：三级回退是显式的，每一级都有独立的 `task_source` 标记可观测，不是靠重试碰运气。
4. **不动既有测试的语义断言**：`read_binding` 消费后仍返回空、`consumed_binding` 标记仍为 `True`，因此 `test_knowledge_store`、`test_task_manager`、`test_phase2_concurrency` 中的既有断言无需修改即通过。

## 后果

- `repowiki/.meta/task_bindings/consumed/` 是新出现的目录，受同一条 gitignore 规则覆盖，不进版本库。
- 已丢失归属的历史 raw 无法追溯补盖（凭证是一次性的）；只能重建绑定，使**后续**捕获恢复归属。
- 结论层已同步：`repowiki/notes/2026-08-24-...一次性消费凭证成功落盘后删除...md` 标记 deprecated，由 `2026-09-11-绑定凭证消费后退役到 consumed/ 而非删除...md`（decision）与 `2026-09-11-会话归属丢失：绑定已消费 + 旧 raw 已被蒸馏...md`（pitfall）取代。

## 验证

- 复现脚本：修复前 `CAP2 task_id=''`；修复后 `CAP2 task_id='task-A' source='binding-archived'`
- 回归测试：`tests/test_knowledge_store.py::test_attribution_survives_distilled_raw_via_archived_binding`
- 全量 `pytest`：933 passed, 2 skipped
