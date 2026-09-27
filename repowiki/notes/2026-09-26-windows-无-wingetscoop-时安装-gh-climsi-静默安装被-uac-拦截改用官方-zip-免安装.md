---
type: procedure
title: Windows 无 winget/scoop 时安装 gh CLI：msi 静默安装被 UAC 拦截，改用官方 zip 免安装版
tags:
- procedure
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 0bf7597a49a6454d97c6523997109749
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-5af19e.md
  scene: 发布流程
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:22:12+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:23Z'
---

## Background
本机 winget 不可用、scoop 是空壳（shims 目录为空），msi 静默安装（msiexec /qn）运行超过 1 分钟未生效，疑似被 UAC 提权拦截。

## 正确做法
用官方 zip 免安装版：`python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/cli/cli/releases/download/vX/gh_X_windows_amd64.zip', ...)"` 下载 → `Expand-Archive` 解压到本地目录（如 `C:\Users\Administrator\gh-cli`）→ 把 `bin` 目录写入用户级 PATH。

## Rationale
Windows 下安装 CLI 工具链的通用兜底路径：winget/scoop/msi 都不行时 zip 免安装版永远可用。
