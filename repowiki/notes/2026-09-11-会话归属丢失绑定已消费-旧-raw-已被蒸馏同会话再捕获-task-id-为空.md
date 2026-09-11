---
type: pitfall
title: "会话归属丢失：绑定已消费 + 旧 raw 已被蒸馏，同会话再捕获 task_id 为空"
tags: ["pitfall"]
aliases: ["task_id 为空", "归属丢失", "binding consumed", "raw 无 task_id"]
metadata:
  date: 2026-09-11
  related_modules: ["store", "task-bindings", "capture-conversation"]
  severity: high
  root_cause: "supersede 继承源只覆盖 raw/.index.json 中 status=pending 的条目；蒸馏删除文件并摘掉索引条目后继承源消失，而一次性凭证已在首次捕获时被销毁，导致归属无处可取。"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T02:48:53Z }
stale_after: 2027-03-10
---

## 现象

同一会话再次捕获后，raw 的 frontmatter **没有 `task_id`**，对话蒸馏后不会归到目标任务，只会变成无归属笔记。会话开始提示却显示「任务 X: 1 条积压」，按 `task_id` 查又是 0 条——两个数字对不上就是这个原因。

排查时的关键信号：`repowiki/raw/.index.json` 里该条 `task_id` 为空字符串，且 `repowiki/.meta/task_bindings/<source_session_id>.json` **已不存在**。凭证被消费了，产物却没盖章。

## 根因

`capture_raw` 的归属继承只有两级：

1. 读绑定凭证（`task_source=binding`），成功后**销毁**凭证
2. supersede 时从索引里 `status=pending` 的旧条目继承（`task_source=binding-inherited`）

第 2 级的继承源是**索引里的 pending 条目**，而蒸馏会删除 raw 文件并摘掉索引条目。于是：

```
首条捕获（拿到 task_id，凭证销毁）→ 蒸馏（文件+索引条目消失）→ 同会话再捕获
→ 无凭证可读，无 pending 条目可继承 → task_id = ""
```

凭证已毁、继承源已失，两头皆空。

## 正确做法

- 修复：凭证消费后**退役**到 `task_bindings/consumed/<sid>.json` 而非删除，并新增第三级回退 `task_source=binding-archived`（见 decision 笔记《绑定凭证消费后退役到 consumed/ 而非删除》）。
- 排查同类问题：先看 `raw/.index.json` 的 `task_id`，再看 `task_bindings/` 与 `task_bindings/consumed/` 里有没有对应 session 的凭证。三者皆空 = 归属已丢且不可追溯（凭证是一次性的）。

## 排查陷阱（我踩过的）

第一反应是「凭证被消费了但 task_id 漏写进 frontmatter」。**这个假设是错的**：受控实验跑 4 个场景（绑定在/不在 × 首次/重捕），`binding → task_id` 链路全部正确。真凶是继承源消失，不是写入漏字段。**先做受控实验证伪直觉，再动手改代码**——凭症状猜根因会改错地方。

## 检测

回归测试 `tests/test_knowledge_store.py::test_attribution_survives_distilled_raw_via_archived_binding` 固定了这个场景。
