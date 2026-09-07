---
type: lesson
title: 维护者 git reset --hard 归位分支前必须检查用户未提交改动；CodeWiki-Plus 上游 Issues 已关（API 410）
tags:
- '17'
- '18'
- codewiki
- github
- lesson
metadata:
  date: 2026-09-07
  related_modules:
  - git
  severity: medium
  source_ref: conversations/conv-处理-PR-https-github.com-mambo-wang-CodeWiki-Plus-pull-17.md
  scene: 上游 PR 维护
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:02:48+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:24Z'
---

## 背景

2026-08-26 处理完 PR #17/#18 后归位本地 develop：执行 `git reset --hard origin/develop`，抹掉了用户工作区未提交的 README 改动（thank-you 图）；凭此前记录的 diff 手工恢复；iamwangbao 的 telemetry jsonl 运行数据丢失（可忽略）。

## 教训

维护者在用户工作区上做分支操作时，`reset --hard` 前必须先检查未提交改动（`git status` + 必要时 stash 或备份 diff 到文件）。工作区不是维护者私有的——上面可能有用户自己的未提交内容。

## 同场其他事实

- PR head 与自己推送的 SHA 不符时先核查：本例是用户自己在分支上追加提交（bca885c）并推送，搭车进了 PR #18，无内容丢失。
- CodeWiki-Plus 上游仓库的 GitHub Issues 功能已关闭（创建 issue 返回 API 410），记账只能改走 Wiki 笔记/汇报，不要依赖 issue 留痕。
