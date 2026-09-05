---
type: pitfall
title: file_lock 的「锁文件」可能是数据文件本身，释放即删只能加在 store.locked() 不能下沉到 file_lock
tags:
- codewiki
- pitfall
metadata:
  date: 2026-09-04
  task_id: 产品维护
  related_modules:
  - store
  - file_lock
  - wiki_index
  - workspace_bootstrap
  severity: medium
  source_ref: conversations/conv-REVIEW本地变更区代码，测试相关功能.md
  scene: KnowledgeStore 跨进程锁治理
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 08:18:32+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:31Z'
---

## Background

给锁文件加「释放后删除」清理逻辑时，直觉的落点是通用的 `file_lock()` 层——改一处全仓生效。但 `file_lock` 在 CodeWiki 里有**两类语义完全不同的调用**，在这个通用层加删除会直接删掉业务数据。

## 坑点

`file_lock` 的两类调用：

- **锁目标数据文件本身**（I/O 直接走锁句柄）：例如 `codewiki/mcp/tools/wiki_index.py` 中的 `with file_lock(shard_path) as f:`（约 221-263 行），以及 `workspace_bootstrap`。这里的「锁文件」就是内容文件，**绝不能删**。
- **锁 sidecar 哨兵文件**（锁文件本身无内容，仅用于互斥）：只有 `store.locked()` 这一类，锁路径由 `_lock_path_for()` 产出。

因此删除逻辑的唯一合法收口点是 **`store.locked()`**（sidecar 语义的唯一出口），不能下沉到 `file_lock` 通用层。

## 正确做法

1. 改锁相关行为前，先枚举 `file_lock` / `locked` 的全部调用点并区分上述两类语义；
2. 只有 sidecar 语义那一支可以做删除/迁移/清理；
3. 好消息是：全仓所有 `locked()` 使用点（git_sync、cache、doc_writer、issue_tracker、note_writer、task_manager、telemetry、session）都收口于 `store.py` 的 `locked()`，sidecar 语义的改动确确实实是「改一处即全局生效」。
