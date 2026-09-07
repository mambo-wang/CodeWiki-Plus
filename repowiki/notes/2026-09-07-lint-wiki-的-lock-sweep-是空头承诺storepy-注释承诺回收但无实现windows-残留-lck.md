---
type: pitfall
title: lint_wiki 的 lock sweep 是空头承诺：store.py 注释承诺回收但无实现，Windows 残留 .lck 无人回收
tags:
- pitfall
- powershell
metadata:
  date: 2026-09-07
  related_modules:
  - store
  - lint
  severity: medium
  source_ref: conversations/conv-把项目中的.lck文件清理掉.md
  scene: .lck 清理
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:00:04+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:14Z'
---

## 背景

2026-09-04 清理仓库 121 个 0 字节 `.lck` 时发现两个事实：

1. Windows 下 `del /S` / `Remove-Item` 批量删除会被用户 PowerShell profile 的安全删除钩子拦截，需改用 Python 逐个 `unlink`（或 `shutil.rmtree`）。
2. **`lint_wiki` 的锁回收兜底是空头承诺**：`codewiki/src/store.py` 注释写 `leave for lint_wiki sweep`，但全仓搜索不到 lint_wiki 里任何 lock sweep / gc 实现。Windows 上 `store.locked` 的 best-effort unlink 因并发持有失败时（另一进程正持锁），该锁文件会永久残留、无人回收。

## 正确做法

- 手工清理：确认无 python 进程持锁后用 Python unlink；`*.lck` 已在 .gitignore。
- 根治方向（当时提出的待办）：在 lint_wiki 加 stale lock 检查，或对 `repowiki/.meta/locks/` 做低水位 GC。

## 分布参考

集中式锁改造前的旧 sidecar 残留在 `repowiki/notes/`（115 个）；当前集中式路径 `repowiki/.meta/locks/` 只有少量。
