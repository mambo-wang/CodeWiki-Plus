---
type: decision
title: 锁文件清理采用「仅 Windows 释放即删」，Unix 一律保留不删
tags:
- codewiki
- decision
- knowledgestore
metadata:
  date: 2026-09-04
  task_id: 产品维护
  related_modules:
  - store
  - file_lock
  - lint_wiki
  severity: high
  source_ref: conversations/conv-REVIEW本地变更区代码，测试相关功能.md
  scene: KnowledgeStore 跨进程锁治理
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 08:18:23+00:00
stale_after: '2027-09-04'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-04T08:21:03Z'
---

## Background

CodeWiki 的 `KnowledgeStore` 用 sidecar 锁文件做跨进程互斥，锁文件放在 `<wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck`（D19 集中化之后）。锁文件用完不删，会随运行时间累积一个哈希一个文件。讨论「能否自动清理」时评估了两种机制：释放时 unlink，以及 `lint_wiki` 定期补刀。

## Decision（正确做法）

用户 2026-09-04 拍板采用「**仅 Windows 释放即删**」：

- 在 `store.locked()` 的出口做 **best-effort unlink（吞掉所有异常）**，不因删除失败影响正常释放流程；
- 该逻辑**只在 Windows 分支启用**，Unix（fcntl/flock）保留「锁文件永不删」的行业惯例；
- 在 `locks.py` 与相关 docstring 中注明 Unix 不删的原因，避免后来者误以为漏实现；
- 规模约 10 行代码 + 配套测试。

## Rationale

- **Windows 可行且安全**：本机实测（win32 / Python 3.14.5），锁文件一旦被任何进程打开（持锁或等锁），`unlink` 直接抛 `WinError 32`（共享冲突）。也就是说「删不掉」本身就是「有人正在用」的天然探测信号，清扫永远不会误删活跃锁；且 Windows 的删除在最后一个句柄关闭前不真正生效，不存在 Unix 式 inode 竞态。正确顺序是先 `close` 释放锁再 `unlink`。
- **Unix 不可行（根因）**：经典 inode race。等锁进程已经 `open` 了旧 inode 的 fd，释放方 unlink 成功后，新进程 `open` 得到的是**新 inode**，两把锁落在不同 inode 上互不相干 → 互斥被破坏，并发 read-modify-write 直接丢更新。这正是「锁文件用完不删」作为行业惯例的来源。

## 被否决的备选方案

`lint_wiki` 补刀（复用其 `fix=true` 自愈先例，如 `stale_refs` 自愈 index）：

1. 锁文件存在是**常态而不是问题**，只能做 fix-only 清扫，不能当作 check 项上报（否则 lint 长期红灯）；
2. Unix 下补刀同样踩 inode race（除非加 `LOCK_NB` 探测，仍残留微小窗口）；
3. 一旦「释放即删」生效，残留只剩「释放瞬间恰好有人在等锁」的瞬态，数量被钉死在上界，补刀收益极小。

## 适用范围

所有基于 `store.locked()` 的 sidecar 锁。锁文件是 git-ignored 的机器本地状态（KB 级、藏在 `.meta/locks/`、上界 = 曾被锁过的目标数），累积本身无正确性影响——本决策是为整洁性做的低风险优化，不是修 bug。
