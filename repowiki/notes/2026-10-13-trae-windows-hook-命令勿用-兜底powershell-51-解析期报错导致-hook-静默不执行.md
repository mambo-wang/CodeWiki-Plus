---
type: pitfall
title: "Trae Windows hook 命令勿用 `||` 兜底——PowerShell 5.1 解析期报错导致 hook 静默不执行"
tags: ["pitfall", "powershell", "sessionstart"]
metadata:
  date: 2026-10-13
  confidence_level: weak
  task_id: Trae适配
  severity: high
  root_cause: "Trae Windows 用 PowerShell 5.1 执行 hook 命令，PS5.1 不支持 `||`（解析期错误整条命令不执行），且 Windows 通常无 python3；bash 风味的 `python3 ... || python ...` 兜底写法在该环境是死命令，失败被 IDE 静默吞掉。"
  reason: "调试根因已在本会话实证（PS5.1 解析错误复现 + 修复后逐事件仿真通过），按主动沉淀协议落草稿待确认"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.14.1, at: 2026-10-13T01:59:18Z }
stale_after: 2027-04-11
source_conversations: ['conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me-0e532c.md']

---

## 现象

Trae（Windows）项目级/全局 hook 配置了 `python3 xxx || python xxx` 形式的命令后从未触发：无 SessionStart 注入、无日志、无任何报错提示，表现为「不稳定/不生效」。

## 根因

Trae 在 Windows 上用 **PowerShell 执行 hook 命令**（官方文档：macOS/Linux 用 Bash，Windows 用 PowerShell）。Windows PowerShell 5.1 **不支持 `||`/`&&`**——且是**解析期错误**（`The token '||' is not a valid statement separator in this version`），整条命令直接不执行，不会进入任何一条分支。叠加 Windows 通常没有 `python3`（python.org 安装只给 `python`/`py`），`python3 ... || python ...` 这种 bash 风味兜底写法在 Trae Windows 上是死命令。非阻断性失败被 IDE 静默吞掉，所以表现为「毫无动静」。

## 结论/做法

- Trae Windows 的 hook command 必须是 **PowerShell 5.1 兼容语法**：直接写 `python ".trae/hooks/xxx.py"`（或 `py ...`）；不要用 `||`/`&&` 做解释器兜底。
- 没有同时兼容 PowerShell 5.1 与 Bash 的单行兜底语法；跨平台仓库要么按平台各配一份，要么统一用 `python`（macOS/Linux 需保证 `python` 可用）。
- 排查同类「hook 没反应」问题的固定动作：①把 command 原样拷到本机 PowerShell 跑一遍看是否解析错误；②模拟事件 JSON 管道给脚本验证 stdin/stdout；③IDE 侧 设置 > Hooks > 运行日志 看 Agent Hooks 日志。

实证：2026-10-13 CodeWiki-Plus 仓库 .trae/hooks.json 三条 hook（SessionStart/Stop/UserPromptSubmit）因同一原因全部从未执行，改为 `python ...` 后模拟 Trae 事件验证通过。

## CLI install-hooks 已按平台生成 Trae Windows 兼容命令（纯 python、无 || 兜底），修正对 2026-10-13 Trae 踩坑笔记的适用范围

> 合并自蒸馏候选：CLI install-hooks 已按平台生成 Trae Windows 兼容命令（纯 python、无 || 兜底），修正对 2026-10-13 Trae 踩坑笔记的适用范围

## Background

踩坑笔记 `notes/2026-10-13-trae-windows-hook-命令勿用-兜底powershell-51-解析期报错导致-hook-静默不执行.md` 记录了 Trae Windows 下 hook command 用 `python3 ... || python ...` 兜底形式会因 PowerShell 5.1 不支持 `||` 而解析期报错、整条静默不执行。

## 本次实证（2026-10-13）

同日重跑 `codewiki install-hooks`（venv 模块入口）后核对 `.trae/hooks.json`：CLI 生成的三条命令（SessionStart/Stop/UserPromptSubmit）均已是纯 `python ".trae/hooks/..."` 形式，无 `||` 兜底——**CLI 已按平台适配 Trae 命令，不再产出死命令**。该结论与上述踩坑笔记的修复建议一致，但补充了新事实：这不是需要手工修正的遗留问题，而是 CLI 已内置的平台适配行为。

对比：`.codebuddy/settings.json` 保留 `python3 ... || python ...` 双解释器形式在 CodeBuddy 宿主下实测可用（本会话 SessionStart 注入正常工作），无需按 Trae 的结论反向修改。

## Rationale

避免后续会话看到 `.codebuddy` 与 `.trae` 的 command 形式不一致时误判为接线错误去「统一修正」——两个宿主的 shell 语义不同，形式差异是刻意的。

## 结论

- Trae Windows：纯 `python` 命令是 CLI 正确产出，勿手工加回 `||` 兜底；
- CodeBuddy：`||` 双解释器形式实测可用，保持原样。
