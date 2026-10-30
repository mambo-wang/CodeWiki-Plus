---
type: decision
title: "移除 caw 订阅模式后端：产品不考虑 claude-code/codex 订阅模式，Windows fcntl 环境性失败随之消失"
tags: ["codewiki", "decision"]
metadata:
  date: 2026-10-30
  confidence_level: weak
  task_id: 发版本
  source_session: "5dee23d20a5649afa4429fdc1594bc07"
  related_modules: ["codewiki/src/be", "codewiki/cli"]
  severity: high
  source_ref: "conversations/conv-@command-windows-python-release-发布版本5.16.3.md"
  scene: "产品维护"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.5, at: 2026-10-30T03:33:09Z }
stale_after: 2027-10-30
origin: conversation

---

## Background

caw（coding-agent-wrapper，`pyproject.toml` 曾有 `coding-agent-wrapper` 依赖）是封装官方 Claude Code / Codex CLI 的 Python 库，CodeWiki 用它实现订阅模式后端：`provider=claude-code/codex` 时 fork CLI 子进程、把读代码/写文档/Mermaid 校验三个 agent 工具经 MCP 暴露给 CLI agent。caw 包依赖 POSIX-only 的 `fcntl` 模块，Windows 上导入即失败，导致 `test_caw_backend_runs_agent_despite_overview` 在 Windows 稳定失败（CI Linux 通过，属环境性失败非代码回归）。

## Decision

用户决策（2026-10-26）：工具不考虑订阅模式，整体移除 caw 相关代码与依赖。落地为 commit `2d2e1e0 refactor: remove caw subscription-mode backend (claude-code/codex CLI providers)`（18 文件，+194/-919）。

- 删除：`codewiki/src/be/caw_backend.py`（325 行）、`codewiki/src/be/caw_toolkit.py`（约 300 行）、`coding-agent-wrapper` 依赖（uv.lock -41 行）
- 清理引用（7 文件）：`backend.py` 删 `CAW_PROVIDERS`/`is_caw_provider()`，`get_backend()` 收敛为单路径；`cli/models/config.py` 的 `validate()`/`is_complete()`、`cli/config_manager.py` 的 `set_config()`/`is_configured()`、`cli/commands/config.py` 的 provider 枚举与 show/check 展示均删订阅模式分支；`mcp/tools/legacy_tools.py` 删 caw_mode 豁免；`tests/test_generation_gaps.py` 删 caw 用例；`tests/test_latest_compat.py` 删 caw_toolkit 导入与 Windows skip 逻辑
- 文档口径同步：README.md 与 CodeWiki介绍.md 中「支持 Claude Code / Codex 订阅模式」表述删除或改为 API 模式口径

## Rationale

订阅模式虽是正式产品功能，但用户明确不再需要；移除后 Windows 全量 pytest 全绿（1359 passed / 2 skipped，不再有环境性失败），少一个依赖与 fcntl 平台限制，`get_backend()` 收敛为单路径。

## 注意

- `cli/utils/ide_config.py:81` 的 `"claude-code"` 是 IDE hook 注册表（install_hooks 目标 IDE），与订阅模式无关，保留正确
- `repowiki/wiki/modules/*.md` 中的订阅模式描述是知识库快照，随下次 `analyze_repo` 重生成自然更新，不手改
- 移除前评估过「只加平台 skip」的最小修复方案，被用户否决——功能下线是产品决策
