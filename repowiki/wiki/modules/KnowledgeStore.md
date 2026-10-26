---
type: Module
title: KnowledgeStore
description: '`KnowledgeStore` 是 CodeWiki 的持久化存储层（`codewiki/src/store.py` + `codewiki/src/frontmatter.py`
  + `codewiki/mcp/tools/store_bridge.py`），为单个 repowiki 根提供三样基础：跨进程安全的原子文件写原语（`atomic_write`
  + 集中于 `.meta/locks/` 的锁文件…'
tags:
- CodeWiki-CN
- knowledgestore
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 04:17:31+00:00
stale_after: 2026-12-03
aliases:
- KnowledgeStore
status: stable
metadata:
  generated_from: 2ce7507
  resource: repo://CodeWiki-CN
  code_fingerprint: sha256:e063ed6853b372d74b62efa26246281188aba13483f64c74c72a0abd9947181b
sources:
- id: repo://codewiki/src/store.py
  resource: repo://codewiki/src/store.py
  content_hash: sha256:aa31e9b5d680d53ee03c9ea6cd0e240e37c5a7fe27219f554fb149c2e2556b69
- id: repo://codewiki/src/frontmatter.py
  resource: repo://codewiki/src/frontmatter.py
  content_hash: sha256:6150fca7b98abd18a5ced3bf332b429bed61f74766f78e0cc0fa9bba3afe970c
- id: repo://codewiki/mcp/tools/store_bridge.py
  resource: repo://codewiki/mcp/tools/store_bridge.py
  content_hash: sha256:0577080bee241e49e26103c68cdf3a0797b6ca59bc6a67c9853940c9213f53fd
- id: repo://codewiki/src/git_sync.py
  resource: repo://codewiki/src/git_sync.py
  content_hash: sha256:e7947d4e462736ae3f0513f2bdea5d0d3c1b36336caeb48b56a3de6dc25eaf28
---
# [KnowledgeStore](../../../codewiki/src/store.py) 模块文档

## 概述
`KnowledgeStore` 是 CodeWiki 的持久化存储层（`codewiki/src/store.py` + `codewiki/src/frontmatter.py` + `codewiki/mcp/tools/store_bridge.py`），为单个 repowiki 根提供四类基础：跨进程安全的原子写与 Git 暂存原语（`atomic_write` / `_stage_removal` + `.<name>.lck` 边车锁族）、统一 frontmatter 解析与轻量 `Page` 只读对象、`KnowledgeStore` 门面（root 下路径解析、页面读写枚举、raw/任务索引缓存），以及按用户分文件的任务记忆（持久 `#id`、supersede 退役标记、条目级 BM25 检索）。`parse_frontmatter` 是全仓库 frontmatter 解析的唯一收敛点；`resolve_output_dir` 把工具调用路由到正确的工作区知识库根（布局路由在 bridge 完成，存储层不感知多仓布局）。

## 组件清单

