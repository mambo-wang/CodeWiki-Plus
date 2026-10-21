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
source_conversations: ['conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me-0e532c.md', 'conversations/conv-codewiki启用任务管理.md']

---

## 背景

全局 `codewiki.exe`（Python314/Scripts）报 `ModuleNotFoundError: No module named 'codewiki'`（exit=1）。早期笔记曾把绕法归因为「需走 `-m codewiki.cli.main`」，2026-10-13 实证核对推翻了该归因。

## 根因（2026-10-13 实证）

- `site-packages/__editable___codewiki_1_0_1_finder.py` 的 MAPPING 指向 `D:\repos\CodeWiki-CN\codewiki`，而该仓库已更名为 CodeWiki-Plus、目录不存在 → 死链。
- 残留发行名是 `codewiki 1.0.1`，本仓 pyproject 发行名是 `codewiki-plus`——**不同名，`pip install -e .` 不会自动顶掉旧安装**，必须先显式 uninstall。
- 「`-m codewiki.cli.main` 能跑」是 cwd 遮蔽假象：`codewiki/__main__.py:5` 就是 `from codewiki.cli.main import cli`，两者等价；在仓根跑 `-m` 时 cwd 进 sys.path 才偶然成功，离开仓根同样失败。**起决定作用的是解释器环境/cwd，不是模块路径。**

## 控范围修复（已验证）

1. 前置核查：用 `importlib.util.find_spec` 遍历 pyproject 全部运行时依赖，确认全局环境已齐 → `--no-deps` 安全（若缺依赖，`--no-deps` 只会把 ModuleNotFoundError 换成 ImportError，应停下改议方案）。
2. `python -m pip uninstall -y codewiki`（清掉 .pth/finder/dist-info）。
3. 仓根 `python -m pip install -e . --no-deps` → `codewiki-plus → D:/repos/CodeWiki-Plus`。
4. 中性 cwd 验证：`codewiki --version`、`codewiki --help`（全子命令导入冒烟）、`codewiki install-hooks --status`。
5. `pip check` 审计副作用：本次未动依赖树，报出的冲突（markitdown-mcp/xai-sdk）判定为预先存在。

## 修复前的回退（历史口径，仍有效）

项目内有 `.venv` 时，用 venv 的模块入口或 console script 均可：`.venv\Scripts\codewiki.exe <cmd>` 或 `.venv\Scripts\python.exe -m codewiki <cmd>`（与 `-m codewiki.cli.main` 等价）。MCP 条目应指向 venv 绝对路径。

## Rationale

仓库文档与 agent prompt（wiki-recall.md、docs/team-memory-hook.md 等）普遍直接敲裸 `codewiki` 命令，全局 CLI 坏掉时每个照文档执行的 agent 都会撞墙并重复排查。死链根因、发行名不同名不互顶、cwd 遮蔽迷惑性、--no-deps 前置依赖核查，四点组合成完整排障路径。
