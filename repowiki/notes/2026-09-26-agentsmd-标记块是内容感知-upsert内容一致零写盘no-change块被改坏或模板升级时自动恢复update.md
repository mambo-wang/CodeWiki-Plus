---
type: architecture
title: AGENTS.md 标记块是内容感知 upsert：内容一致零写盘（[no-change]），块被改坏或模板升级时自动恢复（[updated]）
tags:
- architecture
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 184920b147de4d1f9e2ce9a39d25a453
  related_modules:
  - CLI_Utils
  - MCP_Tools_Workspace
  severity: high
  source_ref: conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-2.md
  scene: AGENTS.md 管理块
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:26:30+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:21Z'
---

## Background
用户实测重复执行初始化/启用任务管理时 AGENTS.md 没变化，质疑 upsert 是否真的在工作。经代码核对与破坏性实测确认行为：

## 机制（`codewiki/cli/utils/ide_config.py` `_upsert_marker_block`）
- 所有写入路径（CLI install-hooks、init_wiki、init_workspace、prompt 引导手动写入）走同一套标记块 upsert：只切 `[start_idx, end_idx+len(end))` 区间重组文本（`ide_config.py:506-523`）。
- 块内整体替换为**当前版本模板**；块外内容（用户自有段落）绝不触碰。
- **内容一致时零写盘**：`new_text == text` 返回 False，CLI 打印 `[no-change] AGENTS.md task-memory section present`（`ide_config.py:520-521`、`install_hooks.py:83`）。
- 模板变了（版本升级）或块被手工改坏 → 区间内恢复/刷新为最新模板，打印 `[updated]`。

## 实测验证（2026-09-21）
破坏 `TEAM-MEMORY-TASK` 块内一行（保留 START/END）→ 重跑 install-hooks → `[updated]` 恢复模板原文，git hash 与测试前完全一致。

## 陷阱
1. **多个 `[no-change]` 容易误以为「没做事」**：AGENTS.md 是多 IDE 共享一份，第一个 IDE 处理时完成 upsert，后续 IDE 都显示 `[no-change]`——实际第一个已做完。
2. 残缺块（只有 START 无 END 或顺序颠倒）被当作「不存在」，追加新块到末尾——极端情况（手工编辑破坏标记）会残留旧块。

## Rationale
理解「工具维护区」语义：重复初始化是安全的，块内刷新为最新模板（协议升级自动同步），无变化零写盘避免 mtime 抖动和 git 假变更；用户自定义必须写在标记块外。
