---
type: lesson
title: "Windows 未跟踪文件消失的取证链：git→IDE 历史→回收站（Shell.Application COM）"
tags: ["comobject", "lesson", "namespace", "originalpath", "powershell"]
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 产品维护
  source_session: "1ef499c7-0214-4c49-8199-9789da0dd7d3"
  severity: medium
  source_ref: "conversations/conv-现在记忆数量超过阈值会提示用户是否压缩记忆，我觉得可以改成不提示用户确认，直接跑subagent来压缩记忆.md"
  scene: "Windows 调试/文件恢复"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.15.0, at: 2026-10-21T12:06:55Z }
stale_after: 2027-04-19
origin: conversation

---

## Background

未跟踪的 `docs/articles/终结篇.md` 与 `images/`（约 20张图）在两次提交之间从磁盘消失。需要判定丢失原因与可恢复性。

## Lesson

Windows 下未跟踪文件消失的取证链（按序排查，成本递增）：
1. `git ls-files -d`（是否 git 删除）→ 空；
2. `git log --all --full-history -- <path>` + `git stash list` + `git fsck --lost-found`（是否曾被跟踪/hashed）→ 零命中；
3. IDE 本地历史 `%APPDATA%/<IDE>/User/History` grep 文件名 → 零命中；
4. **回收站**：PowerShell `Shell.Application` COM 查询 `(New-Object -ComObject Shell.Application).NameSpace(0xA)`，取 NAME/OriginalPath/删除时间 → 命中。

关键判据：`rm` 不进回收站——回收站有记录说明是 Explorer/IDE 级删除（外部会话或用户手工），且可整件还原。

## Rationale

未跟踪文件 git 侧零痕迹，回收站往往是唯一恢复来源；先穷尽 git/IDE 侧再查回收站，可准确归因「谁删的」。

## 依据

本次会话中实测该取证链并命中（2026-10-12，三项文件于 11:24 被移入回收站）。
