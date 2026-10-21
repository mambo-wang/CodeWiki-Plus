---
type: lesson
title: Qoder 任务弹框 4 选项是宿主硬约束不可单框突破：优化走正文清单+「其他」输入，改 hook 源文件须同步 .qoder 副本
tags:
- askuserquestion
- codewiki
- lesson
metadata:
  date: 2026-10-21
  confidence_level: weak
  source_session: 5161496d-a7c1-42bd-bf06-c700791a8f29
  related_modules:
  - hooks
  severity: medium
  source_ref: conversations/conv-我发现qoder中会话开始拉取任务列表还是只展示4项，可以优化吗.md
  scene: Qoder适配：SessionStart 任务关联弹框
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:00:25+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:06Z'
---

## Background

用户希望 Qoder 会话开始的任务关联弹框一屏展示更多任务（6-8 项）。代码核对结论：做不到单框突破。限制点是 `codewiki/hooks/task_session_start.py:202` 的 `_QODER_OPTION_CAP = 4`，这不是 CodeWiki 自限，而是 Qoder `AskUserQuestion` 工具的硬约束（单题 options 硬区间 2-4，越界调用直接失败，见 `notes/2026-09-30-宿主弹框工具的-options-是硬区间2-4只按上限截断会漏了下限.md`）。

## Decision/正确做法

2026-10-13 定案（任务「Qoder适配」）：在约束内做正文清单体验优化，已实施并通过 `tests/test_task_session_start.py` 全部 21 项测试：
- 当进行中任务 >3 个时，question 正文明确说明「为什么只有最近任务进选项」（Qoder options 硬上限 4 个）；
- 其余任务列在「正文任务清单」，引导用户选「其他」输入任务名/task_id 关联；
- 清单末尾追加操作提示：输入任务名、task_id 或关键字，命中即关联，未命中则新建。
- 保留「正文任务清单」标记字符串——测试用 `ctx.rsplit("正文任务清单", 1)` 切片，改掉会坏测试。

## 分档隔离与同步机制

- `task_session_start.py` 通过 `IDE_DIR_NAME`（`Path(__file__).resolve().parents[1].name`）分档：`.qoder` → capped 分支（AskUserQuestion，4 options）；`.codebuddy`/`.claude`/`.gemini`/`.trae` → unlimited 分支（ask_followup_question 一框列全）。改 capped 分支不影响其他宿主。
- **改源文件后必须同步副本**：真源是 `codewiki/hooks/task_session_start.py`，`.qoder/hooks/` 等目录是 `codewiki install-hooks` 拷贝的副本；改完源文件要么手动同步副本，要么重跑 install-hooks（它会强制覆盖副本）。

## 潜在风险（未定案）

当前只把 `.qoder` 识别为 capped 宿主。若未来发现 Claude Code / Gemini CLI 也用 `AskUserQuestion` 且同样 4 选项硬上限，需把 capped 判断从「仅 .qoder」扩展为「claude 家族中实测受限的宿主」。

## Rationale

「4 项限制是宿主工具硬约束而非产品自限」这一结论反复被用户问起；且源文件/副本同步机制是改 hook 时的必踩点，值得持久化。本笔记是既有笔记「宿主弹框工具的 options 是硬区间（2-4）」的应用定案与延伸，互补不重复。
