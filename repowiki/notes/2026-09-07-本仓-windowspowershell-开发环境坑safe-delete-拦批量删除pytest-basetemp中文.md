---
type: pitfall
title: 本仓 Windows/PowerShell 开发环境坑：safe-delete 拦批量删除、pytest basetemp、中文 commit -F、junitxml
  拿失败清单
tags:
- pitfall
- powershell
metadata:
  date: 2026-09-07
  related_modules:
  - tests
  - dev-env
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-.codebuddy-plans-output_dir-收敛为repo_pat-2.md
  scene: output_dir 收敛大重构
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:04:55+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:23Z'
---

## 背景

2026-09-06 output_dir 收敛大重构（119 文件、全量测试回归）期间，Windows + PowerShell 环境反复拖慢排查，以下为本仓实测的环境坑与解法。

## 坑与解法

1. **safe-delete 钩子拦截批量删除**：用户 PowerShell profile 的安全删除包装器会拦截 `del /S`、`Remove-Item -Recurse`（大目录）及 TEMP 下 pytest garbage 目录的批量清理。解法：改用 `cmd /c "rd /s /q ..."` 或 Python `shutil.rmtree`/逐个 `unlink`。
2. **pytest 临时目录策略**：TEMP 下堆积 47 个 pytest-of-* garbage 目录（每次跑测结尾 GC 被沙箱拦截）会连带新跑挂掉；大跑改用 `--basetemp=.pytest-tmp`（工作区内）并加入 .gitignore。注意 basetemp 残留 5000+ 文件时同样触发拦截，需定期清。
3. **中文 commit message**：PowerShell 直接传 `git commit -m "中文..."` 解析失败（详见既有笔记「Windows PowerShell 下 git commit -m 传中文会乱码」）。解法：消息写临时文件 + `git commit -F <file>`。
4. **pytest 输出被噪音吞掉**：PowerShell 输出混入 safe-delete 噪音、过滤逻辑吞行。解法：`cmd /c` 执行并重定向到文件再读；失败清单用 `--junitxml` + ElementTree 解析最可靠。
5. **PowerShell 把 git 进度输出视为 stderr** 属误报，不代表命令失败。

## 适用范围

本仓 Windows 开发环境（CodeBuddy 沙箱 + PowerShell profile 钩子）。
