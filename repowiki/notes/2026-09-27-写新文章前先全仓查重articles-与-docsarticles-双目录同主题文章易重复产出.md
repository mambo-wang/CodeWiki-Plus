---
type: lesson
title: 写新文章前先全仓查重：articles/ 与 docs/articles/ 双目录同主题文章易重复产出
tags:
- lesson
metadata:
  date: 2026-09-27
  confidence_level: weak
  source_session: 9229108d70934c30a5ee699d6afee8d6
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-2fc4c1.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 04:55:32+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-09-27T05:01:31Z'
- by: human:wangbao
  at: '2026-09-27T07:50:27Z'
source_conversations:
- conversations/conv-working_memory_content-The-following-is-the-existing-working-107386.md
---

## Background
2026-09-27 会话中用户要求基于 README 写一篇 CodeWiki 使用全景总结文章。助手先写了 `articles/2026-09-27-codewiki-使用全景与最佳实践.md`，随后通过工作记忆与全仓搜索发现：当天早些时候的另一会话已在 `docs/articles/` 写过同主题文章「CodeWiki-Plus系列14：使用全景与最佳实践——从初始化到知识飞轮的完整路线图.md」（约 17.9 KB，7 阶段结构）。

## 事件
两篇内容高度重叠（同一条「初始化 → 按需生成 → 按需启用任务管理」主线），用户最终拍板保留 `articles/` 新篇、删除系列 14。删除前全仓搜索确认无其他文件引用系列 14（仅 raw 对话转录提及，属暂存区不用处理）。

## Root cause
`articles/` 与 `docs/articles/` 双目录并存，同主题文章分散在两处，写新文章前若只查一个目录就会重复产出。

## 正确做法
1. 写文章前先全仓搜索主题关键词（两个目录都查）；
2. 发现重复后不要自行取舍，列出选项（保留新篇/保留旧篇/并存差异化/合并）交用户拍板；
3. 删除被淘汰文章前全仓搜索引用，确认无死链。

## Rationale
重复文章会分裂读者注意力与维护成本；双目录布局使查重必须覆盖全仓而非单目录。
