---
type: pitfall
title: codewiki MCP 工具必须显式传 repo_path：缺省时 list_tasks 返回空、set_session_task 报任务不存在
tags:
- codewiki
- pitfall
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 产品维护
  source_session: 866c3f80-00e6-4cf2-a227-ed85ecea806a
  related_modules:
  - mcp-tools
  severity: medium
  source_ref: conversations/conv-拉取最新代码.md
  scene: 任何 agent 通过 MCP 调用任务记忆/蒸馏工具
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:14:16+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:03Z'
source_conversations: ['conversations/conv-system-reminder-The-user-selected-the-following-plugins-that.md']

---

## Pitfall

MCP server 会话里不传 `repo_path` 时，布局推导失败且**不报错**：`list_tasks` 静默返回空列表、`set_session_task` 报 `Task 'xxx' does not exist`——极易误判为「任务存储被清空/归档」。实际任务目录（`repowiki/tasks/<task_id>/task.md`）物理存在。

## 正确做法

所有 codewiki MCP 工具调用一律显式传 `repo_path`（如 `repo_path="D:\\repos\\CodeWiki-Plus"`），与 Doctrine「路径与归属：显式参数 > 布局推导 > session 缓存」一致。诊断顺序：工具说任务不存在 → 先 `ls repowiki/tasks/` 核对物理存在 → 补 repo_path 重试。

## 附带事实

- `get_task_context` 在上下文很大时可能超时（实测连续两次 `MCP error -32603: MCP tool invocation did not complete`）；不阻塞主线，可改用 `add_task_memory` 直写通道继续，稍后在自然停顿点重试拉取。
- `add_task_memory` 直写可靠（返回 entry_id 与 hot_entries 计数），任务记忆无需确认闸门（ADR-0002）。

与既有笔记 `notes/2026-10-12-子代理派发指令必须自包含寻址参数要烘进指令文本不能依赖主-agent-会话态.md` 互补：那条讲派发指令要自包含的原则，本条是 repo_path 缺省的具体症状与诊断路径。

## codewiki MCP 写入工具缺 repo_path 会静默落到服务器安装目录而非项目 repowiki

> 合并自蒸馏候选：codewiki MCP 写入工具缺 repo_path 会静默落到服务器安装目录而非项目 repowiki

## 症状

`ingest_note` 调用成功并返回 `note_path`，但笔记落在了 `C:\Users\<user>\AppData\Local\Programs\Qoder CN\.qoder-versions\<ver>\repowiki\notes\`——MCP 服务器自己的安装目录，而不是项目的 `repowiki/notes/`。原因：调用时省略了 `repo_path` 参数，服务器回退到自身默认 output_dir。

## 规避

1. codewiki MCP 的写入类工具（ingest_note / write_doc_file / confirm_note 等）**每次调用都显式传 repo_path**，不依赖会话态兜底——子代理、新会话、跨宿主场景下 session 缓存不可用；
2. 落盘后用 `ls -t <repo>/repowiki/notes/` 磁盘核验返回的 note_path 是否在项目内；
3. 误落后只删自己创建的那个文件——那个目录里可能有历史会话回退写入的其他内容（task bindings、wiki），不能整目录删。

## 依据

2026-10-14 会话实测：首次 ingest 返回的 note_path 指向 .qoder-versions 目录，带 repo_path 重投后落到项目内，误落副本已清理。
