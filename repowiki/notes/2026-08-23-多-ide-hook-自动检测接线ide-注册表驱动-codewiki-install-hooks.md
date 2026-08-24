---
type: decision
title: 多 IDE hook 自动检测接线：IDE 注册表驱动 + codewiki install-hooks
tags:
- codebuddy
- codewiki
- decision
- powershell
aliases:
- 多智能体接线
- install-hooks
- IDE 注册表
- 自动检测 hook
metadata:
  date: 2026-08-23
  task_id: 产品维护
  related_modules:
  - CLI
  - MCP_Prompts
  related_components:
  - codewiki/cli/utils/ide_config.py
  - codewiki/cli/commands/install_hooks.py
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.3.0
  at: 2026-08-23 12:29:40+00:00
stale_after: '2027-08-23'
verified:
- by: codewiki/5.3.0
  at: '2026-08-23T12:44:51Z'
reject_reason: 聚合进场景：IDE-Hook采集链路方法
---

## 背景

CodeWiki 的任务记忆 hook/subagent 接线原本仅支持 CodeBuddy（`.codebuddy/settings.json` + 手动 PowerShell 拷贝）。用户要求扩展为支持市面上常见智能体（Qoder、Claude Code），且「用户触发创建 hook 时自动检测智能体类型，有哪些智能体就创建对应 hook」。

## 决策

1. **IDE 注册表驱动**：新增 `codewiki/cli/utils/ide_config.py`，`IDE_SPECS` 字典定义每个 IDE 的配置目录（`.codebuddy`/`.qoder`/`.claude`）、settings.json 文件名、agents 子目录、是否拷贝 distill-worker。新增一个 IDE 只需加一行数据。
2. **`codewiki install-hooks` CLI 命令默认自动检测**：无参运行时扫描项目根目录存在的 `.codebuddy/.qoder/.claude`，检测到哪些就为哪些接线（无需用户指定 IDE）；`--ide <name>` 跳过检测仅接线指定 IDE；`--repo-path` 指定目标项目。
3. **接线内容**：强制拷贝 hook 脚本（capture_session_end.py + task_session_start.py）与 distill-worker.md 到对应 IDE 目录；幂等合并 settings.json 的 SessionStart/SessionEnd 注册（按 command 去重、保留无关配置、原子写回）；AGENTS.md 任务记忆引导段 upsert（多 IDE 共享一份，只动 TEAM-MEMORY-TASK 标记块）。
4. **prompt 首选 CLI**：team-memory-hook 与 init-wiki 的启用步骤首选运行 `codewiki install-hooks` 自动检测接线；CLI 不可用时回退到手动步骤，补充 Qoder/Claude Code 的 settings.json 路径差异说明。
5. **hook 脚本本体无需改动**：`_ide_hook.py` 已做 CodeBuddy/Claude-Code 通用载荷解析（transcript_path 内联 turns 兜底、CLAUDE_PROJECT_DIR 回退），接线层只需生成对应 IDE 的 settings.json。

## 根因

三个 IDE 的 hooks 事件格式一致（SessionStart matcher=startup、SessionEnd matcher=other），仅配置目录不同；自动检测路径契合「用户用了哪些智能体就为哪些接线」的产品心智。

## 适用范围

- 新增 IDE 支持：在 IDE_SPECS 加一行 + 确认 hooks 事件格式即可
- 不含 Cursor/Windsurf/Trae（无 hooks 机制）

## 相关文档

- [CLI 命令](../wiki/modules/CLI_Commands.md)
- [MCP Prompts](../wiki/modules/MCP_Prompts.md)