| 组件 | 类型 | 文件 | 职责 |
|------|------|------|------|
| `atomic_write` / `_atomic_replace_with_retry` / `_stage_removal` | 函数 / 私有函数 | store.py | 崩溃安全写：同目录临时文件（pid+线程 id 命名）+ `os.replace`（5 次短退避重试抗杀软/索引器短暂占用），`finally` 清理残留临时文件；写成功后在统一漏斗里 best-effort `auto_stage`，删除经 `_stage_removal` 同步 Git 索引（只 stage，不 commit/push） |
| `locked` | 上下文管理器 | store.py | 经 `<wiki-root>/.meta/locks/<sha256[:20]>.lck` 集中锁文件跨线程/跨进程串行化读改写序列（无 `.meta` 祖先时回退目标旁 `.<name>.lck` 边车）；锁独立文件而非目标（Windows 锁文件无法被 rename 覆盖）；Windows 释放时在每路径线程锁临界区内删除锁文件，避免 delete-pending 与兄弟线程 `os.open` 竞争，Unix 刻意保留锁文件防 inode 竞态 |
| `locked_write` | 函数 | store.py | `locked()` + `atomic_write()` 的组合写；团队布局约定下共享文件跨进程写入的标准原语 |
| `locked_rmw` | 函数 | store.py | 锁内读-转换-原子写；`transform` 返回 `None` 中止写（只读窥探），否则返回新文本；ADR-0009 的 supersede 校验失败用内部 `_SupersedeError` 穿过 transform 契约上报 |
| `Page` | 类 | store.py | 轻量只读文档对象（relpath / 绝对路径 / frontmatter / body） |
| `KnowledgeStore`（含 `path`/`relpath`/`_read_text`/`page`/`iter_pages`/`write`/`update_frontmatter`/`content_hash`/`_raw_index`/`_rebuild_raw_index`/`read_task_index`/`write_task_index`/`find_task`/`find_note_by_title`） | 类 | store.py | 单个 repowiki 根的持久化门面：目录/文件路径解析、BOM 容忍读、页面解析与枚举、原子写与 frontmatter 定点更新、raw 与任务索引缓存（目录为真相、缓存校验重建） |
| `capture_raw` / `pending_raws_by_task` / `mark_raw_distilled` / `sync_raw_index` / `delete_raw` | 方法 | store.py | raw 暂存区生命周期：落盘捕获（content_hash 去重 + supersede 继承 task_id；已消费凭证走 archived binding 兜底归属）、按任务汇总待蒸馏清单、蒸馏后索引置位/删除（`_raw_rel` 同时接受 `raw/<name>` 与裸文件名两种约定） |
| `read_binding` / `write_binding` / `remove_binding` / `archive_binding` / `read_archived_binding` / `session_ids_for_task` / `clear_bindings_for_task` / `gc_bindings` | 方法 | store.py | 会话绑定凭证（`.meta/task_bindings/<session>.json`）读写；raw 捕获消耗 live 凭证时转为 `bindings/consumed/` 墓碑而不是直接删除，后续捕获仍可继承 task_id；`session_ids_for_task` 反查任务关联的 live + consumed 会话；`clear_bindings_for_task` 供 delete_task 级联，`gc_bindings` 连带清理过期墓碑 |
| `split_entries` / `split_summary_and_entries` / `entry_sort_key` / `format_memory_entry` | 函数 | store.py | 任务记忆条目切分工具：按 `### ` 时间戳头切条、分离「早期记忆（摘要）」段与条目段、按时间戳排序、生成带 `### YYYY-MM-DD HH:MM` 头的条目——压缩/分层/截断的解析边界（ADR-0001）；`at` 可写入对话真实时间，`entry_id_` 可附加持久 id |
| `entry_id` / `new_entry_id` / `entry_display_ids` / `entry_is_superseded` | 函数 | store.py | ADR-0009 条目身份：持久 `#a3f2` 随机 id（碰撞校验）、为无 id 的历史条目生成 `#e01` 顺序展示号、识别标题下的 `> [superseded ...]` 退役标记 |
| `append_memories` / `supersede_memory` / `search_memories` | 方法 | store.py | 任务记忆读写闭环：跨进程锁内追加带 id 条目（支持同批统一时间与预分配 id）、按持久 id/顺序号写入退役标记（`dry_run` 先校验防孤儿条目）、单任务 live+archive 的条目级 BM25 检索（superseded 不参与打分） |
| `parse_frontmatter` | 函数 | frontmatter.py | 分离文档 frontmatter 与正文（全仓库唯一解析收敛点，json 解码标量值） |
| `resolve_output_dir` | 函数 | store_bridge.py | 把工具调用的 `output_dir` 解析到知识库根：集中式布局成员 → 工作区共享 repowiki；否则状态维持 `repo_path/repowiki` |

## 关键设计

