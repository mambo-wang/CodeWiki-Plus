---
type: pitfall
title: distill_conversation submit 的 distilled 必须是 {conversation_id:{notes,memories}}
  映射，传裸对象会静默返回 missing_result
tags:
- pitfall
metadata:
  date: 2026-09-11
  related_modules:
  - distill
  - mcp
  - capture
  severity: high
  source_ref: conversations/conv-@command-codewiki-蒸馏对话提取记忆和经验.md
  scene: 对话蒸馏 Mode C 提交
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-11 01:06:06+00:00
stale_after: '2027-03-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-11T03:55:11Z'
---

## 背景

用 Mode C（Agent 自己当 LLM）提交蒸馏结果时，把 `distilled` 直接写成裸的 `{"notes": [...], "memories": [...]}` 提交，工具返回 `missing_result`、`notes_created: 0`，笔记和记忆都不落盘，且不报参数错误。改传 `conversation_id` 参数、改传 `raw_path` 都无效（同样 `missing_result`），排查时被误导去怀疑中文长文件名的 stem 截断。

## 正确做法

`distilled` 必须是**以 conversation_id 为 key 的映射**：

```json
{
  "conv-xxxx": {
    "notes": [{"title": "...", "note_type": "pitfall", "related_modules": [], "tags": [], "priority": 85, "content": "## Background\n..."}],
    "memories": ["任务进度一句话"]
  }
}
```

裸 `{notes, memories}` 形状只在**同时传了 `conversation_id` 参数**时才可用（工具据此绑定到单条）。大载荷一律走 `distilled_file` 侧通道：用 write_to_file 把上面的映射写进 `repowiki/raw/.distill-*.json`，再只传 `distilled_file=<路径>`。

## 根因

submit 内部用 `distilled_map.get(stem)` 取值，key 是会话 id（raw 文件名 stem）；传裸对象时 key 集合里没有该 stem，取空后直接判 `missing_result`，不抛形状校验错误。

## 适用范围

所有 Mode C 蒸馏提交；以及 `conflicts_pending` 时带 `dedup_action`（store/skip/update/merge + target）的重提——重提同样必须保持映射形状，且不用再带 memories（避免记忆重复落盘）。

## 关联

与 pitfall『MCP 参数长度受限时蒸馏 submit 应走 distilled_file 文件侧通道』互补：那条讲**载荷太大**怎么传（侧通道），本条讲**形状传错**会静默失败（missing_result）。两者常一起踩：先用文件侧通道解决大小，再确认里面是映射而非裸对象。
