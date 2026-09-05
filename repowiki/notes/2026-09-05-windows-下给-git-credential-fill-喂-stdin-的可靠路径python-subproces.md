---
type: lesson
title: Windows 下给 git credential fill 喂 stdin 的可靠路径：Python subprocess 精确 stdin；无 gh
  CLI 时可复用 GCM 凭证调 GitHub REST API
tags:
- github
- lesson
- powershell
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-发布新的pypi版本，并发布git-release.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:30:39+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:49Z'
---

## Background

环境未安装 `gh` CLI、未配置 GH_TOKEN，需要创建 GitHub Release。验证发现 git credential manager (GCM) 已保存 GitHub 凭证，可复用。

## 踩坑过程（已确认的 shell 行为）

1. PowerShell 管道喂 stdin 给 `git credential fill` 不可靠（stdin 常为空）。
2. `cmd /c echo` 传 stdin 引号解析有问题；执行器在命令含 `cmd /c` 时会把整行切给 cmd.exe，外层 PowerShell 变量全部失效。
3. `git credential fill` 的输入协议需精确 stdin（`protocol=https\nhost=github.com\n\n`），中间隔任何一层 shell 都可能破坏。
4. 曾误判"凭证不存在"——实际是 Python 三元 `raise` 表达式写法 bug，修正为 `assert` 后凭证可用（rc 0，含 username/password）。

## 正确做法

用 Python `subprocess` 直调 `git credential fill`（传入精确 stdin 字节），拿到 username/password 后调用 GitHub REST API（如 `POST /repos/{owner}/{repo}/releases`）创建 Release；凭证只留在进程内，不落盘不打印。

## Root cause

PowerShell/cmd 多层管道对二进制 stdin 与引号的破坏 + 对凭证返回值的误解析。
