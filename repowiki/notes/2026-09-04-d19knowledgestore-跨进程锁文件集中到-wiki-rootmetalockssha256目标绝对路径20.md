---
type: architecture
title: D19：KnowledgeStore 跨进程锁文件集中到 <wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck
tags:
- architecture
- knowledgestore
metadata:
  date: 2026-09-04
  task_id: 产品维护
  related_modules:
  - store
  - config
  - git_sync
  severity: medium
  source_ref: conversations/conv-REVIEW本地变更区代码，测试相关功能.md
  scene: KnowledgeStore 跨进程锁治理
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 08:18:34+00:00
stale_after: '2027-09-04'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-04T08:21:04Z'
---

## Background

D19 之前，`KnowledgeStore` 的跨进程锁以 `<name>.lck` 边车形式散落在**被锁目标的旁边**，污染内容树（例如 wiki 页面目录里出现锁文件），也给团队化布局的「内容树只放内容」约束带来例外。D19 将其迁移为集中存放。该变更共 7 文件 +109/−13，已在 2026-09-04 review 通过（可直接提交，无必须修改项）。

## 结构事实

- 新落点：`<wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck`，由 `codewiki/src/store.py` 的新函数 `_lock_path_for()` 计算：往上找最近的 `.meta` 祖先作为 wiki 根 → 用 `locks_dir` + 绝对路径哈希命名；**找不到 `.meta` 祖先时回退为就地 sidecar**（fail-open，锁放置不会 fail-closed，裸 fixture / 非 wiki 路径仍可用）。`locked()` 改为调用它。
- 互斥正确性不受影响：锁语义只依赖「目标 → 锁路径」的**确定性映射**，与「锁文件是否与目标相邻」无关。`hashlib` 在改动前已被 import，无新增依赖。
- 配套：`codewiki/src/config.py` 的 `TEAM_LAYOUT_REBUILDABLE_FILES` 增加 `.meta/locks/`（标记为可重建、免冲突）；`.gitignore` 与 `gitignore.tpl` 忽略 `repowiki/.meta/locks/`，同时保留 `*.lck` 兜底旧边车（旧版边车锁在 `git_sync.py:334` 也有 `*.lck` unstage 兜底）。
- 实测验证：wiki 页面与 `.meta/` 内文件（如 `aggregate_state.json`）的锁均正确落在 `repowiki/.meta/locks/<hash>.lck`。
- 测试：`tests/test_phase2_concurrency.py` 16 passed（含新增 3 个：集中落点 + 内容树干净 + 幂等重获取、无 `.meta` 时回退 sidecar、跨进程双 subprocess 对同一计数器各 +15 断言结果 =30 且仅 1 个锁文件），加上 test_locks / knowledge_store / layout_routing / phase3_4 / phase4_second_slice 共 63 passed，合计 79 passed（Windows / Python 3.14.5）。

## 已知边界（review 记录，非阻塞）

1. **锁文件无限累积**（git-ignored，无正确性影响）——后续决策见「仅 Windows 释放即删」。
2. `_lock_path_for()` 每次调用都做 `resolve()` + 逐级祖先 `is_dir()` 遍历 + `mkdir`；写路径属低频操作，可接受，若成热点可缓存「root → locks_dir」映射。
3. **Windows 路径大小写**：两个进程以不同大小写形式传入同一目标时，`resolve()` 保留原 casing → 哈希不同 → 锁不互斥。CodeWiki 内部路径均经 root 归一化生成，实际风险极低；docstring 已注明映射是「deterministic on this machine」。
4. **升级窗口**：新旧进程对同一目标算出的锁路径不同，期间**互不互斥**，升级须重启 server。
