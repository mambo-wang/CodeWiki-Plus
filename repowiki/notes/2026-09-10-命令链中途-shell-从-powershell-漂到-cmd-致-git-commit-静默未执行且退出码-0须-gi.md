---
type: lesson
title: 命令链中途 shell 从 PowerShell 漂到 cmd 致 git commit 静默未执行且退出码 0，须 git log 复核落盘
tags:
- lesson
- powershe
- powershell
metadata:
  date: 2026-09-10
  related_modules:
  - git
  - env
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-知识聚合（L2-场景块）-知识聚合工作流（团队记忆融合-P.md
  scene: 版本控制 / 提交落盘
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 08:50:02+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T09:02:21Z'
---

## Background
L2 知识聚合批次提交时，第一条 `git commit` 命令因命令链中途 shell 从 PowerShell 漂到 cmd（`Measure-Object` 不被识别）而整链中断，`git commit` 实际未执行——但退出码为 0，表面「成功」。靠 `git log -1` 复核才发现 HEAD 仍是旧提交（`f08feab`），改用单条命令重跑才成功（`bbc10f9`）。

## 正确做法
- 含管道/cmdlet（`Measure-Object`、`Select-Object` 等）的命令链，不要在 shell 环境可能混用的会话里整链跑；拆成单条独立命令，每条后显式复核（`git log -1`、`git status --short`）。
- Git 关键写操作不能只信退出码：PowerShell→cmd 漂移会让整链静默不执行且返回 0。提交/推送后必须 `git log -1` 或 `git status` 复核落盘。

## Root cause
同一 execute_command 会话里 shell 环境不确定（PowerShell 与 cmd 切换），带 cmdlet 的链在 cmd 下 `Measure-Object` 未定义→链中断→前面 `cd` 已执行但 `git commit` 没跑→外层命令返回 0（cmd 对未定义命令的容错静默吞掉失败）。

## 关联
与 lesson『Windows PowerShell 下 git add 中文路径会静默失败导致 commit/amend 漏改动』同源（都属「Git 写操作静默不落地」），但形态不同：那条是中文路径静默失败，本条是 shell 漂移导致整链静默不执行且 exit 0。两者共同指向——Git 关键写操作后必须显式复核落盘，不能只信退出码。