- **原子文件族与集中锁**：Windows 上被打开/锁定的目标文件不能被 `os.replace` 覆盖，因此锁加在独立文件上（D19：集中存放于 `<wiki-root>/.meta/locks/`，按目标绝对路径哈希命名——锁语义只要求路径确定性映射，与相邻无关；无 `.meta` 祖先的裸 fixture 回退就地边车）；`atomic_write` 用 pid+线程 id 保证跨进程/跨线程临时名唯一，`os.replace` 带退避重试，`finally` 兜底清理。团队布局约定：跨进程共享文件（index、telemetry 等）一律经 `locked_write`/`locked_rmw`，绝不裸 `write_text`。
- **锁文件生命周期分平台**：锁本体由 `codewiki.src.locks.file_lock` 提供；释放后 Windows 在每路径线程锁临界区内尽力删除锁文件（无 inode 竞态），Unix 刻意保留——`flock` 锁的是 inode，删掉路径会让第三个进程锁上一个新文件，出现两个「独占」持有者。
- **门面与 bridge 分层**：`KnowledgeStore` 构造即绑定 root，只认 root 之下的路径，不感知多仓布局；`resolve_output_dir` 是唯一的布局路由入口（集中式 vs 就地）。
- **目录为真相、索引为缓存**：任务索引 `read_task_index` 先做廉价一致性校验（目录名 id 集合 == 缓存 id 集合），失配/损坏才扫描 `task.md` frontmatter 全量重建并回写（失败不抛错）；raw 索引同理以 `conv-*.md` frontmatter 为真相（`_rebuild_raw_index`）。`content_hash` 把 `task_id` 纳入摘要，同一段对话分属不同任务不会被去重误杀。
- **frontmatter 单点解析**：所有 frontmatter 读取统一经 `parse_frontmatter`（utf-8-sig BOM 容忍 + 读取失败返回 None），旧式手工剥引号补丁（如 `_unquote_fm`）已成兼容层——统一 reader 已做 json 解码。
- **写入即暂存、删除也留痕**：`atomic_write` 是所有知识文件写入的唯一漏斗，写入成功后在配置允许时 best-effort `auto_stage`（只 stage 不 commit/push）；删除路径调用 `_stage_removal`，避免索引中出现「已添加又删除」的幽灵条目。两者在非 git 仓库、测试环境或配置关闭时静默跳过，绝不影响主流程。
- **ADR-0009 条目身份**：每条任务记忆的标题行携带持久 `#id`；旧条目在展示时获得 `#e01` 形式顺序号；`supersede_memory` 只在目标标题下插入退役标记，原文保留，检索时排除退役条目但归档命中仍可回报 `superseded=true`。
- **已消费绑定是墓碑而非删除**：绑定凭证在首次捕获后移入 `bindings/consumed/`，既保持一次性语义，又让同一会话后续捕获在 pending raw 已蒸馏后仍能恢复 task_id；扫描/回收时 live 与 consumed 目录遵循同一套年龄规则。

## 数据流（mermaid）

```mermaid
flowchart LR
  A[resolve_output_dir] --> B[KnowledgeStore root]
  B --> C[parse_frontmatter]
  C --> D[Page / iter_pages]
  E[atomic_write / locked_rmw] --> F[meta json + task/raw index]
  E --> G[git auto_stage / stage removal]
  H[capture_raw] --> I[live and archived binding]
  H --> J[raw index]
  K[append_memories / supersede_memory / search_memories] --> L[per-user memory files]
  B --> E
  B --> K
```

## 依赖关系

- 被知识库工具层各模块消费：[MCP_Tools_Knowledge](MCP_Tools_Knowledge.md)、[MCP_Tools_Quality](MCP_Tools_Quality.md)、[MCP_Tools_Workspace](MCP_Tools_Workspace.md)。
- 存储层本身不依赖任何模块页（叶子基础设施）。

## 使用示例

```python
from codewiki.src.store import KnowledgeStore, locked_rmw

store = KnowledgeStore(root)
# 跨进程安全更新 tasks/index
new = locked_rmw(store._task_index_path(), lambda t: transform(t))
for page in store.iter_pages(scope="notes"):
    print(page.relpath, page.frontmatter.get("status"))
```
