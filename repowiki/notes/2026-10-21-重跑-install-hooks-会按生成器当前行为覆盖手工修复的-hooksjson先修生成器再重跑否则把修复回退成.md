---
type: pitfall
title: 重跑 install-hooks 会按生成器当前行为覆盖手工修复的 hooks.json：先修生成器再重跑，否则把修复回退成 HEAD 的坏形态
tags:
- pitfall
- powershell
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: 60447e73-2fba-49e3-b153-c1d74cf16fae
  related_modules:
  - cli
  - hooks
  severity: medium
  source_ref: conversations/conv-codewiki启用任务管理.md
  scene: 多 IDE hook 接线维护（install-hooks 重跑）
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:08:18+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:21Z'
---

## 背景

「启用任务管理」流程中重跑 `codewiki install-hooks` 时，把 `.trae/hooks.json` 里已手工修好的单解释器命令覆盖回 HEAD 的 `python3 … || python …` 双解释器形态——TRAE Windows 走 PowerShell 5.1，`||` 是解析期错误、三个 hook 静默全灭（既有笔记 `notes/2026-10-13-trae-windows-hook-命令勿用-兜底powershell-51-解析期报错导致-hook-静默不执行.md`）。

## Pitfall

install-hooks 对 hooks.json 是「生成器即事实口径」的全量重写：它不感知工作区里对 hooks.json 的手工修复，重跑一律按**当前生成器代码**重写目标文件。若生成器修复（如 `ide_config.py` 的 `_trae_hook_commands`）还在工作区未生效/未提交，重跑会把手工修复回退成生成器的旧坏形态——且恰好等于 HEAD 时 git diff 为空，**回归不可见**。注意与 AGENTS.md 标记块的内容感知 upsert（`notes/2026-09-26-agentsmd-标记块是内容感知-upsert内容一致零写盘no-change块被改坏或模板升级时自动恢复update.md`）区分：那是 upsert 语义，hooks.json 是全量重写语义。

## 正确做法

- 重跑 install-hooks 前先确认生成器（`codewiki/cli/utils/ide_config.py`）已是修复后的版本；修复在源码里就位后，重跑反而是让修复生效的手段。
- 重跑后必须逐文件核对生成产物（git diff + 直接读文件），不能只看 CLI 输出的 `[updated]`/`[no-change]`。
- 判定「手工修复被回退」的技巧：`git show HEAD:<file>` 对比——产物等于 HEAD 而工作区此前有未提交修复，即发生回退。

## 附带事实

- 三端 hook 脚本（task_session_start.py / capture_session_end.py）与 `codewiki/hooks/` 源码四份 md5 应完全一致；不一致即版本漂移，重跑 install-hooks 对齐。
- SessionEnd 采集落盘在 `repowiki/raw/conv-*.md`（fire-and-forget，wrapper 立即返回，子进程稍后落盘——验证时 ls 太早会误判失败）；TRAE Stop 无 transcript_path、不落盘属预期降级。
