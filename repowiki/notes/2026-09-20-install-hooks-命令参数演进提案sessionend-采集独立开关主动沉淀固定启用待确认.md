---
type: decision
title: install-hooks 参数重构定案并实施（ADR-0014）：--capture 独立开关、主动沉淀固定启用、--mode 删除
tags:
- decision
- install-hooks
- capture
- ADR-0014
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 产品维护
  source_session: 7c6e728aee994ae8ac04574de53d3cfd
  related_modules:
  - cli
  - mcp
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me-37c9c2.md
  scene: 产品维护/接线档位
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 06:59:00+00:00
stale_after: '2027-09-23'
origin: conversation
verified:
- by: codewiki/5.13.0
  at: '2026-09-23T07:28:51Z'
---

## Background

2026-09-20 会话中用户对 `codewiki/启用/禁用任务管理（跨会话任务记忆）` 命令提出参数演进需求：SessionEnd 采集 hook 独立开关、去掉 `--active-settle` 改为固定启用主动沉淀，目标是「主动沉淀效果好就不用采集对话和补蒸馏」。经 grilling 三轮共 13 问定案，随后在同会话内完整实施并通过全量测试（1126 通过、0 失败，lint 零错误）。

## 决策（ADR-0014，已实施）

- CLI 新增 `--capture on|off`（默认 on，per-run 全局、不持久化）：off 时移除 SessionEnd（trae 为 Stop）采集注册，SessionStart/UserPromptSubmit/脚本/distill-worker 全保留；重跑接线默认恢复 on，summary 显式报告当前 capture 状态
- `--active-settle` 删除：主动沉淀固定启用，传入即退出码 1 硬报错并提示改用 `--capture`；`hooks.yaml` 删 `active_settle` 字段、`active_settle_of()` 退役、`upsert_active_settle_protocol` 恒渲染协议块（off 分支与混合档位保护逻辑删除）
- `--mode`/`--clean` 删除：档位恒由 `hooks.yaml` 注册表自动判定（qwenwork→prompt 档，codebuddy/qoder/claude-code/trae→hook 档，与原 `--mode auto` 零回归）；`clean_hook_artifacts()` 因唯一调用者消失而删除
- 工具层：`capture_conversation`/`store.capture_raw`/registry schema 删 `active_settle` 参数与 frontmatter 键；`distill_conversation` 所有路径无条件 notes-only（`memories_skipped_reason="channel_exclusive"`）
- 协议块 ②「收尾轮保险采集」整节删除，判据 4 改为收尾轮沉淀自查；qwenwork 宿主小节同步
- `--status`：`active_settle` 列→`capture` 列；wired-on-disk 新增专用值 `hooks(仅SS)+settings(capture off)`，与「接线不完整」的 partial 显式区分
- 文档：ADR-0008 标 superseded、新增 ADR-0014、`docs/接线档位选择设计方案.md` 升 v3（两轴正交模型改写为「写侧固定 on + capture 开关」）、README 与 `docs/team-memory-hook.md` 同步

## Rationale

主动沉淀升为唯一记忆写入通道（固定启用），采集→蒸馏链路降为可关备胎；「字段还在但没人能改」的僵尸配置违反单点收敛；旧参数语义已不存在，静默忽略会让用户误以为关掉了（不静默降级）。

## 已接受代价

存量 4 条积压 raw 补蒸馏只产笔记、记忆内容不落任务记忆（用户显式选择 Q9b，放弃折中方案 c）；共享仓库「hook 宿主切 prompt 档不留脚本」场景失去 CLI 入口（YAGNI，真出现痛点再加回是一行参数的事）。

## 演进留痕

本笔记由同主题「提案待确认」草稿原地更新而来：该提案已定案并实施完毕，旧草稿的「尚未定论」状态作废。相关代码：`codewiki/cli/commands/install_hooks.py`、`codewiki/cli/utils/ide_config.py`、`codewiki/hooks.yaml`、`codewiki/mcp/prompts.py`；决策记录：`docs/adr/0014-distill-notes-only-channel-exclusivity.md`（取代 `docs/adr/0008-active-settle-deterministic-dedup.md`）。
