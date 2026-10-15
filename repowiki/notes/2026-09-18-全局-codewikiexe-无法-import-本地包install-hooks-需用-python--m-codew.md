---
type: pitfall
title: 全局 codewiki.exe 无法 import 本地包：install-hooks 需用 python -m codewiki.cli.main
  从仓库根执行
tags:
- codewiki
- modulenotfounderror
- pitfall
metadata:
  date: 2026-09-18
  confidence_level: weak
  source_session: 7245f28d19714f71bca1abdd87568f23
  related_modules:
  - cli
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me.md
  scene: hook 接线 / CLI 使用
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-18 00:59:36+00:00
stale_after: '2027-03-17'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-18T01:46:12Z'
source_conversations:
- conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-560d5c.md
source_conversations: ['conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me-0e532c.md']

---

## 背景

在 CodeWiki 源码 checkout 内执行 `codewiki install-hooks --repo-path d:\repos\CodeWiki-Plus` 时，PATH 上的全局 `codewiki.exe` 报 `ModuleNotFoundError: No module named 'codewiki'`。

## 原因

console script 的 `sys.path` 不含当前工作目录，且 `codewiki` 包未 pip 安装到全局环境，全局 exe 找不到本地源码包。

## 正确做法

从仓库根目录改用等价模块入口执行（`codewiki/cli/main.py` 有 `__main__` 守卫）：

```powershell
python -m codewiki.cli.main install-hooks --repo-path d:\repos\CodeWiki-Plus
```

这样 `codewiki` 解析到本地源码，功能与 CLI 完全等价。

## 全局 codewiki CLI 因 Python 3.14 缺模块不可用，改用项目 .venv 内 CLI

> 合并自蒸馏候选：全局 codewiki CLI 因 Python 3.14 缺模块不可用，改用项目 .venv 内 CLI

## 补充：另一失败模式——全局 CLI 的 Python 3.14 缺模块（2026-09-21）

全局 `codewiki` CLI 还存在另一种不可用模式：其指向的 Python 解释器（3.14）缺少所需模块，CLI 入口直接报错。此时可改用项目虚拟环境中的 CLI：`d:\repos\CodeWiki-Plus\.venv\Scripts\codewiki.exe install-hooks --repo-path <repo>`。本项目开发会话中应优先使用 `.venv` 内的 codewiki CLI，而非全局安装版。

## 全局 codewiki CLI 损坏时的回退：用项目 venv 的 python -m codewiki.cli.main 模块入口执行 install-hooks

> 合并自蒸馏候选：全局 codewiki CLI 损坏时的回退：用项目 venv 的 python -m codewiki.cli.main 模块入口执行 install-hooks

## Background

在 `d:\repos\CodeWiki-Plus` 执行「启用任务管理采集 Hook」流程时，全局 `codewiki` CLI（Scripts 下的 `codewiki.exe`）启动即报 `ModuleNotFoundError`——全局 Python 3.14 环境缺模块，CLI 完全不可用。

## 正确做法

项目内有 `.venv` 时，改用 venv 内的模块入口执行同一子命令：

```powershell
d:\repos\CodeWiki-Plus\.venv\Scripts\python.exe -m codewiki.cli.main install-hooks --repo-path d:\repos\CodeWiki-Plus
```

本次实测成功完成三个智能体（codebuddy/qoder/trae）的全部接线（脚本强制覆盖拷贝、settings.json/hooks.json 幂等合并、AGENTS.md 任务记忆段 upsert）。

## Rationale

`codewiki install-hooks` 是启用/重接线采集 Hook 的首选路径，CLI 不可用时若直接跳到手动兜底步骤，容易凭记忆重写脚本而与包版本不一致；模块入口与 CLI 入口走同一套代码，是零成本的最短回退。

## Recovery

临时绕过不替代修复：全局 CLI 建议择机 `pip install --force-reinstall codewiki` 重装修复；修复前各仓库均可继续用 venv 模块入口。
