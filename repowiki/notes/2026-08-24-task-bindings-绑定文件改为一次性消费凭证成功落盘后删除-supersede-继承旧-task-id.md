---
type: decision
title: task_bindings 绑定文件改为一次性消费凭证：成功落盘后删除 + supersede 继承旧 task_id
tags:
- decision
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - task_manager
  - capture_conversation
  severity: high
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-repowiki-.meta-task_bindings-这里边残留的数据什么.md
  consolidated_into:
  - wiki/scenarios/任务记忆系统设计方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 15:17:27+00:00
stale_after: '2027-08-24'
origin: conversation
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T15:30:14Z'
reject_reason: 聚合进场景：任务记忆系统设计方法
---

## 背景

用户发现 repowiki/.meta/task_bindings/ 累积 16 个绑定文件（15 指向产品维护、1 指向架构分析），询问何时自动删除。原设计（08-15）：绑定文件由 set_session_task 写入、capture_conversation 消费，但**消费后不删除**（代码标注 intentionally NOT auto-deleted），delete_task 时级联删除、complete_task 不删——所以历史会话绑定永久残留。

## 决策

绑定改为「一次性消费凭证」：capture_conversation 成功落盘后（task_source==binding 且 source_session_id 存在）自动删除 <source_session_id>.json；显式传 task_id 时不消费绑定；删除失败只忽略不阻塞。为防 supersede（同会话二次捕获覆盖旧 raw）时丢归属，加防御：本次解析不到 task_id 时从被替换旧 entry 继承 task_id，重算 content_hash（task_id 参与哈希），task_source=返回 binding-inherited。

## 根因

原设计把「消费」与「清理」分离，消费后无人清理导致残留累积；且 supersede 分支 new_entry task_id 用本次解析结果，若绑定已删会覆盖成空丢归属。删除必须发生在 raw 文件成功落盘后（hook wrapper 是 fire-and-forget，child 异步写盘，删早了会丢）。此决策取代 08-15 的「绑定不被自动消费」旧语义（旧笔记已 deprecated）。
